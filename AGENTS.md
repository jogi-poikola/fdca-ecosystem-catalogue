# FDCA Ecosystem Catalogue Agent Instructions

This repository is the source of truth for the FDCA ecosystem catalogue.
The copies under the Looper vault are read-only mirrors and must never be
edited as an alternative source.

## Classification contract

- `INPUT/fdca-categories.json` owns stable family and primary-category slugs,
  bilingual names, and bilingual user-interface descriptions.
- `INPUT/fdca-classification-rules.json` owns the ordered classification
  decision rules and must reference the taxonomy version it implements.
- `INPUT/company-category-classification-rules.md` is generated from those
  structured files. Never hand-edit it.
- `INPUT/DESIGN.md` owns colours and all other presentation decisions. Visual
  tokens do not belong in the taxonomy.
- A company has exactly one primary `category`. Its family is derived from the
  taxonomy; do not store a second category, subcategory, or tag assignment.
- `uncategorised` is permitted only during intake. It must fail publish checks.

## Required workflow

When the taxonomy evolves:

1. Keep existing slugs stable whenever meaning is unchanged.
2. Update the classification rules in the same change when meaning, coverage,
   ordering, exclusions, or fallback behaviour changes.
3. Migrate affected registry records explicitly; do not silently reinterpret
   existing assignments.
4. Regenerate the Markdown guide and category summary.
5. Run `python3 SKILL/scripts/validate_catalogue.py` and rebuild the dashboard.
6. Sync validated semantic files into Looper with its one-way mirror script.

All maintenance scripts must load the taxonomy and rules at runtime. Do not
hardcode current category names, translations, descriptions, or family
membership in scripts or prompts.
