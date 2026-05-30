"""
Internal Shopee program dictionary for query understanding and search expansion only.
Not displayed to users unless they ask what an acronym means.
"""

from __future__ import annotations

import re

PROGRAM_DICTIONARY = {
    "MDV": "Mega Discount Voucher",
    "CCB": "Coins Cashback",
    "ATC": "Add To Cart Campaign",
    "LS": "Livestream",
    "FBS": "Fulfilled By Shopee",
    "SSPL": "Special SPayLater",
    "SLoan": "Shopee Loan",
    "Price Bidding": "Price Competitiveness Campaign",
    "Video": "Shopee Video",
    "Affiliate": "Shopee Affiliate Program",
}


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _build_lookup() -> dict[str, tuple[str, str]]:
    """Map any abbrev or full name (lowercase) to (abbrev, full_name) pair."""
    lookup: dict[str, tuple[str, str]] = {}
    for abbrev, full_name in PROGRAM_DICTIONARY.items():
        lookup[_normalize_key(abbrev)] = (abbrev, full_name)
        lookup[_normalize_key(full_name)] = (abbrev, full_name)
    return lookup


_LOOKUP = _build_lookup()


def dictionary_prompt_reference() -> str:
    """Compact reference for Claude keyword generation (internal use)."""
    return "\n".join(f"{abbrev} = {full_name}" for abbrev, full_name in PROGRAM_DICTIONARY.items())


def equivalents_for_text(text: str) -> set[str]:
    """Abbreviation and full name for any program detected in text."""
    if not text or not text.strip():
        return set()

    found: set[str] = set()
    lowered = text.lower()

    for abbrev, full_name in PROGRAM_DICTIONARY.items():
        for form in (abbrev, full_name):
            pattern = re.escape(form.lower())
            if re.search(rf"\b{pattern}\b", lowered) or form.lower() in lowered:
                found.add(abbrev)
                found.add(full_name)
                break

    return found


def expand_search_keywords(keywords: list[str], question: str = "") -> list[str]:
    """
    Expand search keywords: for each program, search both abbreviation and full name.
    Example: MDV → "MDV" and "Mega Discount Voucher"
    """
    result: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        cleaned = term.strip()
        if not cleaned:
            return
        key = _normalize_key(cleaned)
        if key in seen:
            return
        seen.add(key)
        result.append(cleaned)

    texts = list(keywords)
    if question.strip():
        texts.append(question)

    for text in texts:
        add(text)
        for term in equivalents_for_text(text):
            add(term)
        pair = _LOOKUP.get(_normalize_key(text))
        if pair:
            add(pair[0])
            add(pair[1])

    return result


def relevance_phrases(question: str, keywords: list[str]) -> list[str]:
    """Phrases to match in article titles/content (abbrev + full name)."""
    phrases: set[str] = set()
    for text in [question, *keywords]:
        phrases.update(equivalents_for_text(text))
    return [p for p in phrases if len(p) >= 2]
