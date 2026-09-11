#!/usr/bin/env python3
"""
Hold INPUT/fdca-member-registry.json to the category taxonomy in
INPUT/fdca-categories.json.

An earlier classification pass wrote categories straight into the JSON and
checked them against nothing, so the registry drifted into invented
subcategory slugs. This script is the enforcement check that was missing.

Two jobs, in order:

1. **Remap.** REMAP below moves each drifted member onto a sanctioned slug.
   Every line was decided by reading that member's own description, and carries
   the reason when it is not obvious.
2. **Validate.** Every entry's `category` must be a taxonomy slug, and its
   `subcategory` must be one the taxonomy lists under that category, or empty.
   A category with no subcategories requires an empty one.

The rule the remap follows: never invent a slug. Where no sanctioned
subcategory fits, the subcategory is cleared and the category kept. Clearing is
honest — it says "this member has no second level" rather than inventing one.

`uncategorised` is not a taxonomy slug and is accepted anyway. It is the
explicit "not classified yet" value that merge_member_list.py writes for a
roster member the website has no page for. It is reported, never remapped:
those members carry no description to classify from.

Usage:
    python3 SKILL/scripts/apply_taxonomy.py [--check]

--check reports what would change and writes nothing.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
TAXONOMY_PATH = INPUT_DIR / "fdca-categories.json"

# The value merge_member_list.py writes for a roster member with no website
# page. Not a taxonomy slug, and deliberately allowed.
UNCLASSIFIED = "uncategorised"

# display_name -> (category, subcategory). "" means no second level.
REMAP = {
    # A sanctioned subcategory fits — just the wrong slug for it.
    "Adapteo": ("services", "temporary_housing"),  # modular accommodation, rented
    "Aro Systems Oy": ("construction", "specialized_contractors"),  # electrical and HVAC installer
    "HYDAC": ("technology_vendors", "cooling_and_heat_recovery"),  # was a second spelling of this slug
    "JAKE Rakennus": ("construction", "general_contractors"),  # turnkey and EPC contracts
    "NYAB": ("construction", "specialized_contractors"),  # describes itself as a specialized contractor
    "Pur-ait Oy": ("services", "security_services"),  # perimeter protection, as Heras is filed
    "Salboheds": ("construction", "specialized_contractors"),
    "Signal Group": ("construction", "specialized_contractors"),  # electrical and telecom infrastructure
    # A manufacturer or supplier, not a contractor — the category moves too.
    "CG PROFESSIONAL": ("technology_vendors", "building_materials"),  # supplies materials, does not build
    "NKT": ("technology_vendors", "power_systems"),  # manufactures the cable it installs
    "Nordec": ("technology_vendors", "building_materials"),  # fabricates steel frames and envelopes
    "Peltitarvike Oy": ("technology_vendors", "building_materials"),  # manufactures construction metal products
    # No sanctioned subcategory fits, so it is cleared rather than invented.
    "BeMaPro Oy": ("services", ""),  # construction project management
    "DECI Ltd": ("planning", "design_engineering"),  # commissioning and engineering management
    "Finess Energy": ("services", ""),  # turnkey energy-efficiency projects
    "Rejlers": ("planning", "design_engineering"),  # engineering consultancy — the category already says it
    "Valorem Energies Finland Oy": ("services", "renewable_energy"),
    "Windelligence": ("services", "renewable_energy"),
    "Oomi Oy": ("services", "renewable_energy"),  # website-only entry, missed by the first pass
}


def load_taxonomy() -> dict:
    """category slug -> the set of subcategory slugs it permits."""
    data = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {c["slug"]: {s["slug"] for s in c["subcategories"]} for c in data["categories"]}


def violations(members: list, allowed: dict) -> list:
    """Every entry whose category or subcategory the taxonomy does not permit."""
    out = []
    for member in members:
        category = member.get("category")
        subcategory = member.get("subcategory") or ""
        if category == UNCLASSIFIED:
            continue
        if category not in allowed:
            out.append((member["display_name"], category, subcategory, "category not in taxonomy"))
        elif subcategory and subcategory not in allowed[category]:
            reason = (
                "category has no subcategories"
                if not allowed[category]
                else "subcategory not in taxonomy"
            )
            out.append((member["display_name"], category, subcategory, reason))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    allowed = load_taxonomy()
    members = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_name = {m["display_name"]: m for m in members}

    unknown = sorted(set(REMAP) - set(by_name))
    if unknown:
        raise SystemExit(f"REMAP names no member in the registry: {unknown}")

    print(f"before — {len(violations(members, allowed))} entries off the taxonomy")
    applied = []
    for name, (category, subcategory) in REMAP.items():
        member = by_name[name]
        was = (member.get("category"), member.get("subcategory") or "")
        if was == (category, subcategory):
            continue
        member["category"], member["subcategory"] = category, subcategory
        applied.append((name, was, (category, subcategory)))

    print(f"remapped {len(applied)} members:")
    for name, was, now in applied:
        old = f"{was[0]}/{was[1]}" if was[1] else was[0]
        new = f"{now[0]}/{now[1]}" if now[1] else f"{now[0]} (no subcategory)"
        print(f"  {name:32s} {old}  ->  {new}")

    left = violations(members, allowed)
    print(f"\nafter — {len(left)} entries off the taxonomy")
    for name, category, subcategory, reason in left:
        print(f"  {name}: {category}/{subcategory} — {reason}")

    unclassified = [m for m in members if m.get("category") == UNCLASSIFIED]
    print(f"\n{len(unclassified)} members still '{UNCLASSIFIED}' — roster members with")
    print("no page on fdca.fi, so no description to classify from.")

    if args.check:
        print("\n--check: nothing written")
        return
    if left:
        raise SystemExit("\nrefusing to write while entries are off the taxonomy")
    REGISTRY_PATH.write_text(
        json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {REGISTRY_PATH.name}")


if __name__ == "__main__":
    main()
