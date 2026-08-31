#!/usr/bin/env python3
"""
Fill in member homepages, descriptions, and category proposals.

The registry may contain roster members or website-only entries that have no
homepage, no description, or no sanctioned category. This script closes those
gaps in three steps, deliberately separated so the machine does the fetching
and a human or an agent does the judging.

    --research   find a url and a description for each member missing one.
                 Tries the obvious domains first, concurrently and for free,
                 and only falls back to a Firecrawl search when that misses.
                 Whatever it finds is written as `url_status: unverified`.
    --review     write website-review.json: every unverified url with the
                 page's own <title>, for an agent to check.
    --confirm    apply those verdicts. `ok` confirms, `wrong` clears the url
                 and remembers it so no later run proposes it again, `none`
                 records that the company has no website.
    --propose    write OUTPUT/category-proposals.json: one row per
                 uncategorised member, carrying the evidence gathered above
                 and an empty category for someone to fill in.
    --apply      read that file back, check every value against
                 INPUT/fdca-categories.json, and write it into the registry.

Nothing here is trusted because a machine produced it. A guessed url is
`unverified` until an agent says otherwise, and a confirmed or human-set value
is never overwritten by a later run — a research pass once silently restored
the European Parliament's STOA page over a correction already made by hand.

Why the split. Classifying a company, and judging whether a url really belongs
to it, are both judgment, and this machine has no model to do them with — the only credential on it is for Linear. A keyword
classifier would be the alternative, and it would invent exactly the kind of
wrong-but-plausible category that took a full clean-up pass to remove. So the
research is automated, the judgment is not, and --apply refuses anything the
taxonomy does not sanction.

Every field this script writes is marked `researched: firecrawl-<date>`, so a
description a search engine wrote is never mistaken for one FDCA published.

Usage:
    python3 SKILL/scripts/enrich_members.py --research [--limit N]
    python3 SKILL/scripts/enrich_members.py --propose
    python3 SKILL/scripts/enrich_members.py --apply [--check]
"""

import argparse
import concurrent.futures
import datetime
import json
import re
import requests
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
TAXONOMY_PATH = INPUT_DIR / "fdca-categories.json"
PROPOSALS_PATH = OUTPUT_DIR / "category-proposals.json"
REVIEW_PATH = OUTPUT_DIR / "website-review.json"

UNCLASSIFIED = "uncategorised"

# Firecrawl throttles a fast loop. These were tuned against a real run that
# hit HTTP 429 on its last 49 members.
# `researched` records who established a member's url and description. Only
# these prefixes are this script's own; anything else was set by a person and
# is never overwritten. Without this rule a research re-run silently restored
# the European Parliament's STOA page over a correction Antti had made, and
# a stealth-mode company with no website can never be recorded as having none.
AUTOMATED_MARKS = ("firecrawl-", "domain-check-")

# A url this script found is a guess until an agent has looked at it. The
# guesses that got through unchecked were not subtle — a singer's homepage for
# "Tate", the European Parliament for "Stoa Technologies", UK Companies House
# for half a run — and each one reads as a fact once it is in the JSON. So a
# machine-found url is written as `unverified` and only an explicit verdict
# promotes it.
URL_UNVERIFIED = "unverified"
URL_CONFIRMED = "confirmed"
URL_NONE = "none"  # checked, and the company genuinely has no website

SEARCH_DELAY = 2.0
RATE_LIMIT_WAIT = 20.0
RATE_LIMIT_RETRIES = 3

# A search result on one of these is about the company but is not the company,
# so it never becomes the member's own url.
HOMEPAGE_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# Words that are not part of a company's domain.
DOMAIN_NOISE = {"oy", "oyj", "ab", "ltd", "limited", "plc", "inc", "corp",
                "corporation", "gmbh", "bv", "as", "finland", "suomi", "group"}


def norm_words(name: str) -> list:
    folded = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "å": "a", "ü": "u"}))
    return [w for w in re.sub(r"[^a-z0-9]+", " ", folded).split() if w]


NOT_A_HOMEPAGE = (
    "linkedin.com", "facebook.com", "wikipedia.org", "youtube.com", "x.com",
    "twitter.com", "instagram.com", "bloomberg.com", "crunchbase.com",
    "finder.fi", "asiakastieto.fi", "vainu.io", "yritystiedot.fi",
    # Company registries describe the company but are not its own site.
    "company-information.service.gov.uk", "companieshouse.gov.uk", "ytj.fi",
    "kauppalehti.fi", "taloussanomat.fi", "dnb.com", "opencorporates.com",
)


