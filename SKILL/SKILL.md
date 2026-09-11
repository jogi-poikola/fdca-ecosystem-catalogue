---
name: ecosystem-catalogue
description: Maintain the FDCA ecosystem catalogue dataset and build its single-file dashboard from this project's local INPUT, SKILL/scripts, and OUTPUT folders.
---

# Ecosystem Catalogue

Use this skill when maintaining the FDCA ecosystem catalogue data in this
project folder: reconciling the roster, checking taxonomy, enriching member
records, scraping FDCA introduction posts, or rebuilding the generated
dashboard.

## Layout

The skill lives in:

`50-59-members/52-member-services/ecosystem-catalogue/development/SKILL`

Scripts are in `SKILL/scripts/`. They resolve paths relative to the
`development/` folder:

- `INPUT/` holds the tracked source data and design tokens.
- `OUTPUT/` holds regenerated artifacts such as `index.html` and
  `category-proposals.json`.

## Normal Checks

From the `development/` folder, use:

```bash
python3 SKILL/scripts/merge_member_list.py --check
python3 SKILL/scripts/apply_taxonomy.py --check
python3 SKILL/scripts/build_dashboard.py
```

`merge_member_list.py --check` verifies the roster reconciliation without
writing. `apply_taxonomy.py --check` verifies every category and subcategory
against `INPUT/fdca-categories.json`. `build_dashboard.py` writes
`OUTPUT/index.html` (Map and List views of the same five-family taxonomy).

## Data Maintenance

Use the maintenance scripts only when the relevant source changes:

- `merge_member_list.py` reconciles `INPUT/fdca-member-list-2026-08-31.txt`
  into `INPUT/fdca-member-registry.json`.
- `apply_taxonomy.py` remaps known historical drift and refuses invalid
  taxonomy values.
- `enrich_members.py --research` fills missing homepages/descriptions using
  Firecrawl and simple domain checks.
- `enrich_members.py --propose` writes
  `OUTPUT/category-proposals.json` for entries still marked
  `uncategorised`.
- `enrich_members.py --apply` applies filled proposals after checking them
  against the taxonomy.
- `probe_missing.py` tries to find missing FDCA intro-post links from the
  FDCA sitemap.
- `scrape_blog_posts.py` fills or retries article-body text for members with
  an intro-post link.

Do not treat website-only entries as confirmed members. The roster owns
membership status; fdca.fi owns display names and scraped public details.
