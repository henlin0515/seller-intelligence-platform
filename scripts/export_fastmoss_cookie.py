#!/usr/bin/env python3
"""Export FastMoss Cookie header for FASTMOSS_COOKIE / FASTMOSS_COOKIE_FILE.

Usage:
  # Headless guest cookies (limited; may not bypass Railway WAF)
  py -3 scripts/export_fastmoss_cookie.py

  # Open a real browser — log into FastMoss, then press Enter in the terminal
  py -3 scripts/export_fastmoss_cookie.py --login

Writes: credentials/fastmoss_cookie.txt (gitignored)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "credentials" / "fastmoss_cookie.txt"


def _cookie_header(cookies: list[dict]) -> str:
    keep = []
    for c in cookies:
        domain = (c.get("domain") or "").lstrip(".").lower()
        if domain.endswith("fastmoss.com"):
            keep.append(c)
    return "; ".join(f"{c['name']}={c['value']}" for c in keep if c.get("name"))


def export_cookies(*, login: bool) -> Path:
    from playwright.sync_api import sync_playwright

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        if login:
            browser = p.chromium.launch(headless=False, channel="msedge")
            context = browser.new_context(
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto("https://www.fastmoss.com/", wait_until="domcontentloaded", timeout=90_000)
            print(
                "Browser opened. Log into FastMoss in that window, then return here and press Enter.",
                flush=True,
            )
            try:
                input()
            except EOFError:
                page.wait_for_timeout(120_000)
            cookies = context.cookies()
            browser.close()
        else:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            page.goto("https://www.fastmoss.com/", wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            page.goto(
                "https://www.fastmoss.com/shop-marketing/detail/7494600626141628535",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            page.wait_for_timeout(2000)
            cookies = context.cookies()
            browser.close()

    header = _cookie_header(cookies)
    if not header:
        raise SystemExit("No fastmoss.com cookies captured.")
    OUT.write_text(header + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(header)} chars, {header.count('=')} entries)")
    return OUT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open Edge and wait until you finish logging in",
    )
    args = parser.parse_args()
    export_cookies(login=args.login)


if __name__ == "__main__":
    main()
