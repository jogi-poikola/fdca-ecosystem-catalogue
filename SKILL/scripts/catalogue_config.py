"""Shared catalogue taxonomy and classification-rule loader.

All catalogue scripts import this module instead of carrying their own copy of
the category structure. The registry stores one primary category slug; family
membership and display labels are derived here from the taxonomy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
TAXONOMY_PATH = INPUT_DIR / "fdca-categories.json"
RULES_PATH = INPUT_DIR / "fdca-classification-rules.json"
DESIGN_PATH = INPUT_DIR / "DESIGN.md"
GUIDE_PATH = INPUT_DIR / "company-category-classification-rules.md"
SUMMARY_PATH = OUTPUT_DIR / "category-summary.md"

UNCLASSIFIED = "uncategorised"
REQUIRED_TEXT_FIELDS = ("en", "fi", "description_en", "description_fi")
VISUAL_FIELDS = {"hue", "chromaK", "color", "colour", "colors", "colours"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_taxonomy() -> dict:
    return load_json(TAXONOMY_PATH)


def load_rules() -> dict:
    return load_json(RULES_PATH)


def load_registry() -> list[dict]:
    return load_json(REGISTRY_PATH)


def taxonomy_index(taxonomy: dict | None = None) -> dict:
    taxonomy = taxonomy or load_taxonomy()
    families = taxonomy["families"]
    category_by_slug = {}
    family_by_slug = {}
    category_family = {}
    for family in families:
        family_by_slug[family["slug"]] = family
        for category in family["categories"]:
            category_by_slug[category["slug"]] = category
            category_family[category["slug"]] = family["slug"]
    return {
        "families": families,
        "family_by_slug": family_by_slug,
        "category_by_slug": category_by_slug,
        "category_family": category_family,
        "category_slugs": set(category_by_slug),
    }


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))


def ui_acronyms(text: str) -> list[str]:
    """Return unexplained all-capital tokens from user-interface copy."""
    return re.findall(r"(?<![\w-])[A-ZÅÄÖ]{2,}(?![\w-])", text)


def validate_taxonomy(taxonomy: dict, rules: dict) -> list[str]:
    errors = []
    if rules.get("taxonomy_version") != taxonomy.get("version"):
        errors.append(
            "rules taxonomy_version does not match taxonomy version: "
            f"{rules.get('taxonomy_version')!r} != {taxonomy.get('version')!r}"
        )

    family_slugs = []
    category_slugs = []
    for family in taxonomy.get("families", []):
        family_slugs.append(family.get("slug"))
        visual = VISUAL_FIELDS.intersection(family)
        if visual:
            errors.append(f"family {family.get('slug')}: visual fields belong in DESIGN.md: {sorted(visual)}")
        for field in REQUIRED_TEXT_FIELDS:
            text = str(family.get(field) or "").strip()
            if not text:
                errors.append(f"family {family.get('slug')}: missing {field}")
            elif field.startswith("description_") and word_count(text) > 15:
                errors.append(f"family {family.get('slug')}: {field} exceeds 15 words")
            for acronym in ui_acronyms(text):
                errors.append(f"family {family.get('slug')}: unexplained acronym {acronym!r} in {field}")

        for category in family.get("categories", []):
            slug = category.get("slug")
            category_slugs.append(slug)
            visual = VISUAL_FIELDS.intersection(category)
            if visual:
                errors.append(f"category {slug}: visual fields belong in DESIGN.md: {sorted(visual)}")
            for field in REQUIRED_TEXT_FIELDS:
                text = str(category.get(field) or "").strip()
                if not text:
                    errors.append(f"category {slug}: missing {field}")
                elif field.startswith("description_") and word_count(text) > 15:
                    errors.append(f"category {slug}: {field} exceeds 15 words")
                for acronym in ui_acronyms(text):
                    errors.append(f"category {slug}: unexplained acronym {acronym!r} in {field}")
            if slug != "data_center_operators" and "data center" in str(category.get("en", "")).lower():
                errors.append(f"category {slug}: redundant 'Data Center' in English name")

    if len(family_slugs) != len(set(family_slugs)):
        errors.append("family slugs are not unique")
    if len(category_slugs) != len(set(category_slugs)):
        errors.append("category slugs are not unique")

    rule_family_slugs = [row.get("family_slug") for row in rules.get("family_sequence", [])]
    if len(rule_family_slugs) != len(set(rule_family_slugs)) or set(rule_family_slugs) != set(family_slugs):
        errors.append("family_sequence must list every taxonomy family exactly once")

    rules_by_family = {row.get("family_slug"): row for row in rules.get("families", [])}
    if set(rules_by_family) != set(family_slugs):
        errors.append("classification rules must contain exactly the taxonomy families")
    referenced = []
    for family_slug in family_slugs:
        for rule in rules_by_family.get(family_slug, {}).get("rules", []):
            category_slug = rule.get("category_slug")
            referenced.append(category_slug)
            if category_slug not in category_slugs:
                errors.append(f"rule references unknown category {category_slug!r}")
            elif taxonomy_index(taxonomy)["category_family"][category_slug] != family_slug:
                errors.append(f"rule for {category_slug!r} is under the wrong family")
    if sorted(referenced) != sorted(category_slugs):
        errors.append("every category must occur exactly once in the decision rules")
    return errors


def validate_registry(members: list[dict], taxonomy: dict, publish: bool = True) -> list[str]:
    index = taxonomy_index(taxonomy)
    errors = []
    seen = set()
    for member in members:
        name = member.get("display_name") or member.get("official_name") or "<unnamed>"
        if name in seen:
            errors.append(f"duplicate display_name: {name}")
        seen.add(name)
        if "subcategory" in member:
            errors.append(f"{name}: legacy subcategory field is not permitted")
        category = member.get("category")
        if category == UNCLASSIFIED:
            if publish:
                errors.append(f"{name}: uncategorised is not publishable")
        elif category not in index["category_slugs"]:
            errors.append(f"{name}: unknown category {category!r}")
    return errors


def fail_on_errors(errors: list[str]) -> None:
    if errors:
        raise SystemExit("\n".join(f"ERROR: {error}" for error in errors))
