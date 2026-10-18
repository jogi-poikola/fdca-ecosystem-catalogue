#!/usr/bin/env python3
"""One-time migration from taxonomy 4.0 to taxonomy 4.1 (2026-10-17).

Taxonomy 4.1 makes two changes in the services family:

- `facility_management` is merged into `equipment_maintenance`, which is now
  named "Maintenance and Facility Services". The category had one member.
- `legal_business_advisory` is split into `legal_services` (law firms) and
  `business_advisory` (financial, property, investment, communications,
  accounting and management advice).

Every affected record is listed by name below; nothing is reinterpreted by a
rule. The script fails if a record still carries a retired slug after the
mapping, so a new record in a retired category cannot slip through.

Usage:
    python3 SKILL/scripts/migrate_categories_v4_1.py [--check]

--check reports what would change and writes nothing.
"""

from __future__ import annotations

import argparse
import json

from catalogue_config import OUTPUT_DIR, REGISTRY_PATH, load_taxonomy, taxonomy_index

RETIRED = {"facility_management", "legal_business_advisory"}
AUDIT_PATH = OUTPUT_DIR / "category-migration-v4.1.json"

# display_name -> category in taxonomy 4.1. Each line was decided by reading the
# record, 2026-10-17. Former members are migrated too, so no record keeps a
# retired slug.
MIGRATION = {
    # Law firms.
    "Borenius Attorneys Ltd": "legal_services",
    "DLA Piper Finland": "legal_services",
    "Hannes Snellman": "legal_services",
    "Lieke Attorneys": "legal_services",
    "Roschier": "legal_services",
    # Financial, property, investment, communications, accounting and management advice.
    "Amesto AccountHouse Oy": "business_advisory",  # accounting, payroll, HR
    "APL Europe (UK) LTD": "business_advisory",  # private investment firm
    "Bergmann": "business_advisory",  # former member; keeps a valid slug
    "CBRE": "business_advisory",  # property and data-centre advisory
    "Costiom OY": "business_advisory",  # management consulting
    "Cushman & Wakefield": "business_advisory",  # property advisory
    "Miltton": "business_advisory",  # communications and public affairs
    # Facility services join equipment maintenance.
    "ISS Palvelut": "equipment_maintenance",
    "Logiservice": "equipment_maintenance",  # former member; keeps a valid slug
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    if taxonomy["version"] != "4.1":
        raise SystemExit(f"this migration targets taxonomy 4.1, found {taxonomy['version']!r}")
    valid = taxonomy_index(taxonomy)["category_slugs"]
    bad = {name: slug for name, slug in MIGRATION.items() if slug not in valid}
    if bad:
        raise SystemExit(f"migration targets unknown categories: {bad}")

    members = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_name = {m["display_name"]: m for m in members}
    missing = sorted(set(MIGRATION) - set(by_name))
    if missing:
        raise SystemExit(f"records named in MIGRATION are not in the registry: {missing}")

    changes = []
    for name, category in MIGRATION.items():
        member = by_name[name]
        if member["category"] != category:
            changes.append({
                "display_name": name,
                "roster_status": member.get("roster_status"),
                "from": member["category"],
                "to": category,
                "taxonomy_version": taxonomy["version"],
            })
            member["category"] = category

    left = [m["display_name"] for m in members if m["category"] in RETIRED]
    if left:
        raise SystemExit(f"records still in a retired category; add them to MIGRATION: {left}")

    for change in changes:
        print(f"{change['display_name']}: {change['from']} -> {change['to']}")
    print(f"{len(changes)} records change; {len(members)} records checked.")
    if args.check:
        print("--check: nothing written")
        return
    REGISTRY_PATH.write_text(json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(changes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {REGISTRY_PATH.name} and {AUDIT_PATH}.")


if __name__ == "__main__":
    main()
