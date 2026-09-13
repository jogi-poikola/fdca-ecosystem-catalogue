#!/usr/bin/env python3
"""One-time migration from the reviewed two-level taxonomy to taxonomy 4.0.

The old audit remains the evidence record. This migration converts each
reviewed family/subcategory result to one primary category and records the
result in OUTPUT/category-classification-v4.json for human validation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from catalogue_config import (
    OUTPUT_DIR,
    REGISTRY_PATH,
    load_rules,
    load_taxonomy,
    taxonomy_index,
)

REVIEW_PATH = OUTPUT_DIR / "category-review-proposals.json"
AUDIT_PATH = OUTPUT_DIR / "category-classification-v4.json"

DEFAULTS = {
    ("data_center_operators", ""): "data_center_operators",
    ("technology_vendors", "power_systems"): "power_equipment",
    ("technology_vendors", "cooling_and_heat_recovery"): "cooling_heat_recovery",
    ("technology_vendors", "it_infrastructure"): "computing_network_equipment",
    ("technology_vendors", "automation_and_safety"): "automation_software",
    ("technology_vendors", "building_materials"): "building_products",
    ("technology_vendors", ""): "other_technology",
    ("construction", "general_contractors"): "industrial_construction",
    ("construction", "specialized_contractors"): "technical_systems_installation",
    ("planning", "design_engineering"): "design_engineering",
    ("planning", "site_developers"): "site_development",
    ("planning", "municipalities"): "municipal_regional_development",
    ("services", "renewable_energy"): "energy",
    ("services", "connectivity"): "connectivity",
    ("services", "facility_management"): "facility_management",
    ("services", "security_services"): "security_services",
    ("services", "it_equipment_services"): "equipment_maintenance",
    ("services", "logistics"): "logistics",
    ("services", "staffing"): "staffing",
    ("services", "legal"): "legal_business_advisory",
    ("services", "real_estate_advisory"): "legal_business_advisory",
    ("services", "public_affairs"): "legal_business_advisory",
    ("services", "investment"): "legal_business_advisory",
    ("services", "temporary_housing"): "other_services",
    ("services", "education_standards_certification"): "other_services",
    ("services", ""): "other_services",
    ("uncategorised", ""): "other_services",
}

OVERRIDES = {
    # Technology categories split from the former automation/safety and catch-all groups.
    "Abloy Oy": "security_technology",
    "Elpac Oy": "security_technology",
    "Fibox Tested Systems Oy": "power_equipment",
    "IQSIGHT": "security_technology",
    "Liekkiloukku": "security_technology",
    "Marioff Corporation OY": "security_technology",
    "Nordpel Oy": "security_technology",
    "Prysmian Group Finland Oy": "power_equipment",
    "Salto Systems Oy": "security_technology",
    "Stoa Technologies Oy": "automation_software",
    "U-Cont": "cooling_heat_recovery",

    # Main contractor requires a confirmed Finnish role. NYAB is confirmed for Nordic Compute, Mikkeli.
    "Fira": "main_contractors",
    "NYAB": "main_contractors",
    "Skanska": "main_contractors",
    "SRV": "main_contractors",
    "Tekova Oyj": "main_contractors",
    "YIT": "main_contractors",

    # Construction specialisms and explicit exclusions from Main Contractors.
    "AGIS Fire & Security Oy": "fire_safety_construction",
    "Aurora Infrastructure Oy": "grid_substation_construction",
    "Consti Group": "other_construction",
    "Cores OY": "roofing_building_envelope",
    "Destia": "infrastructure_construction",
    "ELTEL Networks Oy": "grid_substation_construction",
    "Enerke Oy": "grid_substation_construction",
    "Enersense": "grid_substation_construction",
    "Firesafe Finland Oy": "fire_safety_construction",
    "GRK": "infrastructure_construction",
    "H&MV Engineering": "grid_substation_construction",
    "Hartela Oy": "industrial_construction",
    "Infra ry": "infrastructure_construction",
    "KattoHoiva": "roofing_building_envelope",
    "Kerabit": "roofing_building_envelope",
    "Kreate": "infrastructure_construction",
    "KSBR": "infrastructure_construction",
    "Louhintahiekka Oy": "infrastructure_construction",
    "Omexom": "grid_substation_construction",
    "Paloff Sammutusjärjestelmät Oy": "fire_safety_construction",
    "Peswin Oy": "technical_systems_installation",
    "Pylon": "infrastructure_construction",
    "Salboheds": "infrastructure_construction",
    "Suomen Teollisuuskatot Oy": "roofing_building_envelope",
    "TEP Roof Oy": "roofing_building_envelope",
    "TT-Teknologia Oy": "industrial_construction",
    "Varte Oy": "industrial_construction",

    # Independent planning, supervision and project controls.
    "BeMaPro Oy": "project_management",
    "Cronos Digital Safety Solutions Oy": "project_management",
    "Finavia Oyj": "site_development",
    "GagaMuller": "project_management",
    "Gleeds": "project_management",

    # Service categories learned from the DCD comparison and the audit.
    "Alpiq Finland Oy": "energy",
    "Costiom OY": "legal_business_advisory",
    "Elenia": "energy",
    "Finess Energy": "energy",
    "Gasum": "energy",
    "Helen Oy": "energy",
    "Infuel Oy": "energy",
    "MV-Jäähdytys Oy": "equipment_maintenance",
    "NDT aura Oy": "commissioning_testing",
    "PD Power Oy": "energy",
    "Rentaload": "commissioning_testing",
}

MAIN_CONTRACTOR_EVIDENCE = {
    "Fira": "https://fira.fi/en/news-en/construction-and-project-development-company-fira-selected-as-main-contractor-for-one-of-europes-largest-ai-data-center-projects/",
    "NYAB": "https://nyabgroup.com/en/newsroom/nyab-signs-contract-for-data-center-project-in-mikkeli-finland/",
    "Skanska": "https://www.skanska.com/group/en/media/press-releases/2026/skanska-builds-data-center-expansion-in-espoo-finland-for-eur-100m-about-sek-1.1-billion",
    "SRV": "https://www.srv.fi/en/for-developers/business-premises-construction/data-centers/",
    "Tekova Oyj": "https://tekova.fi/referenssit/datakeskus-mantsala/",
    "YIT": "https://www.yitgroup.com/en/news-repository/investor-news/yit-and-atnorth-agree-on-construction-of-a-data-center-in-kouvola--value-for-yit-approximately-eur-300-million",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate and report without writing")
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    rules = load_rules()
    valid = taxonomy_index(taxonomy)["category_slugs"]
    members = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    reviewed = {row["display_name"]: row for row in review}
    missing = [member["display_name"] for member in members if member["display_name"] not in reviewed]
    if missing:
        raise SystemExit(f"members missing from reviewed audit: {missing}")

    audit = []
    for member in members:
        row = reviewed[member["display_name"]]
        old = (row["proposed_category"], row["proposed_subcategory"])
        category = OVERRIDES.get(member["display_name"], DEFAULTS.get(old))
        if category not in valid:
            raise SystemExit(f"{member['display_name']}: no valid migration for {old}: {category!r}")
        web_sources = list(row["web_sources"])
        if member["display_name"] in MAIN_CONTRACTOR_EVIDENCE:
            source = MAIN_CONTRACTOR_EVIDENCE[member["display_name"]]
            if source not in web_sources:
                web_sources.append(source)
        audit.append({
            "display_name": member["display_name"],
            "taxonomy_version": taxonomy["version"],
            "rules_version": rules["version"],
            "previous_review_category": row["proposed_category"],
            "previous_review_subcategory": row["proposed_subcategory"],
            "category": category,
            "confidence": row["confidence"],
            "evidence_source": "web-verified" if web_sources else row["evidence_source"],
            "offering_summary": row["offering_summary"],
            "web_sources": web_sources,
        })
        member["category"] = category
        member.pop("subcategory", None)

    if args.check:
        print(f"Migration valid for {len(members)} companies; nothing written.")
        return

    REGISTRY_PATH.write_text(json.dumps(members, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Migrated {len(members)} companies to taxonomy {taxonomy['version']}.")
    print(f"Wrote {AUDIT_PATH}.")


if __name__ == "__main__":
    main()
