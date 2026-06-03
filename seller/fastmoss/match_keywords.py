"""Generate FastMoss search keyword variants for a TikTok shop name."""

from __future__ import annotations

import re
import unicodedata

# Trailing / embedded noise common in sheet names (PH marketplace).
_SUFFIX_PATTERNS = (
    r"\bofficial\s*store\b",
    r"\bflagship\s*store\b",
    r"\bofficial\b",
    r"\bmall\b",
    r"\bstore\b",
    r"\bshop\b",
    r"\bph\b",
    r"\.ph\b",
)

_TOKEN_SPLIT = re.compile(r"[\s._\-/\\|+&,]+")


def _strip_emojis(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if unicodedata.category(ch) in {"So", "Sk", "Cn"}:
            continue
        out.append(ch)
    return "".join(out)


def _squeeze_spaces(text: str) -> str:
    return " ".join(text.split())


def _apply_suffix_strips(text: str) -> list[str]:
    """Progressive stripping of store/shop/mall/ph suffixes."""
    variants: list[str] = []
    current = text
    for _ in range(4):
        variants.append(current)
        nxt = current
        for pat in _SUFFIX_PATTERNS:
            nxt = re.sub(pat, " ", nxt, flags=re.IGNORECASE)
        nxt = _squeeze_spaces(nxt.strip(" .-_"))
        if not nxt or nxt.lower() == current.lower():
            break
        current = nxt
        variants.append(current)
    return variants


def _tokens(text: str) -> list[str]:
    parts = [p for p in _TOKEN_SPLIT.split(text) if len(p) >= 2]
    seen: list[str] = []
    for p in parts:
        key = p.lower()
        if key not in {x.lower() for x in seen}:
            seen.append(p)
    return seen


def generate_search_keywords(
    tiktok_shop_name: str,
    *,
    max_keywords: int = 14,
) -> list[str]:
    """
    Build ordered unique search keywords (exact → normalized → token variants).
    Example FS.STORE23 → FS.STORE23, FS STORE23, FSSTORE23, FS, STORE23, …
    """
    raw = _squeeze_spaces(_strip_emojis((tiktok_shop_name or "").strip()))
    if not raw:
        return []

    ordered: list[str] = []

    def add(value: str) -> None:
        key = _squeeze_spaces(value.strip())
        if len(key) < 2:
            return
        if key not in ordered:
            ordered.append(key)

    add(raw)
    add(raw.lower())

    no_punct = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    no_punct = _squeeze_spaces(no_punct)
    if no_punct:
        add(no_punct)
        add(no_punct.lower())
        add(re.sub(r"\s+", "", no_punct))
        add(re.sub(r"\s+", "", no_punct).lower())

    add(raw.replace(".", " "))
    add(raw.replace(".", ""))
    add(raw.replace("_", " "))
    add(raw.replace("_", ""))

    for stripped in _apply_suffix_strips(raw):
        add(stripped)
        add(stripped.lower())
        sp = re.sub(r"[^\w\s]", " ", stripped, flags=re.UNICODE)
        sp = _squeeze_spaces(sp)
        if sp:
            add(sp)
            add(re.sub(r"\s+", "", sp))

    for inner in re.findall(r"\(([^)]+)\)", raw):
        add(inner.strip())
        add(re.sub(r"[^\w\s]", " ", inner, flags=re.UNICODE).strip())

    tokens = _tokens(raw)
    for token in tokens:
        add(token)
        add(token.lower())
        add(re.sub(r"[^\w]", "", token))
    if len(tokens) >= 2:
        add(" ".join(tokens[:2]))
        add("".join(tokens))
        add("".join(tokens).lower())
        add(tokens[0])
        if len(tokens) >= 2:
            add(tokens[-1])
    elif len(tokens) == 1 and len(tokens[0]) >= 4:
        # Long single token e.g. FSSTORE23 → try split alpha/num boundaries
        parts = re.findall(r"[A-Za-z]+|\d+", tokens[0])
        for part in parts:
            if len(part) >= 2:
                add(part)

    return ordered[: max(1, max_keywords)]
