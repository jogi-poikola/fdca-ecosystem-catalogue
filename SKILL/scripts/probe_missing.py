#!/usr/bin/env python3
"""
Find the FDCA "introducing our new member" post for members that have no
`blog_link` yet, by reading fdca.fi's own sitemap.

This script used to guess URLs — up to eight slug spellings per member, each
one a request, thousands of requests for a full run. Measured against the 176
posts the registry already knew, that guessing reproduced 141 (80%). It could
never find `introducing-our-new-member-csc-it-center-for-science-ltd` from the
name "CSC", because no slug rule expands an acronym.

The sitemap gives the whole answer in two requests. fdca.fi runs Yoast, which
publishes /sitemap_index.xml -> /post-sitemap.xml, and that lists every post
URL. So the work is now local: fetch the list once, then match names to slugs
in memory, where a thorough matcher costs nothing.

Matching is deliberately conservative. A post is assigned only when exactly
one member claims it. Every post no member claims, and every ambiguous one,
is reported rather than guessed — an unclaimed post is usually a former member
or a name the registry spells differently, and that is a human's call.

Usage:
    python3 SKILL/scripts/probe_missing.py [--check]

--check reports what would change and writes nothing.
"""

import argparse
import json
import re
from pathlib import Path

import requests

# Resolved against this file, not the shell's working directory.
ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "INPUT" / "fdca-member-registry.json"
SITEMAP_INDEX = "https://www.fdca.fi/sitemap_index.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FDCAResearchBot/1.0)"}
TIMEOUT = 30

# Both spellings FDCA has used for a member introduction post. The second is
# rare — 4 posts against 205 — but it costs nothing to read from the sitemap.
POST_PREFIXES = ("introducing-our-new-member-", "welcome-our-new-member-")

# Slug-level transliteration. Stripping these letters instead of folding them
# is what used to turn "Metsähallitus" into "metshallitus" and miss the post.
FOLD = str.maketrans({"ä": "a", "ö": "o", "å": "a", "ü": "u", "é": "e", "ø": "o", "æ": "a"})

# Words that carry no identity, so a slug often drops them.
NOISE = {
    "oy", "oyj", "ab", "ltd", "limited", "plc", "inc", "corp", "corporation",
    "gmbh", "bv", "as", "a", "s", "the", "of", "city", "group", "company",
    "finland", "suomi", "nordic", "nordics", "europe", "international",
}


def norm(text: str) -> list:
    """A name or a slug reduced to its comparable word list."""
    text = text.lower().translate(FOLD)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [w for w in text.split() if w]


def keys(name: str) -> set:
    """Every compact form of a name a slug might plausibly use."""
    words = norm(name)
    if not words:
        return set()
    meaningful = [w for w in words if w not in NOISE] or words
    out = {
        "".join(words),           # everything, run together
        "".join(meaningful),      # without the noise words
        meaningful[0],            # the first real word alone
    }
    # A parenthesised acronym is often the whole slug: "… (KAMK)" -> "kamk".
    out |= {"".join(norm(part)) for part in re.findall(r"\((.*?)\)", name)}
    # Leading pairs, for names a slug truncates: "DLA Piper Finland" -> "dlapiper".
    for cut in range(2, len(meaningful)):
        out.add("".join(meaningful[:cut]))
    return {k for k in out if len(k) >= 2}


def fetch_post_urls() -> list:
    """Every member-introduction post URL fdca.fi publishes."""
    index = requests.get(SITEMAP_INDEX, headers=HEADERS, timeout=TIMEOUT)
    index.raise_for_status()
    maps = [u for u in re.findall(r"<loc>(.*?)</loc>", index.text) if "post-sitemap" in u]
    if not maps:
        raise SystemExit(f"no post sitemap listed in {SITEMAP_INDEX}")

    urls = []
    for sitemap in maps:
        page = requests.get(sitemap, headers=HEADERS, timeout=TIMEOUT)
        page.raise_for_status()
        urls += re.findall(r"<loc>(.*?)</loc>", page.text)
    return [u for u in urls if any(p in u for p in POST_PREFIXES)]


def slug_core(url: str) -> list:
    """The words of a post URL that name the company."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    for prefix in POST_PREFIXES:
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
            break
    # A slug carries the same noise a name does — "zauner-group" for Zauner
    # Mission Critical, "avesco-oy" for Avesco Oy — so drop it on both sides.
    words = norm(slug)
    return [w for w in words if w not in NOISE] or words


def member_names(member: dict) -> list:
    """Every name this member is known by, including the ones folded into it."""
    names = [member.get("display_name"), member.get("official_name")]
    names += member.get("folded_from") or []
    seen, out = set(), []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def canonical_words(name: str) -> list:
    """The name's meaningful words, in order — its one canonical form."""
    words = norm(name)
    return [w for w in words if w not in NOISE] or words


