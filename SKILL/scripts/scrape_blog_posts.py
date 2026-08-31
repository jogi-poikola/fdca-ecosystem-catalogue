#!/usr/bin/env python3
"""
Scrape FDCA member introduction blog posts.
Saves to JSON after every successful fetch — fault-tolerant by design.
"""

import json
import time
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "INPUT" / "fdca-member-registry.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FDCAResearchBot/1.0)"}
DELAY = 0.5  # seconds between requests — polite but not slow


def extract_blog_text(html: str, url: str) -> str:
    """Extract the main article body text from an FDCA blog post."""
    soup = BeautifulSoup(html, "html.parser")

    # Try common WordPress article content selectors, most specific first
    selectors = [
        "article .entry-content",
        "article .post-content",
        ".entry-content",
        ".post-content",
        "article",
        "main",
    ]

    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            # Remove nav, footer, sidebar noise
            for tag in el.select("nav, footer, .sidebar, .widget, .sharedaddy, "
                                  ".jp-relatedposts, .post-navigation, script, style"):
                tag.decompose()
            text = el.get_text(separator="\n", strip=True)
            # Strip very short results (probably wrong element)
            if len(text) > 80:
                return text

    # No fallback to the whole <body>. That returned the navigation, the
    # cookie banner and the footer as if they were the article, and the
    # result is written straight into blog_content, which the catalogue
    # shows as the member's description. Failing here is the honest answer.
    return "[content extraction failed]"


def scrape(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 404:
            return "[page not found]"
        if r.status_code != 200:
            return f"[HTTP {r.status_code}]"
        return extract_blog_text(r.text, url)
    except requests.RequestException as e:
        return f"[fetch error: {e}]"


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        members = json.load(f)

    # A stored error marker is retried. The previous rule — scrape only where
    # blog_content is empty — meant one timeout or one 502 froze that member's
    # description permanently, because the marker itself counted as content.
    to_scrape = [
        m for m in members
        if m.get("blog_link")
        and (not m.get("blog_content") or m["blog_content"].startswith("["))
    ]

    print(f"Found {len(to_scrape)} members to scrape.\n")

    not_found = 0
    errors = 0
    scraped = 0

    for idx, member in enumerate(to_scrape):
        name = member["display_name"]
        url = member["blog_link"]
        print(f"[{idx+1}/{len(to_scrape)}] {name} — {url}")

        content = scrape(url)

        if content == "[page not found]":
            not_found += 1
            print("  -> PAGE NOT FOUND")
        elif content.startswith("["):
            errors += 1
            print(f"  -> ERROR: {content}")
        else:
            scraped += 1
            preview = content[:80].replace("\n", " ")
            print(f"  -> OK ({len(content)} chars): {preview}…")

        # Write content even for not-found, so the next run does not retry it.
        member["blog_content"] = content

        # CHECKPOINT: save after every single member.
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(members, f, ensure_ascii=False, indent=2)
            f.write("\n")

        if idx < len(to_scrape) - 1:
            time.sleep(DELAY)

    total_with_content = sum(
        1 for m in members
        if m.get("blog_link") and m.get("blog_content")
        and not m["blog_content"].startswith("[")
    )

    print(f"\n{'='*50}")
    print("Done.")
    print(f"  Scraped successfully : {scraped}")
    print(f"  Page not found       : {not_found}")
    print(f"  Errors               : {errors}")
    print(f"  Members with content : {total_with_content}")
    stuck = [
        m["display_name"] for m in members
        if m.get("blog_content") and m["blog_content"].startswith("[")
    ]
    if stuck:
        print(f"\n{len(stuck)} still hold an error marker instead of text:")
        for name in stuck:
            print(f"  {name}")


if __name__ == "__main__":
    main()
