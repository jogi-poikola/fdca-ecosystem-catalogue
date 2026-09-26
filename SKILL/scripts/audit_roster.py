#!/usr/bin/env python3
"""
Audit every place where the dated roster and the catalogue disagree.

A registry entry that no roster line names is either a former member, a
company the roster lists under another name, or a member the roster forgot.
This script gathers the evidence a person needs to tell those apart, so the
question is not re-researched by hand each time a new roster arrives.

For each entry that matches no roster line it checks:

- the live fdca.fi members page: is a logo there that claims the entry?
- the roster's own companies: does one of them look like the same company?
  A strong hint is a shared homepage word or a similar name. A weak hint is
  only a mention in a description; the report leaves it out, the JSON keeps it.
- the entry's current status: already marked `former`, or still pending?

Each entry then gets one verdict:

    alias-candidate   a roster company looks like the same company. Add a
                      pair to ALIASES in merge_member_list.py, and to
                      DISPLAY_PRIMARY when the website brand should show.
    still-listed      not on the roster, but its logo is on the members page.
                      Ask FDCA's office; it may be a member the roster missed.
    likely-former     not on the roster and not on the members page. Add it
                      to FORMER_NOTES in merge_member_list.py once you agree.
    unknown           no live evidence, because the page could not be read or
                      --offline was given.
    reinstate?        marked `former`, but the roster or the members page
                      lists it now. Remove it from FORMER_NOTES.

The script also lists logos on the members page that no registry entry claims:
a new member the registry has not scraped, or a name the registry spells
differently.

The script writes nothing to the registry and edits no table. A person makes
each decision and writes it into merge_member_list.py, and the merge script
applies it. Nothing here is ever deleted.

Usage:
    python3 SKILL/scripts/audit_roster.py [--offline] [--strict] [--json PATH]

--offline   skip fdca.fi; only the roster and the registry are compared
--strict    exit 1 while any entry is undecided (for a scheduled check)
--json      also write the findings as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

from catalogue_config import FORMER_STATUS, PENDING_STATUS, load_registry
from merge_member_list import FORMER_NOTES, full_key, load_list, match, registry_name
from probe_missing import NOISE, claims, norm

SIMILAR = 0.8  # name similarity that counts as a strong hint
MIN_WORD = 5  # a shorter word is too common to name a company

ALIAS_CANDIDATE = "alias-candidate"
STILL_LISTED = "still-listed"
LIKELY_FORMER = "likely-former"
UNKNOWN = "unknown"
REINSTATE = "reinstate?"
# Verdicts that need a person's decision. A former entry that stays absent
# from both the roster and the page is decided and never appears.
UNDECIDED = {ALIAS_CANDIDATE, STILL_LISTED, LIKELY_FORMER, UNKNOWN, REINSTATE}


def brand_words(name: str) -> list:
    """The words of a name that could identify the company on their own."""
    return [w for w in norm(name) if w not in NOISE and len(w) >= MIN_WORD]


def domain_label(url: str) -> str:
    """`https://www.glesys.fi/x` -> `glesys`."""
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    labels = host.split(".")
    return labels[-2] if len(labels) >= 2 else ""


def compact(text: str) -> str:
    return "".join(norm(text))


def candidates(entry: dict, roster_records: dict) -> list:
    """Roster companies that look like the same company as this entry.

    roster_records maps a roster name to the registry records that name it.
    Returns (roster name, strength, reason) rows, strongest first.
    """
    name = registry_name(entry)
    own_key = full_key(name)
    words = set(brand_words(name))
    label = domain_label(entry.get("url"))
    found = {}

    def note(roster_name: str, strength: int, reason: str) -> None:
        if roster_name not in found or found[roster_name][0] < strength:
            found[roster_name] = (strength, reason)

    for roster_name, records in roster_records.items():
        ratio = SequenceMatcher(None, own_key, full_key(roster_name)).ratio()
        if ratio >= SIMILAR:
            note(roster_name, 2, f"similar name ({ratio:.0%})")
        for record in records:
            if record is entry:
                continue
            url = compact(record.get("url") or "")
            text = compact(
                " ".join(str(record.get(f) or "") for f in ("web_search_content", "blog_content"))
            )
            spaced = " ".join(
                str(record.get(f) or "") for f in ("web_search_content", "blog_content")
            ).lower()
            for word in sorted(words):
                if word in url:
                    note(roster_name, 2, f"{word!r} is in its homepage address")
                elif re.search(rf"\b{re.escape(word)}\b", spaced):
                    note(roster_name, 1, f"{word!r} is mentioned in its description")
            if len(label) >= MIN_WORD + 1 and label in url:
                note(roster_name, 2, f"its homepage domain {label!r} is in the entry's address")
            elif len(label) >= MIN_WORD + 1 and label in text:
                note(roster_name, 1, f"{label!r} is mentioned in its description")
    rows = [(n, s, r) for n, (s, r) in found.items()]
    return sorted(rows, key=lambda row: (-row[1], row[0]))


def verdict_for(entry: dict, hints: list, on_page: bool | None, matched: bool) -> str:
    former = entry.get("roster_status") == FORMER_STATUS or registry_name(entry) in FORMER_NOTES
    if former and (matched or on_page):
        return REINSTATE
    if matched or former:
        return ""  # on the roster, or a settled former entry
    if any(strength >= 2 for _, strength, _ in hints):
        return ALIAS_CANDIDATE
    if on_page:
        return STILL_LISTED
    if on_page is None:
        return UNKNOWN
    return LIKELY_FORMER


def audit(registry: list, roster: list, logos: list | None) -> dict:
    """Compare the registry with the roster and, when given, the live logos.

    logos is a list of (logo text, url) rows from the members page, or None
    when the page was not read.
    """
    resolved = match(registry, roster)
    roster_records = {name: [] for name in roster}
    for entry in registry:
        official = resolved[registry_name(entry)]
        if official is not None:
            roster_records[official].append(entry)

    live = logos is not None
    logo_urls = {url for _, url in logos or []}
    rows = []
    for entry in registry:
        matched = resolved[registry_name(entry)] is not None
        on_page = None
        if live:
            on_page = entry.get("logo_url") in logo_urls or any(
                claims(entry, _logo_core(text)) for text, _ in logos
            )
        # Only entries the roster does not name need weighing against it; a
        # former entry is also weighed here, to catch a reinstatement.
        unmatched = not matched
        former = entry.get("roster_status") == FORMER_STATUS or registry_name(entry) in FORMER_NOTES
        if not unmatched and not former:
            continue
        hints = candidates(entry, roster_records) if unmatched else []
        verdict = verdict_for(entry, hints, on_page, matched)
        if verdict:
            rows.append({
                "name": registry_name(entry),
                "status": entry.get("roster_status") or "",
                "verdict": verdict,
                "on_members_page": on_page,
                "roster_matches": hints[:3],
                "roster_line": resolved[registry_name(entry)],
                "url": entry.get("url"),
            })

    unclaimed = []
    if live:
        for text, url in logos:
            core = _logo_core(text)
            if url in {e.get("logo_url") for e in registry}:
                continue
            if not any(claims(e, core) for e in registry):
                unclaimed.append((text, url))
    no_record = [name for name, records in roster_records.items() if not records]
    return {"entries": rows, "unclaimed_logos": unclaimed, "roster_without_record": no_record, "live": live}


def _logo_core(text: str) -> list:
    words = [w for w in norm(text) if w != "fdca" and not w.isdigit()]
    return [w for w in words if w not in NOISE] or words


def report(result: dict) -> None:
    rows = result["entries"]
    if not result["live"]:
        print("fdca.fi was not read: no verdict can use the members page.\n")
    if not rows:
        print("Roster and catalogue agree: no entry needs a decision.")
    order = [ALIAS_CANDIDATE, STILL_LISTED, REINSTATE, LIKELY_FORMER, UNKNOWN]
    for verdict in order:
        group = [r for r in rows if r["verdict"] == verdict]
        if not group:
            continue
        print(f"{verdict} ({len(group)})")
        for row in group:
            print(f"  {row['name']}  [{row['status'] or 'no status'}]  {row['url'] or ''}")
            # A weak hint is a word in a description. It is mostly noise, so
            # only the JSON keeps it.
            strong = [hint for hint in row["roster_matches"] if hint[1] >= 2]
            for roster_name, _, reason in strong:
                print(f"    -> {roster_name}: {reason}")
            if verdict == ALIAS_CANDIDATE:
                best = strong[0][0]
                print(f'    ALIASES line:      "{row["name"]}": "{best}",')
            elif verdict == LIKELY_FORMER:
                print(f'    FORMER_NOTES line: "{row["name"]}": "<why, and who confirmed it>",')
            elif verdict == REINSTATE:
                print(f'    remove "{row["name"]}" from FORMER_NOTES')
        print()
    if result["unclaimed_logos"]:
        print(f"Logos on the members page that no registry entry claims ({len(result['unclaimed_logos'])})")
        print("  A new member to add, or a name the registry spells differently:")
        for text, url in result["unclaimed_logos"]:
            print(f"  {text!r}  {url}")
        print()
    if result["roster_without_record"]:
        print(f"Roster lines with no registry record ({len(result['roster_without_record'])})")
        print("  merge_member_list.py adds each one as a new member:")
        for name in result["roster_without_record"]:
            print(f"  {name}")


def undecided(result: dict) -> int:
    return sum(r["verdict"] in UNDECIDED for r in result["entries"]) + len(result["unclaimed_logos"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="do not read fdca.fi")
    parser.add_argument("--strict", action="store_true", help="exit 1 while anything is undecided")
    parser.add_argument("--json", type=Path, help="also write the findings here")
    args = parser.parse_args()

    logos = None
    if not args.offline:
        try:
            from fetch_logos import fdca_logos

            logos = fdca_logos()
            if not logos:
                print("warning: the members page held no logos; treating it as unread", file=sys.stderr)
                logos = None
        except Exception as error:  # network, layout change: degrade, do not guess
            print(f"warning: could not read fdca.fi ({error}); verdicts use no live evidence", file=sys.stderr)

    result = audit(load_registry(), load_list(), logos)
    report(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.strict and undecided(result):
        raise SystemExit(f"\n{undecided(result)} discrepancies need a decision")


if __name__ == "__main__":
    main()
