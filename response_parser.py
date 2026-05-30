"""Parse formatted assistant replies into structured fields."""

from __future__ import annotations

import re


def parse_assistant_reply(text: str) -> dict[str, str | list[str]]:
    """Split Answer / Key Points / Sources from Claude formatted text."""
    cleaned = text.strip()
    answer = ""
    key_points: list[str] = []
    sources_text = ""

    answer_match = re.search(
        r"Answer:\s*\n(.*?)(?=\nKey Points:|\Z)",
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    if answer_match:
        answer = answer_match.group(1).strip()

    kp_match = re.search(
        r"Key Points:\s*\n(.*?)(?=\nSources:|\Z)",
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    if kp_match:
        for line in kp_match.group(1).splitlines():
            line = line.strip()
            if line.startswith(("-", "•", "*")):
                point = re.sub(r"^[-•*]\s*", "", line).strip()
                if point and point not in key_points:
                    key_points.append(point)

    src_match = re.search(r"Sources:\s*\n(.*)", cleaned, re.DOTALL | re.IGNORECASE)
    if src_match:
        sources_text = src_match.group(1).strip()

    if not answer and not key_points:
        answer = cleaned

    return {
        "answer": answer,
        "key_points": key_points,
        "sources_text": sources_text,
    }
