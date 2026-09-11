# FDCA Ecosystem Catalogue Development

This folder holds the local source data, maintenance skill, and generated
outputs for the FDCA Ecosystem Catalogue prototype.

This repository is the build project for FDCA's Ecosystem Catalogue. The
project's strategy, decisions, and open questions are tracked in the
`looper` Obsidian vault, in
`50-59-members/52-member-services/ecosystem-catalogue/index.md`.

## Layout

```text
development/
  README.md
  INPUT/
    DESIGN.md
    fdca-categories.json
    fdca-member-list-2026-08-31.txt
    fdca-member-registry.json
  SKILL/
    SKILL.md
    scripts/
      apply_taxonomy.py
      build_dashboard.py
      enrich_members.py
      merge_member_list.py
      probe_missing.py
      scrape_blog_posts.py
  OUTPUT/
    fdca-member-dashboard.html
    category-proposals.json
```

`INPUT/` is tracked source material. `OUTPUT/` is for generated artifacts.
There is intentionally no folder-local `.gitignore`: the member registry is
the current operational dataset and should be visible to git like the other
inputs.

## Current Data State

As of 2026-09-07, `INPUT/fdca-member-registry.json` contains 339 entries:

- 324 `on-roster` entries from FDCA's member roster.
- 15 `website-only` entries listed on fdca.fi but not on the roster. These
  are not confirmed members until FDCA's office resolves them.
- 323 entries categorised against `INPUT/fdca-categories.json`.
- 322 entries with websites. `Stoa Technologies Oy` deliberately has none.
- 323 entries with a usable description.
- 209 FDCA introduction posts with real article text and no stored scrape
  error markers.
- 6 entries carry a `note` field recording the office's answer for why they
  are not (or not yet) on the roster — see the vault's
  `50-59-members/52-member-services/ecosystem-catalogue/index.md` "Pending"
  section for the full 2026-09-07 reconciliation.

16 members approved on 2026-08-31 are roster stubs: name and `roster_status`
only, with no website, category, description, or logo. Run
`enrich_members.py` and `apply_taxonomy.py` to fill them, which is why the
three counts above stop short of 339.

The office resolved 9 of the 18 original `website-only` entries on
2026-09-07: 3 were folded into an existing roster entry under a confirmed
alias (`IQSIGHT` → `Keenfinity Sweden AB`, `Liekkiloukku` → `Fintekra Oy`,
`Oomi Oy` → `Lumme Energia Oy`, all now in `ALIASES` /
`DISPLAY_PRIMARY` in `merge_member_list.py`), 3 were confirmed no longer
members (`Bergmann`, `Logiservice`, `NRT Tietoliikenne`), and 2
(`Rentaload`, `UTU Group`) are confirmed new members still waiting on
billing details before they can be added to the roster file. Applied by
hand against the live file, reusing `fold()` for the three merges — never
by a full `merge_member_list.py` rebuild, which drops `url_status` and
loses any earlier fold's `folded_from` (see the vault's
`member-registry-merge-is-lossy` note).

The roster file has 325 nonblank lines but 324 unique names because
`Convergint Finland Oy` appears twice. `merge_member_list.py` deduplicates
that line by normalised name.

## Skill

The local skill in `SKILL/` packages the scripts that maintain this dataset.
Use it for catalogue data checks, roster reconciliation, enrichment, intro-post
scraping, and dashboard generation.

Normal verification from this folder:

```bash
python3 SKILL/scripts/merge_member_list.py --check
python3 SKILL/scripts/apply_taxonomy.py --check
python3 SKILL/scripts/build_dashboard.py
```

The dashboard build writes `OUTPUT/fdca-member-dashboard.html`.

## Inputs

| File | Role |
|---|---|
| `INPUT/fdca-member-registry.json` | Current local catalogue dataset: roster status, names, category, website, logo, intro-post link, article text, and public description. |
| `INPUT/fdca-member-list-2026-08-31.txt` | FDCA's dated member roster source. It owns official membership names. |
| `INPUT/fdca-categories.json` | Category taxonomy copied from the FDCA website repository so this folder can validate itself. |
| `INPUT/DESIGN.md` | Design tokens used by the dashboard builder. |

## Outputs

| File | Role |
|---|---|
| `OUTPUT/fdca-member-dashboard.html` | Generated single-file dashboard. Rebuild it with `build_dashboard.py`; do not hand-edit. |
| `OUTPUT/category-proposals.json` | Optional generated classification queue from `enrich_members.py --propose`. |

## Maintenance Commands

Run only the command that matches the thing that changed:

```bash
python3 SKILL/scripts/merge_member_list.py --check
python3 SKILL/scripts/merge_member_list.py

python3 SKILL/scripts/apply_taxonomy.py --check
python3 SKILL/scripts/apply_taxonomy.py

python3 SKILL/scripts/enrich_members.py --research
python3 SKILL/scripts/enrich_members.py --propose
python3 SKILL/scripts/enrich_members.py --apply --check
python3 SKILL/scripts/enrich_members.py --apply

python3 SKILL/scripts/probe_missing.py --check
python3 SKILL/scripts/probe_missing.py

python3 SKILL/scripts/scrape_blog_posts.py

python3 SKILL/scripts/build_dashboard.py
```

`probe_missing.py` and `scrape_blog_posts.py` need `requests` and
`beautifulsoup4`. `build_dashboard.py` needs `PyYAML`.
