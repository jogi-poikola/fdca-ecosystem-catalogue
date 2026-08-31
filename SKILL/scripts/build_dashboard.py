#!/usr/bin/env python3
"""
Regenerate OUTPUT/fdca-member-dashboard.html from INPUT/fdca-member-registry.json,
INPUT/fdca-categories.json, and INPUT/DESIGN.md. The output is a single
self-contained HTML file — open it directly in any browser, no server or extra
folder needed. DESIGN.md is a build-time-only input: its tokens are read and
resolved here into literal CSS values baked into the output; the generated
HTML's own JS never loads or fetches DESIGN.md at runtime.

Run after fdca-member-registry.json changes (e.g. after scrape_blog_posts.py
or probe_missing.py, or a manual edit) to bring the dashboard back in sync
with the data — or after editing DESIGN.md's tokens to update the CSS.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
CATEGORIES_PATH = INPUT_DIR / "fdca-categories.json"
DESIGN_PATH = INPUT_DIR / "DESIGN.md"
OUTPUT_PATH = OUTPUT_DIR / "fdca-member-dashboard.html"

FDCA_LOGO = "https://www.fdca.fi/wp-content/uploads/2024/09/FDCA_logo_rgb-400x175.png"

# Matches a design.md-style token reference, e.g. "{colors.blue}" or
# "{typography.h1}". Used both to detect a string that IS a single
# reference (resolves to whatever type the token holds — string, dict,
# int) and, via re.sub below, references embedded inside a larger string
# (e.g. the gradient), which always resolve to their string form.
_TOKEN_REF_RE = re.compile(r"\{([a-zA-Z0-9_.]+)\}")
_TOKEN_REF_FULL_RE = re.compile(r"^\{([a-zA-Z0-9_.]+)\}$")


def _resolve_token_path(path, tokens):
    cur = tokens
    for part in path.split("."):
        cur = cur[part]
    return cur


def _resolve_value(value, tokens):
    """Recursively resolve `{path.to.token}` references inside a parsed
    DESIGN.md front-matter value. A string that is *entirely* one
    reference resolves to the referenced token's native type (so
    "{typography.h1}" yields the whole h1 dict, not a stringified one);
    a reference embedded in a larger string (e.g. the hero gradient)
    is substituted as text."""
    if isinstance(value, str):
        full = _TOKEN_REF_FULL_RE.match(value)
        if full:
            return _resolve_value(_resolve_token_path(full.group(1), tokens), tokens)
        return _TOKEN_REF_RE.sub(
            lambda m: str(_resolve_token_path(m.group(1), tokens)), value
        )
    if isinstance(value, dict):
        return {k: _resolve_value(v, tokens) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(v, tokens) for v in value]
    return value


def load_design_tokens():
    """Read DESIGN.md's YAML front matter and return a dict of resolved
    tokens: colors / typography / rounded / spacing as parsed, plus
    components with every `{path.x}` reference resolved to its literal
    value. This is the single build-time bridge from DESIGN.md's design
    tokens into the generated CSS — DESIGN.md is never read or fetched
    by the generated HTML itself."""
    text = DESIGN_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"{DESIGN_PATH}: no YAML front matter found (expected --- fences)")
    front_matter = yaml.safe_load(match.group(1))

    tokens = {
        key: front_matter[key]
        for key in ("colors", "typography", "rounded", "spacing")
        if key in front_matter
    }
    tokens["components"] = {
        name: {k: _resolve_value(v, tokens) for k, v in comp.items()}
        for name, comp in front_matter.get("components", {}).items()
    }
    return tokens


def generate_css(tokens):
    """Build the dashboard's <style> block contents from resolved
    DESIGN.md tokens. Editing a value in DESIGN.md and re-running
    `python3 build_dashboard.py` is sufficient to update the generated
    CSS — nothing here is hand-tuned independently of the tokens."""
    c = tokens["colors"]
    r = tokens["rounded"]
    sp = tokens["spacing"]
    typ = tokens["typography"]
    comp = tokens["components"]

    hero = comp["hero-header"]
    h1 = hero["typography"]
    subtitle = typ["subtitle"]
    fc = comp["filter-chip"]
    fc_typ = fc["typography"]
    fca = comp["filter-chip-active"]
    fca_typ = fca["typography"]
    sc = comp["subfilter-chip"]
    sc_typ = sc["typography"]
    sca = comp["subfilter-chip-active"]
    sca_typ = sca["typography"]
    card = comp["member-card"]
    card_typ = card["typography"]
    body_typ = typ["body"]
    disc = comp["disclaimer-box"]
    disc_typ = disc["typography"]

    css = """*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --blue:      __C_BLUE__;
  --blue-dark: __C_BLUE_DARK__;
  --blue-mid:  __C_BLUE_MID__;
  --charcoal:  __C_CHARCOAL__;
  --black:     __C_BLACK__;
  --white:     __C_WHITE__;
  --gray-ui:   __C_GRAY_UI__;
  --gray-mid:  __C_GRAY_MID__;
  --gray-bg:   __C_GRAY_BG__;
  --grad:      __GRADIENT__;
}
body { font-family: 'Barlow', -apple-system, sans-serif; background: var(--gray-bg); color: var(--black); }

