# FDCA Ecosystem Catalogue

This repository is the source of truth for the FDCA Ecosystem Catalogue. It
contains the member roster, category taxonomy, classification rules,
maintenance scripts and generated dashboard. The Looper vault contains only
read-only mirrors of the important semantic files.

## Canonical data

| File | Role |
|---|---|
| `INPUT/fdca-member-registry.json` | Company records. Each company stores one primary category slug. |
| `INPUT/fdca-member-list-2026-10-17.txt` | Dated FDCA roster and source for official membership names. It is the 2026-09-21 roster (kept as FDCA sent it) plus Kumorion Platforms Oy and the 16 applicants the board approved on 2026-10-17. |
| `INPUT/fdca-categories.json` | Stable family/category slugs and bilingual names and short descriptions. |
| `INPUT/fdca-classification-rules.json` | Machine-applicable evidence order, decision sequences, exclusions and tie-breaks. |
| `INPUT/company-category-classification-rules.md` | Generated human-readable guide; never edit by hand. |
| `INPUT/DESIGN.md` | Palette, family colours, typography and dashboard interaction/layout decisions. |

The taxonomy owns meaning. `DESIGN.md` owns presentation. The registry stores
one primary category; family membership is derived from the taxonomy and is
not a second tag.

## Current data state

As of 2026-10-17, FDCA has **384 members**. That is the number to quote. The
registry holds 396 records, because it also keeps 12 companies that are on no
line of the dated roster:

- 384 records from FDCA's dated roster (`on-roster`): the members;
- 3 records marked `roster_status: applicant`: Daniel Raks Oy, Nordic Kosovo
  Contractors LLC and Solkei Electronics Oy. They applied for membership, and
  the board deferred their applications on 2026-10-17 to ask them questions.
  Their 2026-10-06 research stays in the registry, but the dashboard, the
  layout and the member count leave them out;
- 9 records marked `roster_status: former`. They stay in the registry with
  their research, but the dashboard, the layout and the member count leave them
  out:
  - Bergmann, Logiservice and NRT Tietoliikenne, which FDCA's office confirmed
    are no longer members;
  - Auramarine, Gloriosa Finland, GS Yuasa Battery Europe, Uptime Institute,
    Virtutect and Ynvolve, marked former on 2026-09-26 because they are on no
    roster line and not on fdca.fi's members page. The office has not confirmed
    these six;
- no `website-only` (pending) records remain;
- 396 valid primary-category assignments;
- zero publish-time `uncategorised` records.

The dashboard therefore lists 384 companies and states 384 members.

The 2026-10-17 roster adds to the 2026-09-26 roster the 16 applicants the
board approved on 2026-10-17. They use the company names from the
applications. Their homepages, descriptions and categories come from web
research on 2026-10-06. One record carries a `note` with an open question:

- `BIS Coatings OY`: business ID 3524268-3. It is very likely part of the
  Irish BIS Coatings Ltd. Its category, `other_construction`, is medium
  confidence, because industrial coatings fit no specific category.

A category review on 2026-10-17 moved 12 companies, each to the category its
own website supports: Fortum to `energy`; EKE-Rakennus to
`industrial_construction`; Nova Complex to `data_center_operators` (it builds
its own campuses in Loviisa and Kouvola, like Pure DC and Hyperco); Finkova and
Zauner to `technical_systems_installation`; Pylon to `other_construction`;
Hytrade to `automation_software`; Axians to `computing_network_equipment`;
U-Cont to `power_equipment`; and Heras, Pur-ait and Vepe to
`security_technology`, with Nordpel. Finsbury Infrastructure stays in
`site_development`: it develops data-centre campuses and may transfer or lease
them, and it operates none.

Two records carry a standing decision in their `note`, so a later review does
not move them again:

- `Infra ry` stays in `infrastructure_construction`. It is the association of
  the infrastructure construction companies and belongs with them, although
  the rules list associations under `other_services`. Reviews have tried to
  move it twice; do not.
- `Etha Oy` stays in `site_development`: it develops energy and data-centre
  projects for clients.

fdca.fi introduced BAC and Moi Food Solutions in October 2026. They are not new
members: they are the brands of the roster's `Baltimore Aircoil International NV`
and `NAME COMPANY OY` (Moi Food Solutions is its auxiliary name since
2026-09-22). `ALIASES` maps each brand to its roster line.

The 2026-09-26 roster adds Kumorion Platforms Oy to the 2026-09-21 roster. fdca.fi's
members page shows its logo, FDCA staff counted 368 members that day, and
no other company accounts for the difference. Its public brand is `Kumorion`.
Its category, `automation_software`, is a medium-confidence judgment: it
supplies a cloud platform software layer and no hardware.

