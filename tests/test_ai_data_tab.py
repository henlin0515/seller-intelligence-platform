"""Tests for AI data tab resolution."""

from __future__ import annotations

from seller.google_sheets.ai_data_layout import resolve_ai_data_tab_title


def test_resolve_ai_data_tab_title_matches_case_variants():
    titles = ["shpoee link", "AI data", "Other"]
    assert resolve_ai_data_tab_title(titles) == "AI data"


def test_resolve_ai_data_tab_title_matches_uppercase():
    titles = ["AI DATA", "Notes"]
    assert resolve_ai_data_tab_title(titles) == "AI DATA"
