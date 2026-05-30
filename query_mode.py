"""Detect how many sources and how much content to use per question."""

from __future__ import annotations

import re

DETAIL_PHRASES = (
    "all details",
    "complete guide",
    "full policy",
)

POLICY_TOPIC_RE = re.compile(
    r"\b(policy|policies|fee|fees|eligibility|eligible|requirement|requirements|"
    r"restriction|restrictions|lock-?in|exit|penalty|penalties|charge|charges|"
    r"commission|withholding|prohibited|compliance)\b",
    re.I,
)


def wants_complete_guide(question: str) -> bool:
    q = question.lower()
    return any(phrase in q for phrase in DETAIL_PHRASES)


def is_policy_style_question(question: str) -> bool:
    return bool(POLICY_TOPIC_RE.search(question))


def resolve_search_plan(question: str) -> dict:
    """
    Returns max_sources, full_content, fast, label.
    - detailed: 10 sources, full article text
    - policy: 5 sources, excerpts
    - simple: 3 sources, excerpts (fast mode)
    """
    if wants_complete_guide(question):
        return {
            "max_sources": 10,
            "full_content": True,
            "fast": False,
            "mode": "detailed",
        }
    if is_policy_style_question(question):
        return {
            "max_sources": 5,
            "full_content": False,
            "fast": False,
            "mode": "policy",
        }
    return {
        "max_sources": 3,
        "full_content": False,
        "fast": True,
        "mode": "simple",
    }
