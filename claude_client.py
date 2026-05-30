import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

from program_dictionary import dictionary_prompt_reference, expand_search_keywords

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
DEBUG = os.getenv("DEBUG", "0") == "1"
CLAUDE_TIMEOUT_SEC = float(os.getenv("CLAUDE_TIMEOUT_SEC", "30"))

ASSISTANT_PROCESS = """
1. Search and read all relevant Seller Education sources (already provided below).
2. Merge information from all sources.
3. Remove duplicate information.
4. Resolve conflicts using the latest / most specific source.
5. Extract only what is useful for the seller.
6. Rewrite in natural, seller-friendly language.
"""


_client_instance: Anthropic | None = None


def _client() -> Anthropic:
    global _client_instance
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    if _client_instance is None:
        _client_instance = Anthropic(
            api_key=ANTHROPIC_API_KEY,
            timeout=CLAUDE_TIMEOUT_SEC,
        )
    return _client_instance


def _debug(message: str) -> None:
    if DEBUG:
        print(f"[debug] {message}")


def detect_response_language(question: str) -> str:
    """Match seller input: Traditional Chinese if question contains Chinese, else English."""
    if re.search(r"[\u4e00-\u9fff]", question):
        return "zh-TW"
    return "en"


def _language_instruction(lang: str) -> str:
    if lang == "zh-TW":
        return (
            "LANGUAGE: The seller asked in Chinese. Write the entire reply in Traditional Chinese "
            "(繁體中文) — Answer paragraph, every Key Point bullet, and source titles if translated. "
            "Keep section headers exactly as: Answer, Key Points, Sources. Do not reply in English."
        )
    return (
        "LANGUAGE: The seller asked in English. Write the entire reply in English. "
        "Keep section headers exactly as: Answer, Key Points, Sources. Do not reply in Chinese."
    )


def _empty_response(lang: str) -> str:
    if lang == "zh-TW":
        return (
            "Answer:\n"
            "目前找不到相關的 Seller Education 內容。請改用官方方案名稱再問一次（例如 MDV 或 FBS）。\n\n"
            "Key Points:\n"
            "- 說明你想了解的操作（加入、退出、費用、資格）。\n\n"
            "Sources:\n"
            "(none)"
        )
    return (
        "Answer:\n"
        "I couldn't find Seller Education content for this yet. Try asking again with the "
        "official program name (for example MDV or FBS) so I can look up the right guides.\n\n"
        "Key Points:\n"
        "- Mention what you want to do (join, exit, fees, eligibility).\n\n"
        "Sources:\n"
        "(none)"
    )


def generate_search_keywords(question: str) -> list[str]:
    """Generate broad Seller Education search terms for RM-style platform research."""
    program_ref = dictionary_prompt_reference()
    prompt = f"""You are a senior Shopee Philippines Relationship Manager preparing to research the Seller Education Hub.

Generate exactly 6 to 10 search keywords/phrases for the Seller Education site search.

INTERNAL program dictionary (for query understanding only — do NOT include these definitions in seller-facing text):
{program_ref}

When a seller uses an abbreviation OR full program name, treat them as the same topic.
If the question mentions an acronym, include both the acronym and full name in your keyword list when helpful.

Cover: process, fees, eligibility, exit, restrictions, Seller Centre terms.

Seller question:
{question}

Reply with ONLY a JSON array of strings, no markdown."""

    response = _client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    _debug(f"keyword response: {text}")

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("Claude did not return a JSON keyword array.")
    keywords = json.loads(match.group())
    if not isinstance(keywords, list) or len(keywords) < 5:
        raise ValueError(f"Expected at least 5 keywords, got {len(keywords) if isinstance(keywords, list) else 'invalid'}")
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]
    expanded = expand_search_keywords(cleaned, question)
    _debug(f"expanded search keywords: {', '.join(expanded)}")
    return expanded


def summarize_answer(
    question: str,
    articles: list[dict],
    exact_match: bool,
) -> str:
    """Compose a seller-friendly answer from merged Seller Education sources."""
    lang = detect_response_language(question)
    _debug(f"response language: {lang}")

    if not articles:
        return _empty_response(lang)

    context_parts = []
    for i, source in enumerate(articles, 1):
        body = source.get("content", "")
        label = "relevant excerpt" if source.get("excerpt") else "content"
        context_parts.append(
            f"--- Source {i} ({source.get('source_type', 'article')}) ---\n"
            f"Title: {source.get('title', 'Untitled')}\n"
            f"URL: {source.get('url', '')}\n"
            f"{label} ({len(body)} chars):\n{body}\n"
        )
    context = "\n".join(context_parts)

    coverage_note = (
        "Multiple Seller Education sources were retrieved and appear to cover this topic."
        if exact_match
        else "Sources are partially relevant; synthesize carefully and note gaps."
    )

    language_rule = _language_instruction(lang)

    prompt = f"""You are a Shopee Seller AI Assistant for Philippines sellers.

Your job is NOT to summarize Seller Education articles.
Your job is to help sellers understand Shopee programs and policies.

{language_rule}

Seller question:
{question}

{coverage_note}

You have {len(articles)} sources below. Read ALL of them before writing.

PROCESS:
{ASSISTANT_PROCESS}

ANSWER STYLE:
- Friendly, professional, easy to understand
- Like an experienced Shopee RM explaining to a seller in chat
- The Answer is the primary focus; Key Points are supporting only

DO NOT:
- Summarize articles section by section
- Explain article structure
- Mention Product Tabs, Module Tabs, or Navigation Tabs unless the seller must use them
- Copy article wording directly
- Dump all article content into the reply
- List or explain the internal program dictionary unless the seller asks what an acronym means

Use ONLY facts from the sources. Do not invent fees, dates, or rules. If something is missing, say so briefly in the Answer.

SOURCES:
{context}

OUTPUT — follow EXACTLY (plain text, no extra sections or markdown):

Answer:
<A short seller-friendly explanation in paragraph form. This is the main reply — clear, direct, and complete enough to act on. No bullet lists here.>

Key Points:
- <important supporting point>
(maximum 5-6 bullets; only the most important points; do not repeat the Answer; no duplicates)

Sources:
- <article title> — <url>
(one line per source you used; list all sources you relied on)

If sources are insufficient, use the same three sections. Keep the Answer as one short paragraph.

Reminder: Match the seller's question language in all reply text (see LANGUAGE rule above)."""

    response = _client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
