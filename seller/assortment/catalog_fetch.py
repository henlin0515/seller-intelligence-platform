"""
Best-effort competitor catalog fetch from COMPETITOR_TRACKER Column C (Shopee) and D (TikTok).

Never raises to callers — per-side status ok | na with reason.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests
from requests.exceptions import RequestException

from seller.competitor_tracker.fetcher import fetch_tiktok_page
from seller.assortment.constants import TOP_PRODUCTS_FOR_PRICE_GAP
from seller.competitor_tracker.profile import extract_shop_links_from_html, fetch_profile
from seller.competitor_tracker.utils import deep_find_keys, parse_json_blobs_from_html, safe_http_url

logger = logging.getLogger("seller.assortment.catalog_fetch")

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-PH,en;q=0.9",
    }
)
_FETCH_TIMEOUT = 20

_NAME_KEYS = ("title", "product_name", "name", "productName", "item_name")
_PRICE_KEYS = ("price", "sale_price", "salePrice", "min_price", "minPrice", "current_price")
_IMAGE_KEYS = ("image", "image_url", "imageUrl", "cover", "cover_url", "thumb_url", "thumbnail")
_LINK_KEYS = ("product_link", "productLink", "detail_url", "detailUrl", "url", "link", "pdp_url")
_SKU_KEYS = ("sku_variations", "sku", "variants", "sku_list")


def _top_visible_products(products: list[dict[str, Any]], limit: int = TOP_PRODUCTS_FOR_PRICE_GAP) -> list[dict[str, Any]]:
    """Keep top N visible products (priced first) for shop-level averages."""
    with_price = [p for p in products if p.get("price") is not None]
    pool = with_price if len(with_price) >= 3 else products
    return pool[:limit]


def _side_result(
    *,
    status: str,
    reason: str | None = None,
    products: list[dict[str, Any]] | None = None,
    shop_link: str | None = None,
) -> dict[str, Any]:
    prods = products or []
    return {
        "status": status,
        "reason": reason,
        "products": prods,
        "product_count": len(prods),
        "shop_link": shop_link or "NA",
    }


def _first_str(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _parse_price_val(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in ("value", "amount", "price", "sale_price"):
            if k in val:
                return _parse_price_val(val[k])
        return None
    s = str(val).replace(",", "").replace("₱", "").strip()
    m = re.search(r"[\d.]+", s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _sku_from_item(item: dict[str, Any]) -> list[str] | None:
    for k in _SKU_KEYS:
        raw = item.get(k)
        if isinstance(raw, list):
            out = [str(x) for x in raw if x]
            return out or None
        if isinstance(raw, str) and raw.strip():
            return [p.strip() for p in raw.replace("|", ",").split(",") if p.strip()]
    return None


def _item_to_product(item: dict[str, Any], *, base_url: str = "") -> dict[str, Any] | None:
    name = _first_str(item, _NAME_KEYS)
    if not name or len(name) < 2:
        return None
    link = _first_str(item, _LINK_KEYS)
    if link and link.startswith("/"):
        link = safe_http_url(base_url.rstrip("/") + link)
    image = _first_str(item, _IMAGE_KEYS)
    if image and image.startswith("//"):
        image = "https:" + image
    price = None
    for k in _PRICE_KEYS:
        if k in item:
            price = _parse_price_val(item[k])
            if price is not None:
                break
    return {
        "product_name": name[:512],
        "product_link": link or None,
        "product_image_url": image or None,
        "sku_variations": _sku_from_item(item),
        "price": price,
    }


def _collect_product_dicts(obj: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 14 or len(out) >= 200:
        return
    if isinstance(obj, dict):
        if _first_str(obj, _NAME_KEYS):
            row = _item_to_product(obj)
            if row:
                out.append(row)
        for v in obj.values():
            _collect_product_dicts(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:120]:
            _collect_product_dicts(item, out, depth + 1)


def _extract_products_from_html(html: str, *, base_url: str = "") -> list[dict[str, Any]]:
    if not html:
        return []
    candidates: list[dict[str, Any]] = []
    for blob in parse_json_blobs_from_html(html):
        for plist in deep_find_keys(
            blob,
            ("productList", "products", "itemList", "items", "product_list", "shopProductList"),
        ):
            if isinstance(plist, list):
                for item in plist:
                    if isinstance(item, dict):
                        row = _item_to_product(item, base_url=base_url)
                        if row:
                            candidates.append(row)
        _collect_product_dicts(blob, candidates)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in candidates:
        key = (row.get("product_link") or row["product_name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique[:150]


def _fetch_shopee_http(url: str) -> dict[str, Any]:
    detail: dict[str, Any] = {"ok": False, "url": url, "http_status": None, "html": "", "error": None}
    try:
        resp = _SESSION.get(url, timeout=_FETCH_TIMEOUT, allow_redirects=True)
        detail["http_status"] = resp.status_code
        if resp.status_code >= 400:
            detail["error"] = f"http_{resp.status_code}"
            return detail
        html = resp.text or ""
        detail["html"] = html[:500_000]
        detail["ok"] = len(html) > 500
        if not detail["ok"]:
            detail["error"] = "empty_body"
    except RequestException as exc:
        detail["error"] = str(exc)[:200]
        logger.info("Shopee fetch failed for %s: %s", url, detail["error"])
    return detail


def _resolve_tiktok_shop_urls(tiktok_link: str) -> tuple[list[str], str | None]:
    link = (tiktok_link or "").strip()
    if not link:
        return [], "No TikTok link in Column D."

    lower = link.lower()
    if "/shop" in lower or "shop.tiktok" in lower:
        return [safe_http_url(link)], None

    try:
        profile, raw_fetch = fetch_profile(link)
    except Exception as exc:
        logger.exception("Profile fetch failed for %s", link)
        return [], f"Unable to load TikTok profile: {exc}"

    if not raw_fetch.get("ok") and not raw_fetch.get("html_loaded"):
        err = raw_fetch.get("fetch_error") or "profile_fetch_failed"
        return [], f"Unable to access TikTok profile ({err})."

    shops = list(profile.get("shop_links_on_profile") or [])
    if not shops and raw_fetch.get("html"):
        shops = extract_shop_links_from_html(raw_fetch["html"])
    handle = (profile.get("handle") or "").strip()
    if handle:
        shops.append(f"https://www.tiktok.com/@{handle}/shop")
    shops = list(dict.fromkeys(safe_http_url(u) for u in shops if u))[:5]
    if shops:
        return shops, None
    return [], "No TikTok Shop link found for Column D profile."


def _fetch_catalog_from_url(url: str) -> tuple[list[dict[str, Any]], str | None, str]:
    """Return (products, failure_reason, shop_link_used)."""
    u = safe_http_url((url or "").strip())
    if not u:
        return [], "Empty shop link.", "NA"

    host = urlparse(u).netloc.lower()
    if "tiktok.com" in host or "shop.tiktok" in host:
        fetch = fetch_tiktok_page(u)
        if not fetch.get("ok") and not fetch.get("html_loaded"):
            err = fetch.get("fetch_error") or "fetch_failed"
            return [], f"Unable to access competitor store ({err}).", u
        products = _extract_products_from_html(fetch.get("html") or "", base_url=u)
        if products:
            return products, None, u
        if fetch.get("visible_text_length", 0) < 300:
            return [], "Unable to access competitor store.", u
        return [], "Shop page loaded but no products found in page data.", u

    if "shopee" in host:
        fetch = _fetch_shopee_http(u)
        if not fetch.get("ok"):
            err = fetch.get("error") or "shopee_fetch_failed"
            return [], f"Unable to access competitor store ({err}).", u
        products = _extract_products_from_html(fetch.get("html") or "", base_url=u)
        if products:
            return products, None, u
        return [], "Shopee page loaded but no products found in page data.", u

    return [], f"Unsupported shop link host: {host or 'unknown'}", u


def fetch_shopee_catalog(shopee_link: str) -> dict[str, Any]:
    """Column C — Shopee competitor shop link only."""
    link = (shopee_link or "").strip()
    if not link:
        return _side_result(status="na", reason="No Shopee link in Column C.", shop_link="NA")
    try:
        products, reason, used = _fetch_catalog_from_url(link)
    except Exception as exc:
        logger.exception("Shopee catalog fetch error")
        return _side_result(
            status="na",
            reason=f"Unable to access competitor store ({exc}).",
            shop_link=link,
        )
    if products:
        return _side_result(status="ok", products=_top_visible_products(products), shop_link=used)
    return _side_result(
        status="na",
        reason=reason or "Shopee page loaded but no products found in page data.",
        shop_link=used,
    )


def fetch_tiktok_catalog(tiktok_link: str) -> dict[str, Any]:
    """Column D — TikTok competitor shop/profile link only."""
    link = (tiktok_link or "").strip()
    if not link:
        return _side_result(status="na", reason="No TikTok link in Column D.", shop_link="NA")

    shop_urls, profile_reason = _resolve_tiktok_shop_urls(link)
    if not shop_urls:
        return _side_result(status="na", reason=profile_reason or "Unable to access competitor store.", shop_link=link)

    last_reason = profile_reason or "Unable to access competitor store."
    last_link = link
    for shop_url in shop_urls:
        try:
            products, reason, used = _fetch_catalog_from_url(shop_url)
        except Exception as exc:
            logger.exception("TikTok catalog fetch error for %s", shop_url)
            products = []
            reason = f"Unable to access competitor store ({exc})."
            used = shop_url
        last_link = used
        if products:
            return _side_result(status="ok", products=_top_visible_products(products), shop_link=used)
        if reason:
            last_reason = reason

    return _side_result(
        status="na",
        reason=last_reason or "Unable to access TikTok profile / no products found.",
        shop_link=last_link,
    )


def _product_name_set(products: list[dict[str, Any]]) -> set[str]:
    return {str(p.get("product_name") or "").strip().lower() for p in products if p.get("product_name")}


def compare_shopee_vs_tiktok(
    shopee: dict[str, Any],
    tiktok: dict[str, Any],
) -> dict[str, Any]:
    """Compare catalogs from Column C vs Column D for the same tracker row."""
    shopee_prods = shopee.get("products") or []
    tiktok_prods = tiktok.get("products") or []
    shopee_names = _product_name_set(shopee_prods)
    tiktok_names = _product_name_set(tiktok_prods)
    both = shopee_names & tiktok_names
    return {
        "shopee_product_count": len(shopee_prods),
        "tiktok_product_count": len(tiktok_prods),
        "matching_product_names": len(both),
        "only_on_shopee": len(shopee_names - tiktok_names),
        "only_on_tiktok": len(tiktok_names - shopee_names),
        "both_accessible": shopee.get("status") == "ok" and tiktok.get("status") == "ok",
    }


def _merge_products_for_import(
    shopee: dict[str, Any],
    tiktok: dict[str, Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for side in (tiktok, shopee):
        for row in side.get("products") or []:
            key = (row.get("product_link") or row.get("product_name") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def fetch_tracker_row_catalogs(
    *,
    shopee_link: str = "",
    tiktok_link: str = "",
) -> dict[str, Any]:
    """
    Fetch Shopee (C) and TikTok (D) independently; compare when both have data.
    """
    shopee = fetch_shopee_catalog(shopee_link)
    tiktok = fetch_tiktok_catalog(tiktok_link)
    comparison = compare_shopee_vs_tiktok(shopee, tiktok)
    products = _merge_products_for_import(shopee, tiktok)

    any_ok = shopee.get("status") == "ok" or tiktok.get("status") == "ok"
    return {
        "shopee_status": shopee.get("status", "na").upper(),
        "tiktok_status": tiktok.get("status", "na").upper(),
        "shopee": shopee,
        "tiktok": tiktok,
        "comparison": comparison,
        "products": products,
        "status": "ok" if any_ok else "na",
        "reason": None if any_ok else "Unable to access competitor store on both Shopee and TikTok.",
        "link_results": [
            {
                "link_type": "shopee",
                "shop_link": shopee.get("shop_link"),
                "status": shopee.get("status"),
                "reason": shopee.get("reason"),
                "product_count": shopee.get("product_count", 0),
            },
            {
                "link_type": "tiktok",
                "shop_link": tiktok.get("shop_link"),
                "status": tiktok.get("status"),
                "reason": tiktok.get("reason"),
                "product_count": tiktok.get("product_count", 0),
            },
        ],
    }


# Backward-compatible alias used by older import paths
def fetch_competitor_catalog(*, shopee_link: str = "", tiktok_link: str = "") -> dict[str, Any]:
    out = fetch_tracker_row_catalogs(shopee_link=shopee_link, tiktok_link=tiktok_link)
    primary = out["tiktok"]["shop_link"] if out["tiktok"].get("status") == "ok" else out["shopee"]["shop_link"]
    return {
        "status": out["status"],
        "reason": out["reason"],
        "products": out["products"],
        "shop_link_attempted": primary if primary != "NA" else None,
        "link_results": out["link_results"],
        "shopee": out["shopee"],
        "tiktok": out["tiktok"],
        "comparison": out["comparison"],
    }