def claims(member: dict, core: list) -> bool:
    """True when this member's name accounts for that post slug's words.

    Two rules, both deliberately narrow. A looser prefix test — any key
    prefixing the slug in either direction — recovered three more posts and
    collided on eight, pairing DE-CIX with DECI, Nordec with Nordecon, and
    Signal Group with Signal Solutions. Precision matters more here, because
    a wrong link is silent while an unmatched post gets reported.
    """
    if not core:
        return False
    compact = "".join(core)
    for name in member_names(member):
        if compact in keys(name):
            return True
        # The slug may expand the name: "CSC" ->
        # "csc-it-center-for-science-ltd". Only the full canonical form may
        # match this way, and only word by word — comparing run-together
        # letters instead paired "ARE" with "areco-profiles" and "DECI Ltd"
        # with "decix", because neither prefix ended on a word boundary.
        canonical = canonical_words(name)
        if canonical and core[: len(canonical)] == canonical:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    members = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    print(f"reading {SITEMAP_INDEX} …")
    posts = fetch_post_urls()
    print(f"{len(posts)} member-introduction posts on fdca.fi\n")

    linked = {m["blog_link"].rstrip("/") for m in members if m.get("blog_link")}
    wanted = [m for m in members if not m.get("blog_link")]

    # A blog_link the sitemap does not list is a URL nothing published — the
    # earlier guessing probe could write one that never resolved.
    published = {u.rstrip("/") for u in posts}
    stale = sorted(
        m["display_name"] for m in members
        if m.get("blog_link") and m["blog_link"].rstrip("/") not in published
    )
    if stale:
        print(f"{len(stale)} members hold a blog_link the sitemap does not list:")
        for name in stale:
            print(f"  {name}")
        print()

    # Repair a stale link when exactly one live post claims that member. These
    # were all the same fault: the link says `introducing-our-new-member-…`
    # while FDCA published the post under `welcome-our-new-member-…`, so the
    # stored URL 404s and scrape_blog_posts.py can never fetch the text.
    # Same one-claimant rule as a new assignment — anything less certain is
    # left alone and reported above.
    repaired = []
    for member in members:
        link = (member.get("blog_link") or "").rstrip("/")
        if not link or link in published:
            continue
        hits = [u for u in posts if claims(member, slug_core(u))]
        if len(hits) == 1:
            repaired.append((member, link, hits[0]))
    if repaired:
        print(f"repairing {len(repaired)} of them — one live post each:")
        for member, was, now in repaired:
            print(f"  {member['display_name']}\n    {was}\n    -> {now}")
        print()

    found, ambiguous, unclaimed = [], [], []
    for url in posts:
        if url.rstrip("/") in linked:
            continue
        core = slug_core(url)
        hits = [m for m in wanted if claims(m, core)]
        if len(hits) == 1:
            found.append((hits[0], url))
        elif len(hits) > 1:
            ambiguous.append((url, [m["display_name"] for m in hits]))
        else:
            unclaimed.append(url)

    # One member must not collect two posts.
    counted = {}
    for member, url in found:
        counted.setdefault(id(member), []).append(url)
    doubled = [(m, u) for m, u in found if len(counted[id(m)]) > 1]
    found = [(m, u) for m, u in found if len(counted[id(m)]) == 1]

    print(f"matched {len(found)} posts to members with no blog_link:")
    for member, url in sorted(found, key=lambda x: x[0]["display_name"].lower()):
        print(f"  {member['display_name']:38s} {url}")

    for url, names in ambiguous:
        print(f"\nAMBIGUOUS — {url}\n    claimed by: {', '.join(names)}")
    for member, url in doubled:
        print(f"\nTWO POSTS — {member['display_name']} also matches {url}")

    print(f"\n{len(unclaimed)} posts no current member claims — former members,")
    print("or a name the registry spells differently:")
    for url in unclaimed:
        print(f"  {url}")

    if args.check:
        print("\n--check: nothing written")
        return
    for member, url in found:
        member["blog_link"] = url
    for member, _, url in repaired:
        member["blog_link"] = url
        # The old URL's 404 marker must go, or the scraper skips the new link.
        if (member.get("blog_content") or "").startswith("["):
            member["blog_content"] = None
    JSON_PATH.write_text(
        json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {len(found) + len(repaired)} blog_link fields to {JSON_PATH.name}")


if __name__ == "__main__":
    main()
