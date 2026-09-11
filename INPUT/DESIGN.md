---
version: "beta"
name: "FDCA Member Dashboard"
description: "Design tokens for build_dashboard.py's generated dashboard — a self-contained pan/zoom Map view and a sectioned List view over the same five-family taxonomy."
colors:
  blue: "#003DA6"          # Links, "All categories" chrome, detail-panel category tag
  blueDark: "#020381"      # Masthead ink/wordmark, detail-panel company name
  blueMid: "#2874FC"       # Link hover
  charcoal: "#32373C"      # Base text ink
  white: "#FFFFFF"         # Card, panel, and tile surfaces
  canvasBg: "#F4F5F7"      # Page / map canvas background
  panelBorder: "#E4E7EC"   # Card, block, and detail-panel borders
  sectionBorder: "#EDEFF2" # List-view sticky section header border, divider rules
  pillBg: "#F0F1F4"        # Resting background for the Map/List pill toggle and jump-sheet rows
  muted: "#7A828C"         # Secondary chrome text (jump-sheet counts, search icon)
  secondaryText: "#6B7280" # Tile/row description text
  warn: "#B0663C"          # Website-only / pending-membership notice in the detail panel
typography:
  wordmark:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontWeight: 800
  blockHeader:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontWeight: 800
  subLabel:
    fontFamily: "'Barlow Condensed', sans-serif"
    fontWeight: 700
  body:
    fontFamily: "'Barlow', -apple-system, sans-serif"
    fontWeight: 400
  label:
    fontFamily: "'Barlow', sans-serif"
    fontWeight: 600
---

## Overview

The FDCA Member Dashboard is a single self-contained HTML file — generated
by `build_dashboard.py` from `fdca-member-registry.json` and
`fdca-categories.json` — with two views of the same 323 categorised members:
a pannable, zoomable **Map** (the default) and a sectioned **List**. It has
no build step and no external dependency beyond Google Fonts; open the
output file directly in a browser, no server needed.

Unlike the flat 9-category card grid this replaced, almost none of the
dashboard's layout is expressed as CSS rules. The Map view's block and tile
positions are the output of an integer-cell treemap packer that runs in the
browser at load time and on resize — every family block, subcategory
sub-box, and member tile gets an explicit computed `x/y/w/h` in pixels, not
a CSS Grid or flexbox arrangement. Font sizes inside a block are solved the
same way: the builder tries decreasing sizes until the label or paragraph
fits the block's actual height. This is why the strict `components:` token
schema used by the previous single-view dashboard doesn't fit here — colors
below are read directly by the packer's JS, not applied through CSS classes.

## Family color

Each of the five top-level families in `fdca-categories.json` carries a
`hue` (an OKLCH hue angle) and a `chromaK` (0–1, how far that hue's blocks
and tiles are pushed toward its own sRGB gamut ceiling — a raw chroma value
that reads vivid at one hue reads muddy or clips out of gamut at another, so
each hue needs its own ceiling, not one shared number). Both are read
straight from that file; nothing here duplicates them.

`build_dashboard.py`'s JS derives every family-colored surface from a single
`{h, k}` pair through six fixed OKLCH roles — `surface`/`group` (block and
sub-box fill), `border`/`groupBorder`, `ink` (label text), and `mark` (dot
tint at the lowest zoom tier) — each a fixed `[lightness, chroma-fraction]`
pair scaled by that family's `k` and gamut-clamped per hue. A seventh and
eighth role, `chip`/`chipOn`, color the "Jump to" sheet's category rows the
same way. No family needs a hand-picked hex anywhere; adding a family means
adding one `{slug, hue, chromaK}` entry to the taxonomy.

The five shipped hues, ≥30° apart so no two families read as the same
color: `data_center_operators` 170 (teal, k 0.72), `technology_vendors` 300
(violet, k 0.94), `construction` 15 (red-orange, k 0.95), `services` 100
(olive, k 0.62), `planning` 232 (blue, k 0.98). `colors.blue` itself is
reserved for chrome (links, the pill toggle, the "All categories" jump-sheet
row) and is never used as a family hue.