The 2026-09-21 roster adds 37 new members and lists Abloy, Balanus,
L2 Paloturvallisuus, Rentaload, Usva Energia and UTU, which the 2026-08-31
roster did not. Its line `Hensei Partners Oy nyk. FCDC` is the former name of
`FCDC Corp Oy` and is folded into that record. The website entry
`Glesys Finland Oy` is the brand of the roster's `Oulun DataCenter Oy` and is
folded into that record under the public name `Glesys Finland Oy`.

The former total of 339 counted `KSBR` and
`Keski-Suomen Betonirakenne Oy` separately. They are now folded into one
record under the public name `KSBR`.

## Generated outputs

| File | Role |
|---|---|
| `OUTPUT/index.html` | Self-contained Map/List dashboard; generated by `build_dashboard.py`. |
| `OUTPUT/layout.json` | Solved landscape cell geometry and diagnostics. |
| `OUTPUT/layout-portrait.json` | Independently solved portrait cell geometry and diagnostics. |
| `OUTPUT/category-summary.md` | Bilingual category descriptions and current company counts. |
| `OUTPUT/category-classification-v4.json` | Taxonomy 4.0 classification evidence for human review. |
| `OUTPUT/category-proposals.json` | Optional versioned intake queue generated by `enrich_members.py --propose`. |
| `OUTPUT/logo-review.json` | Logo review queue generated by `fetch_logos.py --review`. |
| `OUTPUT/logo-review.html` | Contact sheet of logo candidates, rendered with the dashboard's greyscale filter. |

## Normal verification

Run from the repository root:

```bash
python3 SKILL/scripts/merge_member_list.py --check
python3 SKILL/scripts/apply_taxonomy.py --check
python3 SKILL/scripts/validate_catalogue.py --check
python3 SKILL/scripts/build_dashboard.py
```

`validate_catalogue.py` checks taxonomy structure, bilingual descriptions,
rule coverage, category validity, publishability and design-family coverage.
Without `--check`, it also regenerates the human-readable decision guide and
category summary.

## Layout workbench

Use the browser workbench to compare live solver output side by side without
modifying the production configuration:

```bash
python3 SKILL/scripts/layout_tool.py --serve
```

Each policy set shows the real production cell geometry for landscape and
portrait side by side, using lightweight member placeholders instead of
logos. English, Finnish and bilingual labels are available. The controls cover
family geometry, all solver strategies, empty-category behavior, all headroom
modes, ordering, language geometry, typography, stability, reflow simulation,
short labels and automatic layout selection. Every control includes its
meaning and tradeoff. Landscape and portrait have separate absolute-slot
diagnostics; clicking a metric highlights those exact grid slots. “Search
algorithms → B” benchmarks deterministic positioning strategies across both
masters and loads the best valid candidate into the comparison pane. A
terminal comparison remains available for automation:

```bash
python3 SKILL/scripts/layout_tool.py --compare layout_mode rectangular polyomino
```

## Maintenance workflows

```bash
# Reconcile a new dated roster. A merge that changes the registry also
# validates, rebuilds the dashboard and runs the Looper mirror command in
# LOOPER_MIRROR_CMD. Set it once, e.g. in your shell profile.
python3 SKILL/scripts/merge_member_list.py --check
python3 SKILL/scripts/merge_member_list.py

# Then decide each entry the roster does not name: alias, former or member.
# Add the printed line to ALIASES or FORMER_NOTES and merge again.
python3 SKILL/scripts/audit_roster.py

# Research and classify new intake records.
python3 SKILL/scripts/enrich_members.py --research
python3 SKILL/scripts/enrich_members.py --propose
python3 SKILL/scripts/enrich_members.py --apply --check
python3 SKILL/scripts/enrich_members.py --apply

# Refresh source material and rebuild.
python3 SKILL/scripts/probe_missing.py --check
python3 SKILL/scripts/scrape_blog_posts.py

# Logos: fdca.fi is the master; homepage logos only where fdca.fi has none.
python3 SKILL/scripts/fetch_logos.py --fdca
python3 SKILL/scripts/fetch_logos.py --review
python3 SKILL/scripts/fetch_logos.py --confirm
python3 SKILL/scripts/fetch_logos.py --verify

# Validate and rebuild.
python3 SKILL/scripts/validate_catalogue.py
python3 SKILL/scripts/build_dashboard.py
```

Classification proposals carry both taxonomy and rules versions. Applying a
stale queue is rejected. A low-confidence proposal requires explicit human
review. `uncategorised` is permitted only as an intake state and fails normal
publication validation.

`fetch_logos.py --fdca` writes FDCA's own logo for every member the fdca.fi
members page covers. `--review` collects candidates from each remaining
member's homepage into a queue and a contact sheet; a person sets each row's
`pick`, and `--confirm` applies it. A white-only logo is served through the
images.weserv.nl proxy with its colours negated, so it shows on the light
dashboard cards.

`probe_missing.py`, `scrape_blog_posts.py` and `fetch_logos.py` need `requests` and
`beautifulsoup4`. The dashboard and validator need `PyYAML`.