def name_tokens(name: str) -> list:
    """The words of a name that a company's own domain is likely to contain."""
    words = re.sub(r"[^a-z0-9]+", " ", name.lower()
                   .translate(str.maketrans({"ä": "a", "ö": "o", "å": "a"}))).split()
    noise = {"oy", "oyj", "ab", "ltd", "limited", "plc", "inc", "corp", "gmbh",
             "bv", "as", "the", "of", "group", "company", "finland", "suomi"}
    return [w for w in words if w not in noise and len(w) > 2] or words


def pick_homepage(results: list, name: str) -> dict:
    """The result most likely to be the company's own site.

    A domain carrying the company's own name is the strongest signal there is,
    and it is what separates meka.eu from a YouTube channel about Meka Pro.
    """
    usable = [r for r in results if not any(x in r.get("url", "") for x in NOT_A_HOMEPAGE)]
    if not usable:
        return None
    tokens = name_tokens(name)
    for result in usable:
        domain = result.get("url", "").split("/")[2].lower() if "//" in result.get("url", "") else ""
        if any(token in domain.replace("-", "") for token in tokens):
            return result
    return usable[0]


def today() -> str:
    return datetime.date.today().isoformat()


def load_registry() -> list:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(members: list) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_taxonomy() -> dict:
    data = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {c["slug"]: {s["slug"] for s in c["subcategories"]} for c in data["categories"]}