## Typography

Two font families, loaded from Google Fonts
(`Barlow Condensed:wght@600;700;800` and `Barlow:wght@400;500;600`):

- **`typography.wordmark`** — Barlow Condensed 800. The "FDCA" mark in the
  masthead block, sized to roughly a fifth of that block's own height so it
  scales with the treemap rather than sitting at a fixed pixel size.
- **`typography.blockHeader`** — Barlow Condensed 800, uppercase. Each
  family block's header (name + member count), solved down from the block's
  available width until the longest word fits without wrapping past the
  block's header row.
- **`typography.subLabel`** — Barlow Condensed 700, uppercase, 70% opacity
  ink. A subcategory sub-box's label, floored at 70% of the largest sibling
  label's size on the same canvas so no narrow sub-box shrinks its label
  into a smudge.
- **`typography.body`** — Barlow 400. Tile/row descriptions and the
  masthead paragraph, both solved the same way as the headers: decreasing
  size until the text fits the room actually available.
- **`typography.label`** — Barlow 600. Tile and row company names, the
  detail panel's field labels, and the jump-sheet's category rows.

Font sizing is entirely a function of the block or tile's own computed
pixel size, never a fixed breakpoint — this is deliberate: the same "family
of a dozen sizes, all solved the same way" rule applies whether the canvas
is 2000px wide on a desktop or 500px wide on a phone.

## Layout: the treemap packer

`layout()` builds one integer-cell grid per canvas: it lays out five
family blocks (plus a masthead block sized to match the Data Center
Operators block beside it) using a recursive area-proportional split
(`tileInt`), sized so each block's cell count matches its member count
(plus room for its own sub-box packing, `packCat`), then repeats block
sizing for a few passes so a family that needed more room than its first
guess settles into its real shape. Operators is pinned top-left; the
masthead sits beside it at a fixed width fraction of the canvas; everything
else packs largest-to-smallest into the remaining band. A member tile is a
fixed `168×190px` cell (`CELL_W`/`CELL_H`) plus a `14px` gap and `7px`
inset (`GAP`/`TIN`) — the packer places whole cells, never a fractional
tile, so nothing can straddle the grid.

## Zoom tiers

The Map view is pannable and zoomable (pointer drag, wheel, pinch), and a
tile's own detail is a function of the current zoom level, not a separate
setting: `dot` (zoomed out — a colored dot per member, no logos) below
`0.2`, `logo` (logo only) below `0.5`, `name` (logo + company name) below
`0.95`, and `card` (logo + name + description + host, the full row-card
detail) above that. This keeps ~320 members legible at every zoom level
without a separate "detail" toggle.

## List view

The List view groups the same data into sticky-headed family sections and,
within each, subcategory groups — a member whose subcategory is blank falls
into that family's synthesized "Other services"/"Other construction"/"Other
technology" group. Below `700px` viewport width the grid becomes a single
column of taller row-cards with a visible description; at or above it, a
denser multi-column grid of compact square cards.

## Detail panel

Clicking a tile or row opens a slide-in panel with the company's display
name, official name (when they differ), category/subcategory tags, full
description, website, and — for a `website-only` roster entry — an amber
pending-membership notice (`colors.warn`) rather than presenting it as a
confirmed member.

## Do's and Don'ts

**Do**
- Do keep every block/tile dimension and font size as a JS-computed pixel
  value tied to the canvas's actual size — never hardcode a size that only
  happens to look right at one viewport width.
- Do add a new family by adding one `{slug, hue, chromaK}` entry to
  `fdca-categories.json`, not by hand-picking a hex color here.
- Do keep the zoom tiers a pure function of `this.v.k` (the current zoom
  scale) — never a separate, independently-toggleable "detail level".

**Don't**
- Don't reintroduce a CSS Grid/flexbox layout for the Map view's blocks or
  tiles — their positions are treemap output, not CSS-expressible without
  duplicating the packer in CSS.
- Don't add a sixth family hue within 30° of an existing one; the OKLCH
  gamut-clamp already pushes each hue as far as it safely can go, so two
  close hues will read as the same color once clamped.
