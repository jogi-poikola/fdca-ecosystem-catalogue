#!/usr/bin/env python3
"""
Merge FDCA's own member list into INPUT/fdca-member-registry.json.

Two sources, one record per member:

- **INPUT/fdca-member-list-<date>.txt** is FDCA's own roster and the master for the
  official name. It is the complete membership; nothing outside it is a member.
- **INPUT/fdca-member-registry.json** is scraped from fdca.fi and is the master for
  the display name — the shorter brand a company is actually known by — plus
  the description, logo, and blog link.

So every merged entry carries both names:

    official_name  the roster line, verbatim
    display_name   the scraped website name, or the official name when the
                   website has no page for that member

Several registry entries can name one roster member — a brand page and a legal
name page, or the same company under two spellings. Those fold into one entry:
the display name comes from the primary, and every empty field is filled from
the others. `folded_from` records what was folded in.

A registry entry that is on no roster line is not confirmed as a member. It
stays in the registry with its scraped research intact, marked
`roster_status: website-only`, and is counted separately from the roster's own
members. Nothing is ever deleted.

Matching is by normalised name (case, punctuation, and company-form suffixes
removed), plus the alternate brands a roster line carries after a `/` or
inside parentheses. ALIASES below carries the pairs no rule can reach.

Usage:
    python3 SKILL/scripts/merge_member_list.py [--check]

--check reports what would change and writes nothing.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
LIST_PATH = INPUT_DIR / "fdca-member-list-2026-08-29.txt"
LIST_DATE = "2026-08-29"

# The scraped fields a fold fills in from a secondary entry.
SCRAPED_FIELDS = (
    "url",
    "category",
    "subcategory",
    "blog_link",
    "blog_content",
    "web_search_content",
    "logo_url",
    "researched",
)

# registry name -> member list name. Every pair here was confirmed by reading
# both names, not by a rule. Keep the comment when the reason is not obvious.
ALIASES = {
    # Confirmed before 2026-08-30.
    "AINS Group": "A-Insinöörit Oy",  # AINS Group is A-Insinöörit's brand
    "Dell Technologies": "Oy Dell Ab",
    "Epm-papst Oy": "ebm-papst Oy",  # registry misspells ebm-papst
    "Fläkt Group": "FläktGroup Finland Oy",
    "Kerabit": "KerabitPro Oy",
    "Reka Cables": "Reka Kaapeli",
    "TietoEVRY Oyj": "Tech Services Finland Oy (Tietoervy)",
    "Verne Finland": "Verne Vantaa Oy",
    "Vesala Oy": "H. Vesala Oy",
    # Same company, spelling or word order differs. Approved 2026-08-30.
    "EKAMI": "Kotkan-Haminan seudun koulutuskuntayhtymä",  # EKAMI is its brand
    "DayOne": "Digitalland Services FI",  # DayOne is the brand; the roster has the legal entity
    "FDCD": "FCDC Corp Oy",  # fdca.fi misspells the title; its own link is fcdc.fi
    "Stanley Security": "Securitas Technology Oy",  # renamed after Securitas bought it
    "Pure DC": "Pure Data Cetres",  # the roster line carries the typo
    "R&M Europe BV": "R&M Europe B.V., Suomen Sivuliike",
    "Server Simply": "Serversimply OU",
    "Supermicro": "Super Micro Computer, B.V.",
    "Synopsis Architects Ltd": "Synopsis Arkkitehdit Oy",
    "U-Cont": "Oy U-Cont Ltd",
    "Westim Qpower": "WestimQpower Oy",
    # Brand, rename, or acquisition. Each confirmed by search, 2026-08-30.
    "BOS Power": "Bertel O. Steen Power Solutions Finland Oy",  # BOS = Bertel O. Steen
    "Borealis Data Center": "Borealis Finland Oy",  # the Kajaani campus entity, not Borealis Polymers
    "GPP Perimeter Protection Oy": "Heras Finland High Security Oy",  # renamed after Garda Group bought Heras
    "Minkels, Legrand": "Legrand DC Solution Nordic",  # Minkels is a Legrand brand
    "Omexom": "Infratek Finland Oy",  # Omexom is the VINCI Energies brand; legal name unchanged
    "Paroc Panel System": "Kingspan Oy",  # Paroc sold Panel System to Kingspan
    # Group versus subsidiary. Antti's call, 2026-08-30: the roster names the
    # entity that is the member, and the parent's scraped description fits it.
    "Erillisverkot": "Leijonaverkot Oy",  # Leijonaverkot is Erillisverkot's data centre subsidiary
    "T-DRILL Industries": "Leinolat Group Oy",  # T-DRILL is one of the Leinolat Group's companies
    "Navitas Yrityspalvelut": "Navitas Kehitys Oy",  # both are Varkaus regional development bodies
    "Worker Henkilöstöratkaisut": "Worker Oulu Oy",  # the roster names only the Oulu company
}

# roster name -> the registry entry whose name becomes the display name, for
# the folds where two scraped entries meet on one roster line and alphabetical
# order would pick the wrong one.
DISPLAY_PRIMARY = {
    "Heras Finland High Security Oy": "Heras Finland High Security Oy",  # not GPP, the old name
    "Legrand DC Solution Nordic": "Legrand",  # not Minkels, one of its brands
    # The only scraped entry carries the website's own typo, so the roster
    # name wins and the scrape contributes just its logo.
    "FCDC Corp Oy": "FCDC Corp Oy",
    "Securitas Technology Oy": "Securitas Technology Oy",  # not "Stanley Security", the old name
    # The roster names the group, so the group name wins over its subsidiary's
    # brand page and the T-DRILL scrape contributes only what Leinolat lacks.
    "Leinolat Group Oy": "Leinolat Group Oy",
}

# Why a registry entry is not on the roster, where the reason is known.
FORMER_NOTES = {}

SUFFIX = (
    r"(oy ab|oyj|oy|ab|ltd|limited|a/s|as|plc|inc|corp|corporation"
    r"|gmbh|sia|group|co|company)"
)


def base(name: str) -> str:
    """Normalise one name to its comparable core."""
    text = re.sub(r"[^a-z0-9åäö ]", " ", name.lower())
    text = re.sub(r"\s+", " ", text).strip()
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\s" + SUFFIX + r"$", "", text).strip()
    return text


def full_key(name: str) -> str:
    """The one normalised form of a name, parentheses dropped."""
    return base(re.sub(r"\(.*?\)", "", name))


def aliases(name: str) -> set:
    """The alternate brands a name carries after a `/` or inside parentheses.

    A parenthesis often holds a qualifier rather than a brand — `(Finland)`
    names no company. The caller drops any alias shared by two roster
    members, which is what disqualifies those generic keys.
    """
    parts = name.split("/") + re.findall(r"\((.*?)\)", name)
    out = {full_key(part) for part in parts}
    out.discard(full_key(name))
    return {key for key in out if key}


def load_list() -> list:
    names, seen = [], set()
    for line in LIST_PATH.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name:
            continue
        key = full_key(name)
        if key in seen:
            continue  # the roster lists Convergint Finland Oy twice
        seen.add(key)
        names.append(name)
    return names


def registry_name(entry: dict) -> str:
    """This entry's own name, whichever field shape it was written in."""
    return entry.get("display_name") or entry["name"]