def search(query: str) -> tuple:
    """Firecrawl web search. Returns (results, reason).

    The CLI exits 0 even when the API refuses, so the exit code says nothing
    and the output has to be read. That mattered: a first full run reported
    "no result" for 49 members that were really HTTP 429, and a rate limit
    reported as an empty web is the kind of silent failure that looks like an
    answer. So a throttle is retried with a growing wait, and whatever is
    still wrong at the end is named.
    """
    wait = RATE_LIMIT_WAIT
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            done = subprocess.run(
                ["firecrawl", "search", query, "--limit", "4", "--json"],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return [], "timed out"
        except FileNotFoundError:
            raise SystemExit("firecrawl CLI not found — install it and run `firecrawl --status`")

        output = (done.stdout or "") + (done.stderr or "")
        if "429" in output:
            if attempt == RATE_LIMIT_RETRIES:
                return [], "rate limited"
            time.sleep(wait)
            wait *= 2
            continue
        try:
            return json.loads(done.stdout).get("data", {}).get("web", []) or [], "ok"
        except json.JSONDecodeError:
            reason = output.strip().splitlines()[0] if output.strip() else "no output"
            return [], reason[:80]
    return [], "rate limited"


def human_checked(member: dict) -> bool:
    """True when a person or an agent, not this script, settled these fields."""
    if member.get("url_status") in (URL_CONFIRMED, URL_NONE):
        return True
    mark = member.get("researched")
    return bool(mark) and not mark.startswith(AUTOMATED_MARKS)


def page_title(url: str) -> str:
    """The page's <title>, which is the quickest evidence of whose site it is."""
    try:
        r = requests.get(url, timeout=10, allow_redirects=True,
                         headers={"User-Agent": HOMEPAGE_AGENT})
    except requests.RequestException as error:
        return f"[unreachable: {type(error).__name__}]"
    if r.status_code != 200:
        return f"[HTTP {r.status_code}]"
    match = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip()[:120] if match else "[no title]"


def review(members: list) -> None:
    """Write the queue of machine-found urls for an agent to check."""
    todo = [
        m for m in members
        if m.get("url") and m.get("url_status", URL_UNVERIFIED) == URL_UNVERIFIED
    ]
    print(f"fetching titles for {len(todo)} unverified urls …")
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        titles = list(pool.map(lambda m: page_title(m["url"]), todo))

    rows = [
        {
            "official_name": m.get("official_name"),
            "display_name": m["display_name"],
            "url": m["url"],
            "page_title": title,
            "description": (m.get("web_search_content") or "")[:200],
            "found_by": m.get("researched"),
            "verdict": "",
        }
        for m, title in zip(todo, titles)
    ]
    rows.sort(key=lambda r: r["display_name"].lower())
    REVIEW_PATH.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {REVIEW_PATH.name} — {len(rows)} urls to check")
    print("\nSet each `verdict` to:")
    print("  ok      the url really is this company's own site")
    print("          (edit the row's `url` first to fix a wrong path)")
    print("  wrong   it is some other company — the url is cleared and never retried")
    print("  none    this company has no website (stealth, or none exists)")
    print("\nthen run: python3 enrich_members.py --confirm")


def confirm(members: list, check: bool) -> None:
    """Apply the agent's verdicts from the review queue."""
    if not REVIEW_PATH.exists():
        raise SystemExit(f"{REVIEW_PATH.name} not found — run --review first")
    rows = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    by_name = {m["display_name"]: m for m in members}

    counts = {"ok": 0, "wrong": 0, "none": 0}
    blank, bad = 0, []
    for row in rows:
        verdict = (row.get("verdict") or "").strip().lower()
        member = by_name.get(row["display_name"])
        if member is None:
            bad.append((row["display_name"], "no member with this display_name"))
            continue
        if not verdict:
            blank += 1
        elif verdict == "ok":
            # The reviewer may fix the url in the row rather than reject it —
            # ksb.com/fi returned 404 while ksb.com/fi-fi was the real page,
            # and rejecting that would have thrown away a correct company for
            # a wrong path.
            if row.get("url") and row["url"] != member.get("url"):
                print(f"  corrected {row['display_name']}: {member.get('url')} -> {row['url']}")
                member["url"] = row["url"]
            member["url_status"] = URL_CONFIRMED
            counts["ok"] += 1
        elif verdict == "wrong":
            # Remember the rejection, so a later run cannot propose it again.
            rejected = member.get("rejected_urls") or []
            if member.get("url") and member["url"] not in rejected:
                rejected.append(member["url"])
            member["rejected_urls"] = rejected
            member["url"] = None
            member["url_status"] = URL_UNVERIFIED
            member.pop("researched", None)
            counts["wrong"] += 1
        elif verdict == "none":
            member["url"], member["url_status"] = None, URL_NONE
            counts["none"] += 1
        else:
            bad.append((row["display_name"], f"unknown verdict {verdict!r}"))

    print(f"ok {counts['ok']}, wrong {counts['wrong']}, none {counts['none']}, "
          f"blank {blank}, rejected {len(bad)}")
    for name, why in bad:
        print(f"  REJECTED {name}: {why}")
    if bad:
        raise SystemExit("\nfix those rows; nothing written")
    if check:
        print("\n--check: nothing written")
        return
    save_registry(members)
    print(f"\nwrote {REGISTRY_PATH.name}")


def domain_candidates(name: str) -> list:
    """The URLs a company of this name plausibly lives at."""
    words = [w for w in norm_words(name) if w not in DOMAIN_NOISE] or norm_words(name)
    if not words:
        return []
    urls = []
    for slug in dict.fromkeys(["".join(words), words[0], "-".join(words)]):
        for tld in (".fi", ".com", ".net"):
            urls += [f"https://www.{slug}{tld}", f"https://{slug}{tld}"]
    return urls


def domain_guess(name: str) -> str:
    """The company's own site, found by trying the obvious domains.

    Most members are `<name>.fi`. Checking that directly is free and takes a
    second, where a Firecrawl search is rate-limited to roughly eight members
    per ten minutes and costs credits — a full run of 71 members spent most of
    an hour backing off from HTTP 429 and filled 22. The candidates are probed
    concurrently, so the whole guess costs about as long as its slowest single
    request rather than the sum of all of them.

    A search is still the fallback, because a name like "Visio
    Henkilostoratkaisut Oy" lives at visiohr.fi and no rule reaches that. It
    is just no longer the first move.
    """
    candidates = domain_candidates(name)
    if not candidates:
        return None
    token = ([w for w in norm_words(name) if w not in DOMAIN_NOISE] or norm_words(name))[0]

    def fetch(url):
        try:
            r = requests.get(url, timeout=8, allow_redirects=True,
                             headers={"User-Agent": HOMEPAGE_AGENT})
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        # The domain must actually be this company's, not a squatter's or a
        # same-named business elsewhere. This is a coarse filter, not proof —
        # --review is where an agent settles it.
        haystack = (r.url + r.text[:8000]).lower().replace(" ", "")
        return r.url if token[:5] in haystack else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for hit in pool.map(fetch, candidates):
            if hit:
                return hit
    return None


def research(members: list, limit: int) -> None:
    """Fill url and web_search_content for members that have neither."""
    todo = [
        m for m in members
        if not human_checked(m)
        and (not m.get("url") or not (m.get("web_search_content") or m.get("blog_content")))
    ]
    if limit:
        todo = todo[:limit]
    print(f"researching {len(todo)} members\n")

    stamp = f"firecrawl-{today()}"
    filled, failed = 0, []
    for index, member in enumerate(todo, 1):
        name = member.get("official_name") or member["display_name"]
        print(f"[{index}/{len(todo)}] {name} …", end=" ", flush=True)

        # Free and instant; only pay for a search when this fails.
        rejected = set(member.get("rejected_urls") or [])
        if not member.get("url"):
            guessed = domain_guess(name)
            if guessed in rejected:
                guessed = None
            if guessed:
                member["url"] = guessed
                member["url_status"] = URL_UNVERIFIED
                member["researched"] = f"domain-check-{today()}"
                filled += 1
                print(f"-> {guessed} (domain)")
                save_registry(members)
                continue

        results, reason = search(f"{name} official website")
        if not results:
            print(reason)
            failed.append((name, reason))
            time.sleep(SEARCH_DELAY)
            continue

        homepage = pick_homepage(results, name)
        if homepage and homepage["url"] in rejected:
            homepage = None
        if not member.get("url") and homepage:
            member["url"] = homepage["url"]
            member["url_status"] = URL_UNVERIFIED
        if not member.get("web_search_content"):
            best = homepage or results[0]
            text = " ".join(part for part in (best.get("title"), best.get("description")) if part)
            member["web_search_content"] = text.strip() or None
        member["researched"] = stamp
        filled += 1
        print(f"-> {member.get('url')}")

        # Checkpoint after every member: a search run is slow and interruptible.
        save_registry(members)
        time.sleep(SEARCH_DELAY)

    print(f"\nfilled {filled} members, wrote {REGISTRY_PATH.name}")
    if failed:
        print(f"{len(failed)} returned nothing:")
        for name, reason in failed:
            print(f"  {name}: {reason}")
        print("\nRe-run --research to retry only these; members already filled are skipped.")


def propose(members: list) -> None:
    """Write the queue of members still needing a category, with the evidence."""
    rows = [
        {
            "official_name": m["official_name"],
            "display_name": m["display_name"],
            "url": m.get("url"),
            "evidence": (m.get("web_search_content") or m.get("blog_content") or "")[:400],
            "category": "",
            "subcategory": "",
        }
        for m in members
        if m.get("category") == UNCLASSIFIED
    ]
    rows.sort(key=lambda r: r["display_name"].lower())
    OUTPUT_DIR.mkdir(exist_ok=True)
    PROPOSALS_PATH.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    without = sum(1 for r in rows if not r["evidence"])
    print(f"wrote {PROPOSALS_PATH.name} — {len(rows)} members to classify")
    print(f"{without} of them still have no evidence; run --research first")
    print("\nFill in `category` (and `subcategory` where the taxonomy has one),")
    print("then run: python3 SKILL/scripts/enrich_members.py --apply")


def apply(members: list, check: bool) -> None:
    """Read the filled proposals back, validate, and write them in."""
    if not PROPOSALS_PATH.exists():
        raise SystemExit(f"{PROPOSALS_PATH.name} not found — run --propose first")
    allowed = load_taxonomy()
    rows = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
    by_official = {m["official_name"]: m for m in members}

    applied, skipped, bad = [], 0, []
    for row in rows:
        category = (row.get("category") or "").strip()
        subcategory = (row.get("subcategory") or "").strip()
        if not category:
            skipped += 1
            continue
        member = by_official.get(row["official_name"])
        if member is None:
            bad.append((row["official_name"], "no member with this official_name"))
        elif category not in allowed:
            bad.append((row["official_name"], f"category {category!r} not in the taxonomy"))
        elif subcategory and subcategory not in allowed[category]:
            bad.append((row["official_name"], f"subcategory {subcategory!r} not under {category}"))
        else:
            applied.append((member, category, subcategory))

    print(f"{len(applied)} ready, {skipped} still blank, {len(bad)} rejected")
    for name, why in bad:
        print(f"  REJECTED {name}: {why}")
    if bad:
        raise SystemExit("\nfix the rejected rows; nothing written")
    for member, category, subcategory in applied:
        member["category"], member["subcategory"] = category, subcategory
    for member, category, subcategory in applied:
        label = f"{category}/{subcategory}" if subcategory else category
        print(f"  {member['display_name']:34s} -> {label}")

    if check:
        print("\n--check: nothing written")
        return
    save_registry(members)
    print(f"\nwrote {REGISTRY_PATH.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--research", action="store_true", help="web-search missing members")
    mode.add_argument("--propose", action="store_true", help="write the classification queue")
    mode.add_argument("--apply", action="store_true", help="apply the filled queue")
    mode.add_argument("--review", action="store_true", help="queue machine-found urls for checking")
    mode.add_argument("--confirm", action="store_true", help="apply the checked urls")
    parser.add_argument("--limit", type=int, default=0, help="research at most N members")
    parser.add_argument("--check", action="store_true", help="with --apply: write nothing")
    args = parser.parse_args()

    members = load_registry()
    if args.research:
        research(members, args.limit)
    elif args.propose:
        propose(members)
    elif args.review:
        review(members)
    elif args.confirm:
        confirm(members, args.check)
    else:
        apply(members, args.check)


if __name__ == "__main__":
    main()
