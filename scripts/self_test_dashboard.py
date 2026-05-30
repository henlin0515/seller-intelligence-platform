"""Local dashboard self-test — run while uvicorn is on http://127.0.0.1:8000"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("DASHBOARD_TEST_URL", "http://127.0.0.1:8000")

REQUIRED = {
    "shop_info": {"shop_id", "shop_name", "managed_tier", "bu", "lead", "bd_category"},
    "commercial": {"adgmv", "ado", "uv"},
    "paid_ads": {"ads_spend", "ads_gmv", "roas", "take_rate", "adg_pct"},
    "ams": {"ams_spend", "take_rate"},
    "mpa": {"mpa_gmv", "take_rate"},
    "fbs": {"fbs_gmv", "fbs_ado"},
    "livestream": {"seller_ls_hrs"},
    "video": {"video_adgmv", "adg_pct", "new_uploads"},
    "mdv": {"mdv_adgmv", "adg_pct"},
}

FORBIDDEN = [
    "sourceFieldsUsed",
    "calculationFormula",
    "rawData",
    "raw_debug",
    "Paid Ads Active",
    "Total ADG M",
    "Daily Net Ads",
    "VIdeo GMV Contri",
]


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode())


def post(path: str) -> dict:
    req = urllib.request.Request(BASE + path, method="POST", headers={"Content-Length": "0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def main() -> int:
    passed: list[str] = []
    issues: list[str] = []

    try:
        h = get("/health")
        if h.get("status") != "ok":
            issues.append(f"health: {h}")
        else:
            passed.append("health OK")
    except Exception as e:
        issues.append(f"health failed: {e}")
        print("\n".join(issues))
        return 1

    try:
        refresh = post("/api/seller/refresh")
        count = refresh.get("seller_count", 0)
        if not refresh.get("loaded") and count <= 0:
            issues.append(f"refresh failed: {refresh}")
        else:
            passed.append(f"Google Sheets refresh OK — {count} sellers")
    except urllib.error.HTTPError as e:
        issues.append(f"refresh HTTP {e.code}: {e.read().decode()[:400]}")
    except Exception as e:
        issues.append(f"refresh error: {e}")

    try:
        status = get("/api/seller/status")
        count = status.get("seller_count", 0)
        if count <= 0:
            issues.append(f"seller_count not > 0: {status}")
        else:
            passed.append(f"seller cache OK — count={count}")
    except Exception as e:
        issues.append(f"status error: {e}")

    searches = [
        ("Mumu PH", "mumu", "19100527"),
        ("Watch District PH", "watch", "625975"),
    ]
    for query, name_part, expected_id in searches:
        try:
            sr = get("/api/seller/search?" + urllib.parse.urlencode({"q": query}))
            results = sr.get("results") or []
            if not results:
                issues.append(f"search '{query}': no results")
            elif name_part not in results[0].get("shop_name", "").lower():
                issues.append(f"search '{query}': got {results[0]}")
            elif str(results[0].get("shop_id")) != str(expected_id):
                issues.append(
                    f"search '{query}': id {results[0].get('shop_id')} != {expected_id}"
                )
            else:
                passed.append(f"search '{query}' -> {results[0]['shop_name']} ({expected_id})")
        except Exception as e:
            issues.append(f"search '{query}': {e}")

    for sid, label in [("19100527", "Mumu PH"), ("625975", "Watch District PH")]:
        try:
            p = get(f"/api/seller/{sid}")
            sections_list = p.get("sections") or []
            payload_check = json.dumps(
                {
                    "shop": p.get("shop"),
                    "sections": sections_list,
                    "health": p.get("health"),
                    "insights": p.get("insights"),
                    "recommendations": p.get("recommendations"),
                    "charts": p.get("charts"),
                }
            )
            for f in FORBIDDEN:
                if f in payload_check:
                    issues.append(f"{label}: payload contains forbidden '{f}'")
            if len(sections_list) != 9:
                issues.append(f"{label}: expected 9 sections, got {len(sections_list)}")

            sections = {s["key"]: s for s in sections_list}
            for sk, keys in REQUIRED.items():
                if sk not in sections:
                    issues.append(f"{label}: missing section {sk}")
                    continue
                got = {m["key"] for m in sections[sk].get("metrics", [])}
                miss = keys - got
                if miss:
                    issues.append(f"{label}: {sk} missing metrics {miss}")

            passed.append(f"dashboard API {label} — 9 sections, metric keys OK")
        except Exception as e:
            issues.append(f"dashboard {label}: {e}")

    # index page
    try:
        with urllib.request.urlopen(BASE + "/", timeout=30) as r:
            html = r.read().decode()
        if "Seller Intelligence" not in html and "Seller Performance" not in html:
            issues.append("index HTML missing seller intelligence UI")
        if "rawDebugPanel" in html:
            issues.append("index HTML still has rawDebugPanel")
        if "rawDataSection" in html:
            issues.append("index HTML still has rawDataSection")
        else:
            passed.append("index page loads — no debug/raw panels in HTML")
    except Exception as e:
        issues.append(f"index page: {e}")

    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for x in passed:
        print(f"  PASS: {x}")
    for x in issues:
        print(f"  FAIL: {x}")
    print("=" * 60)
    if issues:
        print(f"FAILED ({len(issues)} issues)")
        return 1
    print(f"ALL PASSED ({len(passed)} checks)")
    print(f"\nOpen in browser: {BASE}/")
    print("Then: Seller Intelligence → search Mumu PH or Watch District PH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