def match(registry: list, roster: list) -> dict:
    """registry name -> roster name, or None when the entry is not on it."""
    by_full = {full_key(name): name for name in roster}

    # An alias two roster members share names neither of them — `(Finland)`
    # is a qualifier, not a brand — so only the unique ones can match.
    shared = {}
    for name in roster:
        for key in aliases(name):
            shared.setdefault(key, set()).add(name)
    by_alias = {
        key: names.pop() for key, names in shared.items()
        if len(names) == 1 and key not in by_full
    }

    resolved = {}
    for entry in registry:
        name = registry_name(entry)
        if name in ALIASES:
            resolved[name] = ALIASES[name]
            continue
        # Either side may hold the brand and the other the legal name, so
        # look both names up under both forms.
        keys = {full_key(name)} | aliases(name)
        hits = {by_full[key] for key in keys if key in by_full}
        hits |= {by_alias[key] for key in keys if key in by_alias}
        if len(hits) == 1:
            resolved[name] = hits.pop()
            continue
        if len(hits) > 1:
            raise SystemExit(f"ambiguous match for {name!r}: {sorted(hits)}")
        # Fall back to a token-prefix match: a brand name in the registry
        # against the same company's legal name on the roster.
        tokens = full_key(name).split()
        prefix = {
            roster_name
            for key, roster_name in by_full.items()
            if key.split()[: len(tokens)] == tokens
            or tokens[: len(key.split())] == key.split()
        }
        if len(prefix) == 1:
            resolved[name] = prefix.pop()
        elif len(prefix) > 1:
            raise SystemExit(f"ambiguous prefix match for {name!r}: {sorted(prefix)}")
        else:
            resolved[name] = None
    return resolved


