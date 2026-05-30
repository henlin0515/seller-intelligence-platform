"""Orchestrates search + Claude for terminal and web (no logic duplication)."""

from __future__ import annotations

import asyncio

from claude_client import generate_search_keywords, summarize_answer
from query_mode import resolve_search_plan
from response_parser import parse_assistant_reply
from search import search_edu_articles


def _sources_for_api(fetched: list[dict]) -> list[dict]:
    items = []
    for source in fetched:
        url = source.get("url", "").strip()
        if not url:
            continue
        items.append(
            {
                "title": source.get("title", "Untitled"),
                "url": url,
                "type": source.get("source_type", "article"),
            }
        )
    return items


async def process_question(question: str) -> dict:
    """
    Run full assistant pipeline.
    Returns answer, key_points, sources, formatted (full text), mode.
    """
    question = question.strip()
    if not question:
        raise ValueError("Question is required")

    plan = resolve_search_plan(question)
    keywords = await asyncio.to_thread(generate_search_keywords, question)
    fetched_sources, strong_match = await search_edu_articles(question, keywords, plan=plan)
    formatted = await asyncio.to_thread(
        summarize_answer, question, fetched_sources, strong_match
    )
    parsed = parse_assistant_reply(formatted)

    return {
        "answer": str(parsed["answer"]),
        "key_points": list(parsed["key_points"]),
        "sources": _sources_for_api(fetched_sources),
        "formatted": formatted,
        "mode": plan.get("mode", "simple"),
    }


def process_question_sync(question: str) -> dict:
    """Sync entry point for terminal_bot (no running asyncio loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(process_question(question))

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, process_question(question))
        return future.result()