.l1-header { background: var(--grad); padding: __HERO_PADDING__; text-align: center; }
.l1-header img { height: 44px; margin-bottom: 18px; display: block; margin-left: auto; margin-right: auto; }
.l1-header h1 {
  font-family: __H1_FONT_FAMILY__;
  font-weight: __H1_FONT_WEIGHT__;
  font-size: clamp(26px, 6vw, __H1_FONT_SIZE_MAX__);
  text-transform: uppercase;
  color: var(--white);
  letter-spacing: __H1_LETTER_SPACING__;
  margin-bottom: 8px;
}
.l1-header p { color: rgba(255,255,255,.75); font-size: clamp(13px, 3.5vw, __SUBTITLE_FONT_SIZE_MAX__); }

.l1-filter-bar {
  background: var(--white);
  border-bottom: 2px solid var(--gray-bg);
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 12px 20px;
}
.l1-filter-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.l1-subfilter-inner {
  max-width: 1400px;
  margin: 8px auto 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.l1-filter-btn {
  background: var(--white);
  border: 1.5px solid var(--gray-bg);
  border-radius: __FC_RADIUS__;
  padding: __FC_PADDING__;
  font-family: __FC_FONT_FAMILY__;
  font-size: __FC_FONT_SIZE__;
  font-weight: __FC_FONT_WEIGHT__;
  color: var(--gray-mid);
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.l1-filter-btn:hover { border-color: var(--blue-mid); color: var(--blue); }
.l1-filter-btn.active { background: var(--blue); border-color: var(--blue); color: var(--white); font-weight: __FCA_FONT_WEIGHT__; }
.l1-subfilter-btn {
  background: var(--gray-bg);
  border: 1.5px solid transparent;
  border-radius: __SC_RADIUS__;
  padding: __SC_PADDING__;
  font-family: __SC_FONT_FAMILY__;
  font-size: __SC_FONT_SIZE__;
  font-weight: __SC_FONT_WEIGHT__;
  color: var(--charcoal);
  cursor: pointer;
  white-space: nowrap;
  transition: all .15s;
}
.l1-subfilter-btn:hover { background: rgba(0,61,166,.12); }
.l1-subfilter-btn.active { background: var(--blue-mid); color: var(--white); font-weight: __SCA_FONT_WEIGHT__; }
.l1-count {
  display: inline-block;
  border-radius: __BADGE_RADIUS__;
  padding: 1px 7px;
  font-size: 11px;
  margin-left: 5px;
  background: rgba(0,0,0,.06);
}
.l1-filter-btn.active .l1-count, .l1-subfilter-btn.active .l1-count { background: rgba(255,255,255,.25); }

.l1-content { max-width: 1400px; margin: 0 auto; padding: 32px 20px 80px; }
.disclaimer {
  background: __DISC_BG__;
  border: 1px solid rgba(0,61,166,.15);
  border-radius: __DISC_RADIUS__;
  padding: __DISC_PADDING__;
  font-size: __DISC_FONT_SIZE__;
  color: var(--gray-mid);
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.disclaimer strong { color: var(--blue); }

.l1-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: __GRID_GAP__;
}
.l1-card {
  background: var(--white);
  border: 1.5px solid var(--gray-bg);
  border-radius: __CARD_RADIUS__;
  padding: __CARD_PADDING__;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  cursor: pointer;
  transition: all .2s;
  text-decoration: none;
  color: inherit;
}
.l1-card:hover { border-color: var(--blue); box-shadow: 0 4px 16px rgba(0,61,166,.12); transform: translateY(-2px); }
.l1-card.l1-hidden { display: none; }
.l1-card-logo { width: 80px; height: 52px; object-fit: contain; margin-bottom: 12px; filter: grayscale(20%); }
.l1-card:hover .l1-card-logo { filter: none; }
.l1-card-name { font-family: __CARD_NAME_FONT_FAMILY__; font-size: __CARD_NAME_FONT_SIZE__; font-weight: __CARD_NAME_FONT_WEIGHT__; color: var(--charcoal); line-height: __CARD_NAME_LINE_HEIGHT__; }
.l1-card-desc { display: none; font-size: __BODY_FONT_SIZE__; color: var(--gray-mid); margin-top: 8px; line-height: __BODY_LINE_HEIGHT__; }
.l1-card:hover .l1-card-desc { display: block; }
.l1-card-blog { display: none; margin-top: 8px; font-size: 11px; color: var(--blue); font-weight: 500; }
.l1-card:hover .l1-card-blog { display: inline-block; }
.l1-empty { grid-column: 1 / -1; text-align: center; color: var(--gray-mid); padding: 40px 0; }
"""

    replacements = {
        "__C_BLUE__": c["blue"],
        "__C_BLUE_DARK__": c["blueDark"],
        "__C_BLUE_MID__": c["blueMid"],
        "__C_CHARCOAL__": c["charcoal"],
        "__C_BLACK__": c["black"],
        "__C_WHITE__": c["white"],
        "__C_GRAY_UI__": c["grayUi"],
        "__C_GRAY_MID__": c["grayMid"],
        "__C_GRAY_BG__": c["grayBg"],
        "__GRADIENT__": hero["backgroundColor"],
        "__HERO_PADDING__": hero["padding"],
        "__H1_FONT_FAMILY__": h1["fontFamily"],
        "__H1_FONT_WEIGHT__": str(h1["fontWeight"]),
        "__H1_FONT_SIZE_MAX__": h1["fontSize"],
        "__H1_LETTER_SPACING__": h1["letterSpacing"],
        "__SUBTITLE_FONT_SIZE_MAX__": subtitle["fontSize"],
        "__FC_RADIUS__": fc["rounded"],
        "__FC_PADDING__": fc["padding"],
        "__FC_FONT_FAMILY__": fc_typ["fontFamily"],
        "__FC_FONT_SIZE__": fc_typ["fontSize"],
        "__FC_FONT_WEIGHT__": str(fc_typ["fontWeight"]),
        "__FCA_FONT_WEIGHT__": str(fca_typ["fontWeight"]),
        "__SC_RADIUS__": sc["rounded"],
        "__SC_PADDING__": sc["padding"],
        "__SC_FONT_FAMILY__": sc_typ["fontFamily"],
        "__SC_FONT_SIZE__": sc_typ["fontSize"],
        "__SC_FONT_WEIGHT__": str(sc_typ["fontWeight"]),
        "__SCA_FONT_WEIGHT__": str(sca_typ["fontWeight"]),
        "__BADGE_RADIUS__": r["badge"],
        "__DISC_BG__": disc["backgroundColor"],
        "__DISC_RADIUS__": disc["rounded"],
        "__DISC_PADDING__": disc["padding"],
        "__DISC_FONT_SIZE__": disc_typ["fontSize"],
        "__GRID_GAP__": sp["lg"],
        "__CARD_RADIUS__": card["rounded"],
        "__CARD_PADDING__": card["padding"],
        "__CARD_NAME_FONT_FAMILY__": card_typ["fontFamily"],
        "__CARD_NAME_FONT_SIZE__": card_typ["fontSize"],
        "__CARD_NAME_FONT_WEIGHT__": str(card_typ["fontWeight"]),
        "__CARD_NAME_LINE_HEIGHT__": card_typ["lineHeight"],
        "__BODY_FONT_SIZE__": body_typ["fontSize"],
        "__BODY_LINE_HEIGHT__": body_typ["lineHeight"],
    }
    for placeholder, value in replacements.items():
        css = css.replace(placeholder, value)
    return css


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def load_categories():
    raw = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    categories = []
    known_slugs = set()
    for cat in raw["categories"]:
        subcats = [
            {"slug": s["slug"], "label": s["en"]}
            for s in cat.get("subcategories", [])
        ]
        categories.append({
            "slug": cat["slug"],
            "label": cat["en"],
            "subcats": subcats,
        })
        known_slugs.add(cat["slug"])
    return categories, known_slugs


def load_members(known_category_slugs):
    members_raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    members = []
    skipped = []
    for m in members_raw:
        cat = m.get("category", "")
        if cat not in known_category_slugs:
            skipped.append(m.get("display_name", "?"))
            continue
        desc = m.get("web_search_content") or ""
        if not desc:
            blog = m.get("blog_content") or ""
            desc = blog if not blog.startswith("[") else ""
        members.append({
            "name": m["display_name"],
            "cat": cat,
            "subcat": m.get("subcategory") or "",
            "url": m["url"],
            "blog": m.get("blog_link") or None,
            "logo": m["logo_url"],
            "desc": desc,
        })
    members.sort(key=lambda m: m["name"].lower())
    return members, skipped


def render_html(categories, members, css):
    member_count = len(members)
    category_count = len(categories)

    html = HTML_TEMPLATE
    html = html.replace("__CSS_BLOCK__", css)
    html = html.replace("__MEMBER_COUNT__", str(member_count))
    html = html.replace("__CATEGORY_COUNT__", str(category_count))
    html = html.replace("__CATEGORIES_JSON__", json.dumps(categories, ensure_ascii=False))
    html = html.replace("__MEMBERS_JSON__", json.dumps(members, ensure_ascii=False))
    return html


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FDCA Member Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;700;800&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<!-- Generated by build_dashboard.py from fdca-member-registry.json + fdca-categories.json + DESIGN.md. Do not hand-edit; re-run the builder instead. -->
<style>
__CSS_BLOCK__</style>
</head>
<body>

<div class="l1-header">
  <img src="__FDCA_LOGO__" alt="FDCA">
  <h1>Member Companies</h1>
  <p>Finnish Data Center Association — __MEMBER_COUNT__ member organisations across __CATEGORY_COUNT__ sectors</p>
</div>
<div class="l1-filter-bar">
  <div class="l1-filter-inner" id="l1Filters"></div>
  <div class="l1-subfilter-inner" id="l1Subfilters"></div>
</div>
<div class="l1-content">
  <div class="disclaimer">
    <strong>Note:</strong> Member descriptions below are based on FDCA introduction blog posts and public web sources. Content is informational, not an official FDCA statement.
  </div>
  <div id="l1Grid" class="l1-grid"></div>
</div>

<script>
const categories = __CATEGORIES_JSON__;
const members = __MEMBERS_JSON__;

let activeCat = null;
let activeSubcat = null;

function catBySlug(slug) { return categories.find(c => c.slug === slug); }

function renderFilters() {
  const bar = document.getElementById('l1Filters');
  bar.innerHTML = '';

  const allBtn = document.createElement('button');
  allBtn.className = 'l1-filter-btn' + (activeCat === null ? ' active' : '');
  allBtn.innerHTML = `All <span class="l1-count">${members.length}</span>`;
  allBtn.onclick = () => { activeCat = null; activeSubcat = null; renderFilters(); renderSubfilters(); applyFilter(); };
  bar.appendChild(allBtn);

  categories.forEach(cat => {
    const count = members.filter(m => m.cat === cat.slug).length;
    if (!count) return;
    const btn = document.createElement('button');
    btn.className = 'l1-filter-btn' + (activeCat === cat.slug ? ' active' : '');
    btn.innerHTML = `${cat.label} <span class="l1-count">${count}</span>`;
    btn.onclick = () => { activeCat = cat.slug; activeSubcat = null; renderFilters(); renderSubfilters(); applyFilter(); };
    bar.appendChild(btn);
  });
}

function renderSubfilters() {
  const bar = document.getElementById('l1Subfilters');
  bar.innerHTML = '';
  if (!activeCat) return;
  const cat = catBySlug(activeCat);
  if (!cat || !cat.subcats.length) return;

  const availableSubcats = cat.subcats.filter(sc =>
    members.some(m => m.cat === activeCat && m.subcat === sc.slug)
  );
  if (!availableSubcats.length) return;

  const allBtn = document.createElement('button');
  allBtn.className = 'l1-subfilter-btn' + (activeSubcat === null ? ' active' : '');
  const allCount = members.filter(m => m.cat === activeCat).length;
  allBtn.innerHTML = `All ${cat.label} <span class="l1-count">${allCount}</span>`;
  allBtn.onclick = () => { activeSubcat = null; renderSubfilters(); applyFilter(); };
  bar.appendChild(allBtn);

  availableSubcats.forEach(sc => {
    const count = members.filter(m => m.cat === activeCat && m.subcat === sc.slug).length;
    const btn = document.createElement('button');
    btn.className = 'l1-subfilter-btn' + (activeSubcat === sc.slug ? ' active' : '');
    btn.innerHTML = `${sc.label} <span class="l1-count">${count}</span>`;
    btn.onclick = () => { activeSubcat = sc.slug; renderSubfilters(); applyFilter(); };
    bar.appendChild(btn);
  });
}

function renderGrid() {
  const grid = document.getElementById('l1Grid');
  grid.innerHTML = '';
  members.forEach(m => {
    const card = document.createElement('a');
    card.className = 'l1-card';
    card.href = m.url;
    card.target = '_blank';
    card.rel = 'noopener';
    card.dataset.cat = m.cat;
    card.dataset.subcat = m.subcat;
    card.innerHTML = `
      <img class="l1-card-logo" src="${m.logo}" alt="${m.name}" onerror="this.style.display='none'">
      <div class="l1-card-name">${m.name}</div>
      <div class="l1-card-desc">${m.desc}</div>
      ${m.blog ? `<span class="l1-card-blog">↗ Read intro post</span>` : ''}
    `;
    grid.appendChild(card);
  });
}

function applyFilter() {
  document.querySelectorAll('.l1-card').forEach(c => {
    const catMatch = !activeCat || c.dataset.cat === activeCat;
    const subMatch = !activeSubcat || c.dataset.subcat === activeSubcat;
    c.classList.toggle('l1-hidden', !(catMatch && subMatch));
  });
}

renderFilters();
renderSubfilters();
renderGrid();
applyFilter();
</script>
</body>
</html>
"""

HTML_TEMPLATE = HTML_TEMPLATE.replace("__FDCA_LOGO__", FDCA_LOGO)


def main():
    categories, known_slugs = load_categories()
    members, skipped = load_members(known_slugs)
    tokens = load_design_tokens()
    css = generate_css(tokens)

    if skipped:
        print(f"Skipped {len(skipped)} members with unknown category: {skipped}")

    html = render_html(categories, members, css)

    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(members)} members, {len(categories)} categories)")


if __name__ == "__main__":
    main()