SCRAPE_SOURCE = "fdca.fi-scrape"


def is_scraped(entry: dict) -> bool:
    """True when this entry came from fdca.fi rather than from the roster.

    The original scrape wrote no `source` field at all, so a missing one means
    scraped. Only the roster stubs ever carried the field.
    """
    return not str(entry.get("source") or "").startswith("member-list")


def fold(official: str, entries: list) -> dict:
    """One member record from every registry entry that names it."""
    scraped = [e for e in entries if is_scraped(e)]
    chosen = DISPLAY_PRIMARY.get(official)
    if chosen:
        primary = next(e for e in entries if registry_name(e) == chosen)
    elif len(scraped) == 1:
        primary = scraped[0]
    elif len(scraped) > 1:
        raise SystemExit(
            f"{official!r} has {len(scraped)} scraped entries and no "
            f"DISPLAY_PRIMARY: {sorted(registry_name(e) for e in scraped)}"
        )
    else:
        primary = entries[0]

    others = [e for e in entries if e is not primary]
    merged = {
        "official_name": official,
        "display_name": registry_name(primary) if is_scraped(primary) else official,
        "roster_status": "on-roster",
        "source": primary.get("source") or SCRAPE_SOURCE,
    }
    for field in SCRAPED_FIELDS:
        value = primary.get(field)
        if value in (None, "", "uncategorised"):
            for other in others:
                if other.get(field) not in (None, "", "uncategorised"):
                    value = other[field]
                    break
        merged[field] = value
    # A roster stub folded in under its own official name adds no information,
    # so only a distinctly named entry is worth recording.
    names = sorted(
        registry_name(e) for e in others if registry_name(e) != official
    )
    if names:
        merged["folded_from"] = names
    return merged


def website_only(entry: dict) -> dict:
    """An entry fdca.fi lists that no roster line names.

    Kept in the same file as the members and marked, never removed. A former
    member and a naming mismatch look identical to a matcher, and only FDCA's
    office can tell them apart — see the project note for the open question.
    """
    out = {
        "official_name": None,
        "display_name": registry_name(entry),
        "roster_status": "website-only",
        "source": entry.get("source") or SCRAPE_SOURCE,
    }
    for field in SCRAPED_FIELDS:
        out[field] = entry.get(field)
    note = FORMER_NOTES.get(out["display_name"])
    if note:
        out["note"] = note
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    roster = load_list()
    resolved = match(registry, roster)

    groups, dropped = {}, []
    for entry in registry:
        official = resolved[registry_name(entry)]
        if official is None:
            dropped.append(entry)
        else:
            groups.setdefault(official, []).append(entry)

    members = [fold(official, groups[official]) for official in sorted(groups)]
    missing = [name for name in roster if name not in groups]
    members += [fold(name, [{"source": f"member-list-{LIST_DATE}"}]) for name in missing]
    members.sort(key=lambda m: m["display_name"].lower())

    extras = sorted(
        (website_only(e) for e in dropped), key=lambda m: m["display_name"].lower()
    )
    absorbed = sum(len(entries) - 1 for entries in groups.values())

    print(f"roster members ({LIST_DATE}): {len(roster)}")
    print(f"registry entries before:     {len(registry)}")
    print(f"  merged into another entry: {absorbed}")
    print(f"  on the website only:       {len(extras)}")
    print(f"added from the roster:       {len(missing)}")
    print(f"members after:               {len(members)}")
    print()
    print("Two scraped pages, one member — the display name kept:")
    for member in members:
        if member.get("folded_from"):
            print(f"  {member['official_name']}  <-  {', '.join(member['folded_from'])}")
    print()
    print("Website-only entries — on no roster line:")
    for member in extras:
        print(f"  {member['display_name']}")

    if args.check:
        print("\n--check: nothing written")
        return
    REGISTRY_PATH.write_text(
        json.dumps(members + extras, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {REGISTRY_PATH.name} — {len(members)} members + {len(extras)} website-only")


if __name__ == "__main__":
    main()
