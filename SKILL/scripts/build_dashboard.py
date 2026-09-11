#!/usr/bin/env python3
"""
Regenerate OUTPUT/index.html from INPUT/fdca-member-registry.json,
INPUT/fdca-categories.json, and INPUT/DESIGN.md. The output is a single
self-contained HTML file — open it directly in any browser, no server or
extra folder needed.

The page is a pannable, zoomable Map view (the default) plus a sectioned
List view, both over the same five-family taxonomy. Map block/tile
positions are NOT CSS — they are the output of an integer-cell treemap
packer that runs in the browser (ported from a hand-built reference; see
INPUT/DESIGN.md "Layout: the treemap packer"), so block sizes always match
each family's real member count and font sizes are solved to fit the space
actually available, at any viewport size. DESIGN.md holds the flat color
palette and per-family hue/chromaK lives in fdca-categories.json; neither
is a CSS class — both are embedded as data and read directly by the page's
own JS.

Run after fdca-member-registry.json changes (e.g. after scrape_blog_posts.py
or probe_missing.py, or a manual edit) to bring the dashboard back in sync
with the data — or after editing DESIGN.md's colors.
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
OUTPUT_PATH = OUTPUT_DIR / "index.html"

FDCA_LOGO = "https://www.fdca.fi/wp-content/uploads/2024/09/FDCA_logo_rgb-400x175.png"

# Display label for the blank-subcategory bucket within a family that has
# subcategories. Families with no subcategories (data_center_operators) or
# whose members always carry a subcategory (planning, after the five-family
# migration) never need one.
OTHER_LABEL = {
    "technology_vendors": "Other technology",
    "construction": "Other construction",
    "services": "Other services",
}

_TOKEN_REF_RE = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


def load_design_tokens():
    """Read DESIGN.md's YAML front matter: colors + typography only — the
    page's layout is computed by its own JS (see module docstring), so
    there is no `components:` block to resolve here anymore."""
    text = DESIGN_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"{DESIGN_PATH}: no YAML front matter found (expected --- fences)")
    front_matter = yaml.safe_load(match.group(1))
    return {
        key: front_matter[key]
        for key in ("colors", "typography")
        if key in front_matter
    }


def generate_css(colors):
    """The only real CSS the page ships: reset, scrollbar, link colors, and
    the panel/sheet entrance keyframes. Everything else is inline, JS-set
    styling — see the module docstring."""
    css = """*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: __C_CANVAS_BG__; }
body { font-family: 'Barlow', -apple-system, sans-serif; color: __C_CHARCOAL__; }
a { color: __C_BLUE__; text-decoration: none; }
a:hover { color: __C_BLUE_MID__; text-decoration: underline; }
input, button { font-family: 'Barlow', sans-serif; }
button { -webkit-tap-highlight-color: transparent; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: __C_PANEL_BORDER__; border-radius: 8px; }
.nobar::-webkit-scrollbar { height: 0; width: 0; }
@keyframes panelIn { from { transform: translateX(12px); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes panelBody { from { transform: translateY(6px); opacity: 0; } to { transform: none; opacity: 1; } }
@keyframes sheetIn { from { transform: translateY(20px); opacity: 0; } to { transform: none; opacity: 1; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .001s !important; transition-duration: .001s !important; } }
"""
    return (
        css.replace("__C_CANVAS_BG__", colors["canvasBg"])
        .replace("__C_CHARCOAL__", colors["charcoal"])
        .replace("__C_BLUE__", colors["blue"])
        .replace("__C_BLUE_MID__", colors["blueMid"])
        .replace("__C_PANEL_BORDER__", colors["panelBorder"])
    )


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
            "hue": cat.get("hue", 235),
            "chromaK": cat.get("chromaK", 0.8),
            "subcats": subcats,
            "otherLabel": OTHER_LABEL.get(cat["slug"]),
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
            "official": m.get("official_name") or m["display_name"],
            "cat": cat,
            "subcat": m.get("subcategory") or "",
            "url": m["url"],
            "blog": m.get("blog_link") or None,
            "logo": m["logo_url"],
            "desc": desc,
            "rosterStatus": m.get("roster_status") or "",
        })
    members.sort(key=lambda m: m["name"].lower())
    return members, skipped


def render_html(categories, members, css, colors):
    html = HTML_TEMPLATE
    html = html.replace("__CSS_BLOCK__", css)
    html = html.replace("__MEMBER_COUNT__", str(len(members)))
    html = html.replace("__CATEGORIES_JSON__", json.dumps(categories, ensure_ascii=False))
    html = html.replace("__MEMBERS_JSON__", json.dumps(members, ensure_ascii=False))
    html = html.replace("__COLORS_JSON__", json.dumps(colors, ensure_ascii=False))
    html = html.replace("__FDCA_LOGO__", FDCA_LOGO)
    return html


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FDCA Member Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<!-- Generated by build_dashboard.py from fdca-member-registry.json + fdca-categories.json + DESIGN.md. Do not hand-edit; re-run the builder instead. Map/List layout is computed by this page's own JS, not CSS — see INPUT/DESIGN.md. -->
<style>
__CSS_BLOCK__</style>
</head>
<body>

<div id="stage" style="position:fixed; inset:0; display:flex; flex-direction:column; overflow:hidden;">
  <div id="stageInner" style="position:relative; flex:1; min-height:0;">

    <div style="position:absolute; top:14px; left:50%; transform:translateX(-50%); z-index:45; display:flex; align-items:center; gap:7px; background:#FFFFFF; border:1.5px solid var(--panel-border); border-radius:24px; padding:5px; box-shadow:0 6px 22px rgba(2,3,129,.12);">
      <div style="display:flex; align-items:center; gap:3px; background:var(--pill-bg); border-radius:18px; padding:3px;">
        <button id="mapTab" type="button" style="border:none; border-radius:15px; font-family:Barlow,sans-serif; font-size:13.5px; font-weight:700; letter-spacing:.02em; cursor:pointer; height:30px; padding:0 16px;">Map</button>
        <button id="listTab" type="button" style="border:none; border-radius:15px; font-family:Barlow,sans-serif; font-size:13.5px; font-weight:700; letter-spacing:.02em; cursor:pointer; height:30px; padding:0 16px;">List</button>
      </div>
      <button id="jumpBtn" type="button" aria-label="Jump to a category" style="display:flex; align-items:center; gap:7px; height:32px; max-width:260px; padding:0 14px; border:none; border-radius:18px; background:transparent; cursor:pointer; font:inherit;">
        <span id="jumpLabel" style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13.5px; font-weight:600; color:var(--charcoal);">All categories</span>
        <span style="flex:none; font-size:11px; color:var(--muted);">&#9662;</span>
      </button>
    </div>

    <div id="viewport" style="position:absolute; inset:0; overflow:hidden; cursor:grab; touch-action:none; background-color:var(--canvas-bg);">
      <div id="wrap" style="position:absolute; top:0; left:0; transform-origin:0 0;"></div>
    </div>

    <div id="listPane" style="position:absolute; inset:0; overflow-y:auto; overflow-x:hidden; display:none; touch-action:pan-y; background:var(--canvas-bg); padding:0 0 40px;"></div>

    <aside id="detailPanel" data-detail-panel="1" style="position:absolute; top:0; right:0; bottom:0; width:380px; max-width:100%; background:#FFFFFF; border-left:1.5px solid var(--panel-border); box-shadow:-12px 0 34px rgba(2,3,129,.10); z-index:60; display:none; flex-direction:column; animation:panelIn .2s cubic-bezier(.2,0,0,1) both;"></aside>
    <aside id="categoryPanel" data-cat-panel="1" style="position:absolute; top:0; right:0; bottom:0; width:380px; max-width:100%; background:#FFFFFF; border-left:1.5px solid var(--panel-border); box-shadow:-12px 0 34px rgba(2,3,129,.10); z-index:60; display:none; flex-direction:column; animation:panelIn .2s cubic-bezier(.2,0,0,1) both;"></aside>

    <div id="zoomBar" style="position:absolute; left:50%; bottom:18px; transform:translateX(-50%); z-index:50; display:none; align-items:center; gap:7px; background:#FFFFFF; border:1.5px solid var(--panel-border); border-radius:26px; padding:6px; box-shadow:0 10px 30px rgba(2,3,129,.13);">
      <button id="zoomOutBtn" type="button" aria-label="Zoom out" style="border:1.5px solid var(--panel-border); background:#FFFFFF; border-radius:50%; width:32px; height:32px; font-size:16px; color:var(--charcoal); cursor:pointer; line-height:1;">&minus;</button>
      <button id="zoomInBtn" type="button" aria-label="Zoom in" style="border:1.5px solid var(--panel-border); background:#FFFFFF; border-radius:50%; width:32px; height:32px; font-size:16px; color:var(--charcoal); cursor:pointer; line-height:1;">+</button>
      <div style="width:1px; height:22px; background:var(--panel-border);"></div>
      <button id="fitBtn" type="button" aria-label="Fit the whole map" style="border:1.5px solid var(--panel-border); background:#FFFFFF; border-radius:50%; width:32px; height:32px; font-size:16px; color:var(--charcoal); cursor:pointer; line-height:1;">&#10530;</button>
    </div>

    <div id="sheetOverlay" style="position:absolute; inset:0; z-index:70; display:none; flex-direction:column; justify-content:flex-end; background:rgba(2,3,129,.28);">
      <button id="sheetDismiss" type="button" style="flex:1 1 auto; border:none; background:transparent; cursor:pointer; min-height:60px;"></button>
      <div style="flex:0 1 auto; display:flex; flex-direction:column; min-height:0; max-height:76%; background:#FFFFFF; border-radius:20px 20px 0 0; box-shadow:0 -12px 40px rgba(2,3,129,.2); animation:sheetIn .22s cubic-bezier(.2,0,0,1) both;">
        <div style="display:flex; align-items:center; gap:12px; padding:16px 18px 12px; border-bottom:1.5px solid var(--section-border); flex:none;">
          <span style="font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:20px; letter-spacing:.03em; text-transform:uppercase; color:var(--blue-dark); margin-right:auto;">Jump to</span>
          <button id="sheetClose" type="button" aria-label="Close" style="border:none; background:var(--pill-bg); border-radius:50%; width:36px; height:36px; font-size:19px; line-height:1; color:var(--muted); cursor:pointer;">&times;</button>
        </div>
        <div id="sheetList" style="overflow-y:auto; padding:8px 12px 22px; display:flex; flex-direction:column; gap:2px;"></div>
      </div>
    </div>

  </div>
</div>

<script>
const categories = __CATEGORIES_JSON__;
const members = __MEMBERS_JSON__;
const COLORS = __COLORS_JSON__;
const FDCA_LOGO = "__FDCA_LOGO__";

document.documentElement.style.setProperty('--panel-border', COLORS.panelBorder);
document.documentElement.style.setProperty('--section-border', COLORS.sectionBorder);
document.documentElement.style.setProperty('--pill-bg', COLORS.pillBg);
document.documentElement.style.setProperty('--muted', COLORS.muted);
document.documentElement.style.setProperty('--charcoal', COLORS.charcoal);
document.documentElement.style.setProperty('--canvas-bg', COLORS.canvasBg);
document.documentElement.style.setProperty('--blue-dark', COLORS.blueDark);

const BLANK = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
const FALLBACK_TONE = { h: 262, k: 0.30 };
const TONE = {};
categories.forEach(c => { TONE[c.slug] = { h: c.hue, k: c.chromaK }; });
const toneOf = slug => TONE[slug] || FALLBACK_TONE;

// Every family color is one of these fixed OKLCH roles on the family's own
// hue — see INPUT/DESIGN.md "Family color". [lightness, chroma-fraction].
const ROLE = {
  surface: [0.972, 0.019], group: [0.992, 0.010], border: [0.880, 0.048],
  groupBorder: [0.930, 0.026], ink: [0.415, 0.115], mark: [0.620, 0.115],
  chip: [0.965, 0.024], chipOn: [0.905, 0.070], chipBd: [0.900, 0.040],
  chipBdOn: [0.630, 0.120], subInk: [0.500, 0.085]
};
const _fits = (L, C, h) => {
  const a = C * Math.cos(h * Math.PI / 180), b = C * Math.sin(h * Math.PI / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
               -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
               -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
  return rgb.every(u => { const v = u <= 0.0031308 ? 12.92 * u : 1.055 * Math.pow(Math.max(u, 0), 1 / 2.4) - 0.055; return v >= -0.001 && v <= 1.001; });
};
const _cache = {};
const roleColor = (T, name) => {
  const key = T.h + '|' + T.k + '|' + name;
  if (_cache[key]) return _cache[key];
  const r = ROLE[name];
  let c = r[1] * T.k;
  if (!_fits(r[0], c, T.h)) { let lo = 0, hi = c; for (let i = 0; i < 22; i++) { const mid = (lo + hi) / 2; if (_fits(r[0], mid, T.h)) lo = mid; else hi = mid; } c = lo * 0.94; }
  return (_cache[key] = 'oklch(' + r[0] + ' ' + (Math.round(c * 1000) / 1000) + ' ' + T.h + ')');
};

const CELL_W = 168, CELL_H = 190, GAP = 14, TIN = 7, PITCH_X = CELL_W + GAP + TIN * 2, PITCH_Y = CELL_H + GAP + TIN * 2, CELL_RATIO = PITCH_Y / PITCH_X, PIN = 'data_center_operators';
const NARROW = 700;
const initialsOf = n => n.replace(/\b(oy|ab|ltd|oyj|inc|group|finland|as|plc|corp)\b/gi, ' ').trim().split(/[\s-]+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
function hostOf(u) { if (!u) return ''; try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return u.replace(/^https?:\/\//, '').replace(/\/.*$/, ''); } }
function clipTo(s, n) { if (!s) return ''; return s.length <= n ? s : s.slice(0, n).replace(/[\s,;:.]+\S*$/, '') + '…'; }
function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }

class Dash {
  constructor() {
    this.state = { q: '', sel: null, catPanel: null, tier: 'logo', view: null, vw: 0, vh: 0, autoFormat: null, focusCat: null, focusSub: null, sheetOpen: false };
    this.v = { x: 0, y: 0, k: 1 };
    this.broken = {};
    this.dragged = false;
    this._layout = null; this._layoutKey = null; this._cats = null;
    this.bound = false;
    // Public comments — fetched once from the Netlify Function backend
    // (netlify/functions/comments.mjs) and kept in sync locally as people
    // post; see commentsFor()/postComment(). Empty until loadComments()
    // resolves, so the page still renders fine standalone (e.g. a local
    // file:// preview with no backend to fetch from).
    this.comments = { companies: {}, categories: {} };
  }

  isNarrow() { return !!(this.state.vw && this.state.vw < NARROW); }
  view() { return this.state.view || (this.isNarrow() ? 'list' : 'map'); }
  listMode() { return this.view() !== 'map'; }
  fmt() { return this.state.autoFormat || 'wide'; }

  setState(patch, cb) { Object.assign(this.state, patch); this.render(); if (cb) cb(); }

  matches(m, q) {
    if (!q) return true;
    return (m.name + ' ' + (m.official || '') + ' ' + (m.desc || '') + ' ' + m.cat + ' ' + (m.subcat || '')).toLowerCase().indexOf(q) >= 0;
  }

  select(m) { if (this.dragged) { this.dragged = false; return; } this.setState({ sel: m, catPanel: null }); }

  loadComments() {
    fetch('/api/comments')
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (data) { this.comments = data; this.render(); } })
      .catch(() => {}); // no backend reachable (e.g. a local file:// preview) — comments just stay empty
  }

  commentsFor(target, key) {
    const bucket = target === 'company' ? this.comments.companies : this.comments.categories;
    return (bucket && bucket[key]) || [];
  }

  renderCommentList(list) {
    if (!list.length) return '<div style="font-size:12.5px; color:var(--muted);">No comments yet.</div>';
    return list.slice().reverse().map(c => {
      const d = new Date(c.ts);
      const when = isNaN(d) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
      return '<div style="padding:8px 0; border-top:1px solid var(--section-border);">'
        + '<div style="font-size:13px; line-height:1.5; color:var(--charcoal);">' + esc(c.text) + '</div>'
        + '<div style="font-size:10.5px; color:var(--muted); margin-top:3px;">' + when + '</div></div>';
    }).join('');
  }

  // Posts one comment, updates the local cache from the server's response
  // (the source of truth), then hands control back to the caller to redraw
  // just its own comment list — never a full render(), so the panel that
  // was just typed into doesn't get rebuilt out from under the user.
  postComment(target, key, text, btn, onDone) {
    const clean = text.trim();
    if (!clean || btn.disabled) return;
    btn.disabled = true;
    fetch('/api/comments', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ target: target, key: key, text: clean }),
    })
      .then(r => r.json().then(data => ({ ok: r.ok, data: data })))
      .then(({ ok, data }) => {
        btn.disabled = false;
        if (!ok) { alert(data.error || 'Could not post comment.'); return; }
        const bucket = target === 'company' ? this.comments.companies : this.comments.categories;
        bucket[key] = data.list;
        onDone();
      })
      .catch(() => { btn.disabled = false; alert('Could not post comment — check your connection.'); });
  }

  buildCats() {
    const byCat = {};
    members.forEach(m => { (byCat[m.cat] = byCat[m.cat] || []).push(m); });
    const order = categories.map(c => c.slug).filter(s => byCat[s]);
    Object.keys(byCat).forEach(s => { if (order.indexOf(s) < 0) order.push(s); });
    let cats = order.map(slug => {
      const meta = categories.find(c => c.slug === slug) || { slug: slug, label: slug, subcats: [] };
      const list = byCat[slug];
      const subSlugs = (meta.subcats || []).map(s => s.slug);
      const groups = [];
      if (subSlugs.length) {
        subSlugs.forEach(s => {
          const g = list.filter(m => m.subcat === s);
          if (g.length) groups.push({ label: (meta.subcats.find(x => x.slug === s) || {}).label, items: g });
        });
        const rest = list.filter(m => subSlugs.indexOf(m.subcat) < 0);
        if (rest.length) groups.push({ label: meta.otherLabel || 'Other', items: rest });
      } else {
        groups.push({ label: meta.label, items: list });
      }
      return { slug: slug, meta: meta, list: list, groups: groups };
    });
    cats.sort((x, y) => (x.slug === PIN ? -1 : y.slug === PIN ? 1 : y.list.length - x.list.length));
    return cats;
  }

  layout() {
    const fmt = this.fmt();
    if (this._layout && this._layoutKey === fmt) return this._layout;
    const target = fmt === 'tall' ? 9 / 16 : 16 / 9;
    const ASPECT = target * CELL_RATIO;
    let cats = this.buildCats();
    this._cats = cats.slice();
    const opsCat = cats.filter(c => c.slug === PIN)[0] || cats[0];
    cats = [{ slug: '__title', title: true, meta: { label: '', subcats: [] }, list: [], groups: [], mirror: opsCat }].concat(cats);

    const tileInt = (items, x0, y0, w0, h0) => {
      const out = [];
      const rec = (list, x, y, w, h) => {
        if (!list.length || w < 1 || h < 1) return;
        if (list.length === 1) { out.push({ it: list[0], x: x, y: y, w: w, h: h }); return; }
        const total = list.reduce((s, i) => s + i.cells, 0);
        let acc = 0, idx = 0;
        for (let i = 0; i < list.length - 1; i++) { acc += list[i].cells; idx = i; if (acc >= total / 2) break; }
        const A = list.slice(0, idx + 1), B = list.slice(idx + 1);
        const sa = A.reduce((s, i) => s + i.cells, 0), sb = total - sa;
        if (w >= h) {
          let w1 = Math.max(1, Math.min(w - 1, Math.round(w * sa / total)));
          while (w1 < w - 1 && w1 * h < sa) w1++;
          while (w1 > 1 && (w - w1) * h < sb) w1--;
          rec(A, x, y, w1, h); rec(B, x + w1, y, w - w1, h);
        } else {
          let h1 = Math.max(1, Math.min(h - 1, Math.round(h * sa / total)));
          while (h1 < h - 1 && w * h1 < sa) h1++;
          while (h1 > 1 && w * (h - h1) < sb) h1--;
          rec(A, x, y, w, h1); rec(B, x, y + h1, w, h - h1);
        }
      };
      rec(items.slice(), x0, y0, w0, h0);
      return out;
    };

    const hrOf = g => (g.label ? 1 : 0);

    const packCat = (cat, wc, hc) => {
      if (cat.title) return (hc < 2 || wc < 1) ? null : { leaves: [], usedRows: hc };
      if (hc < 2 || wc < 1) return null;
      let dem = cat.groups.map(g => g.items.length + (g.label ? 2 : 0));
      let good = null;
      for (let it = 0; it < 18; it++) {
        const leaves = tileInt(cat.groups.map((g, i) => ({ idx: i, cells: dem[i] })), 0, 0, wc, hc);
        let ok = leaves.length === cat.groups.length;
        leaves.forEach(L => {
          const g = cat.groups[L.it.idx], hr = hrOf(g);
          const cap = L.w * Math.max(0, L.h - hr);
          if (g.items.length > cap) { ok = false; dem[L.it.idx] = g.items.length + (hr + 1) * L.w; }
        });
        if (ok) {
          good = leaves;
          const next = dem.slice();
          leaves.forEach(L => {
            const g = cat.groups[L.it.idx], hr = hrOf(g);
            next[L.it.idx] = L.w * (hr + Math.max(1, Math.ceil(g.items.length / L.w)));
          });
          if (next.every((v, i) => v === dem[i])) break;
          dem = next;
        }
      }
      if (!good) return null;
      const usedRows = Math.max.apply(null, good.map(L => L.y + L.h));
      return { leaves: good, usedRows: usedRows };
    };

    const demOf = c => {
      const n = c.list.length + c.groups.filter(g => g.label).length;
      return n + Math.max(2, Math.ceil(Math.sqrt(n * ASPECT)));
    };
    let cdem = cats.map(c => (c.title ? demOf(c.mirror) : demOf(c)));
    let plan = null;
    const TITLE_FRAC = fmt === 'tall' ? 2 / 3 : 1 / 2;
    const build = () => {
      const T = cdem.reduce((s, v) => s + v, 0);
      const W = Math.max(8, Math.round(Math.sqrt(T * ASPECT)));
      const titleW = Math.max(2, Math.min(W - 3, Math.round(W * TITLE_FRAC)));
      const rightW = W - titleW;
      const items = [];
      for (let i = 1; i < cats.length; i++) items.push({ idx: i, cells: cdem[i] });
      const hAspect = Math.max(4, Math.round((titleW * PITCH_X) / (2.0 * PITCH_Y)));
      const A = [], B = [];
      let acc = 0;
      items.forEach(it => {
        // Operators (always items[0], Pinned first) must sit beside the
        // masthead whenever there is any real column to put it in — a tall
        // canvas can make the size estimate below reject even the first
        // item, which would leave the masthead alone with a dead gap beside
        // it instead of paired with a category, as every other aspect ratio
        // shows it.
        const forced = A.length === 0 && rightW >= 1;
        if (forced || acc + it.cells <= rightW * hAspect) { A.push(it); acc += it.cells; }
        else B.push(it);
      });
      const needA = A.reduce((s, it) => s + cats[it.idx].list.length + cats[it.idx].groups.filter(g => g.label).length * Math.max(1, Math.round(rightW / A.length)), 0);
      const hLo = Math.ceil((titleW * PITCH_X) / (2.8 * PITCH_Y));
      const hHi = Math.floor((titleW * PITCH_X) / (1.5 * PITCH_Y));
      const titleH = Math.max(4, Math.min(Math.max(hLo, Math.ceil(needA / rightW)), Math.max(hLo, hHi)));
      while (A.length > 1 && A.reduce((s, i) => s + i.cells, 0) > rightW * titleH) B.unshift(A.pop());
      const sumB = B.reduce((s, i) => s + i.cells, 0);
      const bottomRows = Math.max(2, Math.ceil(sumB / W));
      const leaves = [];
      if (A.length) tileInt(A, titleW, 0, rightW, titleH).forEach(L => leaves.push(L));
      if (B.length) tileInt(B, 0, titleH, W, bottomRows).forEach(L => leaves.push(L));
      if (leaves.length !== cats.length - 1) return null;
      const res = [{ idx: 0, L: { x: 0, y: 0, w: titleW, h: titleH }, p: { leaves: [], usedRows: titleH } }];
      let ok = true;
      leaves.forEach(L => {
        const p = packCat(cats[L.it.idx], L.w, L.h);
        if (!p) { ok = false; cdem[L.it.idx] += Math.max(2, L.w); return; }
        res.push({ idx: L.it.idx, L: L, p: p });
      });
      return ok ? { res: res, W: W, H: titleH + bottomRows } : null;
    };
    for (let iter = 0; iter < 30 && !plan; iter++) plan = build();
    if (plan) {
      for (let pass = 0; pass < 5; pass++) {
        const next = cdem.slice();
        plan.res.forEach(r => { next[r.idx] = r.L.w * (r.p.usedRows + 0); });
        next[0] = cdem[0];
        if (next.every((v, i) => v === cdem[i])) break;
        const prev = cdem.slice();
        cdem = next;
        const p2 = build();
        if (!p2) { cdem = prev; break; }
        plan = p2;
      }
    }
    if (!plan) { cdem = cats.map(c => c.list.length * 3 + 6); plan = build(); }

    const clusters = plan.res.map(r => {
      const cat = cats[r.idx], T = toneOf(cat.slug), L = r.L;
      const px = L.x * PITCH_X, py = L.y * PITCH_Y;
      const wpx = L.w * PITCH_X - GAP;
      if (cat.title) {
        const hpx = L.h * PITCH_Y - GAP;
        const ops = cat.mirror.list.length;
        const body = 'The Finnish Data Center Association is the full ecosystem association for Finland’s data center industry, representing ' + members.length + ' member organisations: ' + ops + ' data center operators and ' + (members.length - ops) + ' supply chain organisations.';
        const pad = Math.round(Math.min(wpx, hpx) * 0.085);
        const gap = Math.round(pad * 0.4);
        const mark = Math.min(hpx * 0.21, wpx * 0.48);
        const fieldH = hpx * 0.15;
        const innerW = wpx - pad * 2;
        const room = hpx - pad * 2 - gap * 2 - mark * 0.86 - fieldH;
        let bodyFont = 14;
        for (let fs = Math.floor(Math.min(wpx * 0.084, hpx * 0.072)); fs >= 14; fs -= 1) {
          const lines = Math.max(1, Math.ceil((0.5 * body.length * fs) / innerW));
          if (lines * fs * 1.38 <= room) { bodyFont = fs; break; }
        }
        return {
          slug: '__title', isTitle: true, label: '', count: '',
          x: px, y: py, w: wpx, h: hpx,
          markFont: mark, bodyFont: bodyFont, titlePad: pad, titleGap: gap, body: body,
          bg: '#FFFFFF', border: COLORS.panelBorder, ink: COLORS.blueDark, dot: COLORS.blueDark,
          fieldH: fieldH, fieldFont: hpx * 0.055,
          headFont: 0, headPad: 0, boxes: [], slabels: [], tiles: []
        };
      }
      const nameLen = Math.max(7, cat.meta.label.length);
      const headRowH = PITCH_Y - GAP;
      const availW = Math.max(120, wpx - TIN * 2 - Math.min(150, wpx * 0.2));
      const roomH = headRowH - 14;
      const headLongest = Math.max.apply(null, cat.meta.label.split(/\s+/).map(w => w.length));
      const headWordCap = (availW - 8) / (0.5 * Math.max(3, headLongest));
      let headFont = 34;
      for (let fs = Math.floor(Math.min(CELL_H * 0.98, headWordCap)); fs >= 34; fs -= 1) {
        const lines = Math.max(1, Math.ceil((0.5 * nameLen * fs) / availW));
        if (lines * fs <= roomH) { headFont = fs; break; }
      }
      const boxes = [], slabels = [], tiles = [];
      r.p.leaves.forEach(sub => {
        const sx = (L.x + sub.x) * PITCH_X, sy = (L.y + sub.y) * PITCH_Y;
        const g0 = cat.groups[sub.it.idx];
        const lbl = g0.label || '';
        const hr = lbl ? 1 : 0;
        const bx0 = sx - px, by0 = sy - py, bw0 = sub.w * PITCH_X - GAP, bh0 = sub.h * PITCH_Y - GAP;
        const rowW = bw0 - 26, rowH = hr * PITCH_Y - GAP - 12;
        const longest = lbl ? Math.max.apply(null, lbl.split(/\s+/).map(w => w.length)) : 1;
        const wordCap = rowW / (0.58 * Math.max(3, longest));
        let lf = 0;
        for (let fs = Math.floor(Math.min(headFont * 0.5, wordCap, CELL_H * 0.8)); fs >= 18; fs -= 1) {
          const lines = Math.max(1, Math.ceil((0.58 * Math.max(5, lbl.length) * fs) / rowW));
          if (lines * fs * 1.02 <= rowH) { lf = fs; break; }
        }
        if (!lf) lf = 18;
        boxes.push({ x: bx0, y: by0, w: bw0, h: bh0, bg: roleColor(T, 'group'), bd: roleColor(T, 'groupBorder') });
        const g = cat.groups[sub.it.idx];
        let i = 0;
        const cellOf = k => ({
          x: (L.x + sub.x + (k % sub.w)) * PITCH_X - px + TIN,
          y: (L.y + sub.y + hr + Math.floor(k / sub.w)) * PITCH_Y - py + TIN
        });
        if (lbl) slabels.push({ wordCap: wordCap, x: bx0 + 13, y: by0, w: bw0 - 26, h: hr * PITCH_Y - GAP, text: lbl, n: g.items.length, font: lf, countFont: Math.max(12, Math.round(lf * 0.46)) });
        g.items.forEach(m => { const c = cellOf(i++); tiles.push({ m: m, x: c.x, y: c.y, w: CELL_W, h: CELL_H }); });
      });
      return {
        slug: cat.slug, label: cat.meta.label, count: cat.list.length,
        x: px, y: py, w: wpx, h: L.h * PITCH_Y - GAP,
        headFont: headFont, headPad: TIN + 4,
        markFont: 0, bodyFont: 0, titlePad: 0, titleGap: 0, body: '', isTitle: false, fieldH: 0, fieldFont: 0,
        boxes: boxes, slabels: slabels, tiles: tiles,
        bg: roleColor(T, 'surface'), border: roleColor(T, 'border'),
        ink: roleColor(T, 'ink'), dot: roleColor(T, 'mark')
      };
    });

    const fonts = [];
    clusters.forEach(c => c.slabels.forEach(s => fonts.push(s.font)));
    if (fonts.length) {
      const floor = Math.max.apply(null, fonts) * 0.7;
      clusters.forEach(c => c.slabels.forEach(s => {
        const target = Math.min(floor, s.wordCap);
        if (s.font >= target) return;
        s.font = target;
        s.countFont = Math.max(12, Math.round(target * 0.46));
      }));
    }

    const rawW = plan.W * PITCH_X, rawH = plan.H * PITCH_Y;
    let maxW = rawW, h = rawH;
    if (rawW / rawH < target) maxW = rawH * target; else h = rawW / target;
    const ox = (maxW - rawW) / 2, oy = (h - rawH) / 2;
    clusters.forEach(c => { c.x += ox; c.y += oy; });
    this._layoutKey = fmt;
    const tc = clusters.filter(c => c.isTitle)[0];
    this._layout = { clusters: clusters, w: maxW, h: h, titleAspect: tc ? tc.w / tc.h : 1 };
    return this._layout;
  }

  bind() {
    const vp = document.getElementById('viewport');
    if (!vp || this.bound) return;
    this.bound = true;
    const pts = new Map();
    let drag = null, pinch = null, lastTap = 0;
    const mid = () => {
      const a = [...pts.values()];
      return { x: (a[0].x + a[1].x) / 2, y: (a[0].y + a[1].y) / 2, d: Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y) };
    };
    vp.addEventListener('pointerdown', e => {
      if (e.target.closest('[data-nodrag]')) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2) { drag = null; pinch = mid(); }
      else if (pts.size === 1) {
        drag = { px: e.clientX, py: e.clientY, moved: 0 };
        vp.style.cursor = 'grabbing';
        const now = Date.now();
        if (now - lastTap < 300) {
          const r = vp.getBoundingClientRect();
          this.zoomAt(e.clientX - r.left, e.clientY - r.top, 2);
          this.dragged = true;
        }
        lastTap = now;
      }
    });
    window.addEventListener('pointermove', e => {
      if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2 && pinch) {
        const m = mid(), r = vp.getBoundingClientRect();
        if (pinch.d > 0) {
          this.zoomAt(m.x - r.left, m.y - r.top, m.d / pinch.d);
          this.v.x += m.x - pinch.x; this.v.y += m.y - pinch.y;
          this.applyTransform();
        }
        pinch = m; this.dragged = true;
        return;
      }
      if (!drag) return;
      const dx = e.clientX - drag.px, dy = e.clientY - drag.py;
      drag.px = e.clientX; drag.py = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
      this.v.x += dx; this.v.y += dy; this.applyTransform();
    });
    const endPointer = e => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = null;
      if (pts.size === 0 && drag) { this.dragged = drag.moved > 6; drag = null; vp.style.cursor = 'grab'; }
    };
    window.addEventListener('pointerup', endPointer);
    window.addEventListener('pointercancel', endPointer);
    vp.addEventListener('wheel', e => {
      e.preventDefault();
      const r = vp.getBoundingClientRect();
      this.zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.0016));
    }, { passive: false });
    const onResize = () => {
      const st = document.getElementById('stageInner');
      const r = st ? st.getBoundingClientRect() : vp.getBoundingClientRect();
      const auto = r.height > r.width ? 'tall' : 'wide';
      const flipped = auto !== this.state.autoFormat;
      const changed = Math.abs(r.width - this.state.vw) > 1 || flipped;
      if (flipped) this._layout = null;
      if (changed) this.setState({ vw: r.width, vh: r.height, autoFormat: auto }, () => this.fit());
      else this.applyTransform();
    };
    document.addEventListener('pointerdown', e => {
      const inChrome = e.target.closest('[data-detail-panel]') || e.target.closest('[data-cat-panel]') || e.target.closest('button') || e.target.closest('input') || e.target.closest('a');
      if (inChrome) return;
      if (this.state.sel) this.setState({ sel: null });
      else if (this.state.catPanel) this.setState({ catPanel: null });
    });
    window.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (this.state.sel) this.setState({ sel: null });
      else if (this.state.catPanel) this.setState({ catPanel: null });
    });
    window.addEventListener('resize', onResize);
    onResize();
    this.fit();
  }

  zoomCenter(factor) {
    const st = document.getElementById('stageInner');
    if (!st) return;
    const r = st.getBoundingClientRect();
    this.zoomAt(r.width / 2, r.height / 2, factor);
  }

  zoomAt(cx, cy, factor) {
    const k0 = this.v.k, k = Math.min(3.4, Math.max(this.minK || 0.02, k0 * factor));
    this.v.x = cx - (cx - this.v.x) * (k / k0);
    this.v.y = cy - (cy - this.v.y) * (k / k0);
    this.v.k = k; this.applyTransform();
  }

  setView(v) {
    if (this.view() === v) return;
    this.setState({ view: v, sheetOpen: false }, () => {
      if (v === 'map') this.fit();
      if (document.getElementById('listPane')) document.getElementById('listPane').scrollTop = 0;
    });
  }

  fit() {
    const st = document.getElementById('stageInner'), l = this.layout();
    if (!st || !l) return;
    const r = st.getBoundingClientRect();
    if (!r.width) return;
    const TOP = 76;
    const fitBoth = Math.min((r.width - 40) / l.w, (r.height - TOP - 24) / l.h);
    const k = this.isNarrow() ? Math.max(fitBoth, (r.width - 20) / l.w) : fitBoth;
    this.minK = Math.min(0.1, fitBoth * 0.9);
    this.v.k = Math.min(1.4, k);
    this.v.x = (r.width - l.w * this.v.k) / 2;
    this.v.y = TOP + Math.max(0, (r.height - TOP - l.h * this.v.k) / 2);
    this.setState({ focusCat: null, focusSub: null });
    this.applyTransform();
  }

  applyTransform() {
    const w = document.getElementById('wrap');
    if (w) w.style.transform = 'translate(' + this.v.x + 'px,' + this.v.y + 'px) scale(' + this.v.k + ')';
    const k = this.v.k;
    const tier = k < 0.2 ? 'dot' : (k < 0.5 ? 'logo' : (k < 0.95 ? 'name' : 'card'));
    if (tier !== this.state.tier) this.setState({ tier: tier });
  }

  goTo(slug, label) {
    this.setState({ focusCat: slug, focusSub: label || null, sheetOpen: false });
    if (this.listMode()) {
      const box = document.getElementById('listPane');
      const q = label ? '[data-sub="' + slug + '::' + label + '"]' : '[data-sec="' + slug + '"]';
      const el = box && box.querySelector(q);
      if (el) box.scrollTo({ top: Math.max(0, el.offsetTop - 2), behavior: 'smooth' });
      return;
    }
    const l = this.layout();
    const c = l && l.clusters.filter(x => x.slug === slug)[0];
    const st = document.getElementById('stageInner');
    if (!c || !st) return;
    let bx = c.x, by = c.y, bw = c.w, bh = c.h;
    if (label) {
      const s = c.slabels.filter(x => x.text === label)[0];
      if (s) { bx = c.x + s.x; by = c.y + s.y; bw = s.w; bh = s.h; }
    }
    const r = st.getBoundingClientRect();
    let k = Math.min((r.width - 32) / bw, (r.height - 32) / bh);
    k = Math.min(this.isNarrow() ? 0.5 : 1.4, Math.max(this.minK || 0.02, k));
    this.v.k = k;
    this.v.x = (r.width - bw * k) / 2 - bx * k;
    this.v.y = (r.height - bh * k) / 2 - by * k;
    this.applyTransform();
  }

  render() {
    const view = this.view();
    const list = this.listMode();
    document.getElementById('viewport').style.display = list ? 'none' : 'block';
    document.getElementById('listPane').style.display = list ? 'block' : 'none';
    document.getElementById('zoomBar').style.display = list ? 'none' : 'flex';
    this.styleTab(document.getElementById('mapTab'), view === 'map');
    this.styleTab(document.getElementById('listTab'), view === 'list');

    const cats = this._cats || this.buildCats();
    const q = this.state.q.trim().toLowerCase();
    const tier = this.state.tier;

    if (!list) this.renderMap(tier, q);
    else this.renderList(cats, q);

    document.getElementById('jumpLabel').textContent = this.state.focusSub || (this.state.focusCat ? (cats.filter(c => c.slug === this.state.focusCat)[0] || {}).meta.label : 'All categories');
    this.renderSheet(cats);
    this.renderDetail();
    this.renderCategoryPanel();
  }

  styleTab(btn, on) {
    btn.style.background = on ? '#FFFFFF' : 'transparent';
    btn.style.color = on ? COLORS.blue : COLORS.muted;
    btn.style.boxShadow = on ? '0 1px 3px rgba(2,3,129,.14)' : 'none';
  }

  renderMap(tier, q) {
    const l = this.layout();
    const wrap = document.getElementById('wrap');
    wrap.style.width = l.w + 'px';
    wrap.style.height = l.h + 'px';
    const dotDisp = tier === 'dot';
    const cardDisp = tier === 'card';
    const nameDisp = tier === 'name' || tier === 'card';
    const logoH = cardDisp ? 34 : 66;
    const parts = l.clusters.map(c => {
      if (c.isTitle) {
        return '<div style="position:absolute; left:' + c.x + 'px; top:' + c.y + 'px; width:' + c.w + 'px; height:' + c.h + 'px; background:' + c.bg + '; border:1.5px solid ' + c.border + '; border-radius:14px;">'
          + '<div style="position:absolute; inset:0; display:flex; flex-direction:column; justify-content:space-between; gap:' + c.titleGap + 'px; padding:' + c.titlePad + 'px; overflow:hidden;">'
          + '<img src="' + FDCA_LOGO + '" alt="FDCA" style="height:' + c.markFont + 'px; width:auto; object-fit:contain; object-position:left top; flex:none;">'
          + '<span style="font-size:' + c.bodyFont + 'px; line-height:1.38; color:' + c.ink + '; flex:none;">' + esc(c.body) + '</span>'
          + '<div data-nodrag="1" style="display:flex; align-items:center; gap:' + c.titlePad + 'px; height:' + c.fieldH + 'px; flex:none; border:2px solid var(--panel-border); border-radius:' + c.fieldH + 'px; padding:0 ' + c.titlePad + 'px; background:#FAFBFC;">'
          + '<span style="font-size:' + c.fieldFont + 'px; color:var(--muted); flex:none;">&#8981;</span>'
          + '<input id="searchInput" value="' + esc(this.state.q) + '" aria-label="Search member companies" placeholder="Search ' + members.length + ' companies — name, service, technology" style="border:none; outline:none; flex:1 1 auto; min-width:0; font-family:Barlow,sans-serif; font-size:' + c.fieldFont + 'px; color:var(--charcoal); background:transparent;">'
          + '</div></div></div>';
      }
      const boxes = c.boxes.map(b => '<div style="position:absolute; left:' + b.x + 'px; top:' + b.y + 'px; width:' + b.w + 'px; height:' + b.h + 'px; background:' + b.bg + '; border:1.5px solid ' + b.bd + '; border-radius:10px;"></div>').join('');
      const slabels = c.slabels.map(s => '<div style="position:absolute; left:' + s.x + 'px; top:' + s.y + 'px; width:' + s.w + 'px; height:' + s.h + 'px; display:flex; align-items:center; gap:12px; overflow:hidden;">'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:' + s.font + 'px; line-height:.98; letter-spacing:.035em; text-transform:uppercase; color:' + c.ink + '; opacity:.78; overflow-wrap:anywhere; min-width:0;">' + esc(s.text) + '</span>'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:' + s.countFont + 'px; color:' + c.ink + '; opacity:.42; flex:none;">' + s.n + '</span></div>').join('');
      const tiles = c.tiles.map(t => {
        const m = t.m, idx = t.idx;
        const hit = this.matches(m, q);
        const op = hit ? 1 : 0.13;
        const border = tier === 'dot' ? 'transparent' : (hit ? 'var(--panel-border)' : 'transparent');
        let inner = '<div style="display:' + (dotDisp ? 'block' : 'none') + '; width:34px; height:34px; border-radius:50%; background:' + c.dot + ';"></div>';
        if (!dotDisp) {
          if (m.logo && !this.broken[m.logo]) {
            inner += '<img data-fallback="1" src="' + esc(m.logo) + '" alt="" loading="lazy" style="width:100%; height:' + logoH + 'px; object-fit:contain; object-position:' + (cardDisp ? 'left center' : 'center') + '; filter:grayscale(1); opacity:.88; flex:none;">';
          } else {
            inner += '<div style="width:100%; height:' + logoH + 'px; display:flex; align-items:center; justify-content:' + (cardDisp ? 'flex-start' : 'center') + '; font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:22px; letter-spacing:.04em; color:' + c.dot + '; flex:none;">' + esc(initialsOf(m.name)) + '</div>';
          }
        }
        if (nameDisp) inner += '<div style="width:100%; margin-top:6px; font-size:12px; font-weight:600; line-height:1.25; text-align:' + (cardDisp ? 'left' : 'center') + '; color:var(--charcoal); overflow:hidden; flex:none;">' + esc(m.name) + '</div>';
        if (cardDisp) {
          const metaLine = [c.label, m.subcat ? m.subcat.replace(/_/g, ' ') : ''].filter(Boolean).join(' · ');
          inner += '<div style="width:100%; margin-top:2px; font-size:8.6px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:' + c.ink + '; opacity:.72; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; flex:none;">' + esc(metaLine) + '</div>'
            + '<div style="width:100%; margin-top:6px; overflow:hidden; min-height:0; flex:1 1 auto;"><div style="font-size:9.4px; line-height:1.42; color:var(--secondary-text,#6B7280); overflow:hidden; display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical;">' + esc(clipTo(m.desc, 132)) + '</div></div>'
            + '<div style="width:100%; margin-top:5px; padding-top:4px; border-top:1px solid var(--section-border); font-size:9px; font-weight:600; color:' + COLORS.blue + '; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; flex:none;">' + esc(hostOf(m.url)) + '</div>';
        }
        return '<button type="button" data-midx="' + idx + '" style="position:absolute; left:' + t.x + 'px; top:' + t.y + 'px; width:' + t.w + 'px; height:' + t.h + 'px; background:' + (dotDisp ? 'transparent' : '#FFFFFF') + '; border:' + (dotDisp ? 0 : 1.5) + 'px solid ' + border + '; border-radius:7px; cursor:pointer; opacity:' + op + '; display:flex; flex-direction:column; align-items:center; justify-content:' + (cardDisp ? 'flex-start' : 'center') + '; padding:9px; overflow:hidden; font:inherit; text-align:' + (cardDisp ? 'left' : 'center') + ';">' + inner + '</button>';
      }).join('');
      return '<div style="position:absolute; left:' + c.x + 'px; top:' + c.y + 'px; width:' + c.w + 'px; height:' + c.h + 'px; background:' + c.bg + '; border:1.5px solid ' + c.border + '; border-radius:14px;">'
        + '<div style="position:absolute; left:' + c.headPad + 'px; top:0; right:' + c.headPad + 'px; height:' + (PITCH_Y - GAP) + 'px; display:flex; align-items:center; gap:18px; overflow:hidden;">'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:800; font-size:' + c.headFont + 'px; line-height:.95; letter-spacing:.015em; text-transform:uppercase; color:' + c.ink + '; overflow-wrap:anywhere; min-width:0;">' + esc(c.label) + '</span>'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:' + Math.round(c.headFont * 0.5) + 'px; color:' + c.ink + '; opacity:.45; flex:none;">' + c.count + '</span>'
        + '<button type="button" data-nodrag="1" data-catcomment="' + c.slug + '" title="Comment on ' + esc(c.label) + '" style="margin-left:auto; flex:none; border:none; background:transparent; cursor:pointer; padding:2px; font-size:' + Math.max(13, Math.round(c.headFont * 0.42)) + 'px; color:' + c.ink + '; opacity:.5; line-height:1;">&#128172;</button></div>'
        + boxes + slabels + tiles + '</div>';
    });

    // flatten tile member refs into a lookup array for the click handler
    this._mapTileMembers = [];
    l.clusters.forEach(c => c.tiles.forEach(t => { t.idx = this._mapTileMembers.length; this._mapTileMembers.push(t.m); }));
    wrap.innerHTML = parts.join('');
    const search = document.getElementById('searchInput');
    if (search) {
      // A full render() rebuilds this input's own DOM node, which would drop
      // focus after every keystroke — so typing goes through the cheap
      // filterMap()/filterList() path instead, never through setState/render().
      search.addEventListener('input', e => { this.state.q = e.target.value; this.filterMap(); this.filterList(); });
      search.addEventListener('pointerdown', e => e.stopPropagation());
    }
    wrap.querySelectorAll('img[data-fallback]').forEach(img => {
      img.addEventListener('error', () => { this.broken[img.getAttribute('src')] = true; this.render(); }, { once: true });
    });
    if (!wrap._bound) {
      wrap._bound = true;
      wrap.addEventListener('click', e => {
        const catBtn = e.target.closest('[data-catcomment]');
        if (catBtn) { this.setState({ catPanel: catBtn.dataset.catcomment, sel: null }); return; }
        const el = e.target.closest('[data-midx]');
        if (!el) return;
        this.select(this._mapTileMembers[+el.dataset.midx]);
      });
    }
  }

  renderList(cats, q) {
    const pane = document.getElementById('listPane');
    const narrow = this.isNarrow();
    const gridCols = narrow ? '1fr' : 'repeat(auto-fill, minmax(330px, 1fr))';
    const total = members.length;
    const masthead = '<div style="display:flex; flex-direction:column; gap:10px; max-width:640px; margin:20px auto 14px; padding:22px; background:#FFFFFF; border:1.5px solid var(--panel-border); border-radius:14px;">'
      + '<img src="' + FDCA_LOGO + '" alt="FDCA" style="height:32px; width:auto; object-fit:contain; object-position:left top;">'
      + '<span style="font-size:14px; line-height:1.5; color:' + COLORS.blueDark + ';">The Finnish Data Center Association is the full ecosystem association for Finland’s data center industry, representing ' + total + ' member organisations across ' + categories.length + ' families.</span>'
      + '<div data-nodrag="1" style="display:flex; align-items:center; gap:9px; height:44px; border:1.5px solid var(--panel-border); border-radius:22px; padding:0 14px; background:#FAFBFC;">'
      + '<span style="font-size:15px; color:var(--muted);">&#8981;</span>'
      + '<input id="searchInputList" value="' + esc(this.state.q) + '" aria-label="Search member companies" placeholder="Search ' + total + ' companies — name, service, technology" style="border:none; outline:none; flex:1 1 auto; min-width:0; font-family:Barlow,sans-serif; font-size:14.5px; color:var(--charcoal); background:transparent;">'
      + '</div></div>';

    // Every row is always built (never filtered out here) — search-driven
    // visibility is applied afterwards by filterList(), which only toggles
    // style.display. Rebuilding this HTML on every keystroke would destroy
    // and recreate the search <input> itself, dropping focus after one char.
    const sections = cats.map(c => {
      const T = toneOf(c.slug);
      const groups = c.groups.map(g => {
        const own = g.label && g.label !== c.meta.label;
        const rows = g.items.map(m => {
          const idx = members.indexOf(m);
          const logo = (m.logo && !this.broken[m.logo])
            ? '<img data-fallback="1" src="' + esc(m.logo) + '" alt="" loading="lazy" style="max-width:100%; max-height:100%; object-fit:contain; filter:grayscale(1); opacity:.9;">'
            : '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:20px; letter-spacing:.04em; color:' + roleColor(T, 'mark') + ';">' + esc(initialsOf(m.name)) + '</span>';
          return '<button type="button" data-midx="' + idx + '" style="display:' + (this.matches(m, q) ? 'flex' : 'none') + '; flex-direction:row; align-items:center; gap:13px; width:100%; min-height:72px; padding:11px 13px; background:#FFFFFF; border:1.5px solid var(--section-border); border-radius:10px; cursor:pointer; font:inherit; text-align:left; overflow:hidden;">'
            + '<div style="display:flex; align-items:center; justify-content:flex-start; width:62px; height:42px; flex:none;">' + logo + '</div>'
            + '<div style="display:flex; flex-direction:column; gap:2px; min-width:0; flex:1 1 auto;">'
            + '<span style="font-size:14px; font-weight:600; line-height:1.25; color:var(--charcoal);">' + esc(m.name) + '</span>'
            + '<span style="font-size:12px; line-height:1.4; color:var(--secondary-text,#6B7280); overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">' + esc(clipTo(m.desc, 160)) + '</span></div></button>';
        }).join('');
        return '<div data-sub="' + c.slug + '::' + (g.label || '') + '" style="scroll-margin-top:44px;">'
          + (own ? '<div style="display:flex; align-items:baseline; gap:8px; padding:10px 14px 4px;"><span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:13.5px; letter-spacing:.06em; text-transform:uppercase; color:' + roleColor(T, 'ink') + '; opacity:.75;">' + esc(g.label) + '</span><span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:12px; color:' + roleColor(T, 'ink') + '; opacity:.4;">' + g.items.length + '</span></div>' : '')
          + '<div style="display:grid; grid-template-columns:' + gridCols + '; gap:8px; padding:8px 12px 14px;">' + rows + '</div></div>';
      });
      const n = c.groups.reduce((s, g) => s + g.items.length, 0);
      return '<section data-sec="' + c.slug + '" style="margin:0 0 10px;">'
        + '<div style="position:sticky; top:0; z-index:3; display:flex; align-items:baseline; gap:10px; padding:11px 14px 9px; background:' + roleColor(T, 'surface') + '; border-bottom:1.5px solid ' + roleColor(T, 'border') + ';">'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:800; font-size:21px; line-height:1; letter-spacing:.02em; text-transform:uppercase; color:' + roleColor(T, 'ink') + ';">' + esc(c.meta.label) + '</span>'
        + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:15px; color:' + roleColor(T, 'ink') + '; opacity:.5;">' + n + '</span>'
        + '<button type="button" data-catcomment="' + c.slug + '" title="Comment on ' + esc(c.meta.label) + '" style="margin-left:auto; flex:none; border:none; background:transparent; cursor:pointer; padding:2px; font-size:15px; color:' + roleColor(T, 'ink') + '; opacity:.55; line-height:1;">&#128172;</button></div>'
        + groups.join('') + '</section>';
    }).join('');

    pane.innerHTML = masthead + sections + '<div id="listEmptyMsg" style="display:none; padding:60px 24px; text-align:center; font-size:14px; color:var(--muted);"></div>';
    const search = document.getElementById('searchInputList');
    if (search) {
      search.addEventListener('input', e => { this.state.q = e.target.value; this.filterMap(); this.filterList(); });
      search.addEventListener('pointerdown', e => e.stopPropagation());
    }
    pane.querySelectorAll('img[data-fallback]').forEach(img => {
      img.addEventListener('error', () => { this.broken[img.getAttribute('src')] = true; this.render(); }, { once: true });
    });
    this.filterList();
    if (!pane._bound) {
      pane._bound = true;
      pane.addEventListener('click', e => {
        const catBtn = e.target.closest('[data-catcomment]');
        if (catBtn) { this.setState({ catPanel: catBtn.dataset.catcomment, sel: null }); return; }
        const el = e.target.closest('[data-midx]');
        if (!el) return;
        this.select(members[+el.dataset.midx]);
      });
    }
  }

  // Cheap search-only update: toggles existing tiles/rows in place instead
  // of rebuilding renderMap()/renderList()'s HTML, so the search <input>
  // itself is never destroyed and typing never loses focus.
  filterMap() {
    if (this.listMode()) return;
    const q = this.state.q.trim().toLowerCase();
    const dot = this.state.tier === 'dot';
    const wrap = document.getElementById('wrap');
    if (!wrap || !this._mapTileMembers) return;
    wrap.querySelectorAll('[data-midx]').forEach(btn => {
      const m = this._mapTileMembers[+btn.dataset.midx];
      if (!m) return;
      const hit = this.matches(m, q);
      btn.style.opacity = hit ? '1' : '.13';
      if (!dot) btn.style.borderColor = hit ? 'var(--panel-border)' : 'transparent';
    });
  }

  filterList() {
    const q = this.state.q.trim().toLowerCase();
    const pane = document.getElementById('listPane');
    if (!pane) return;
    let hits = 0;
    pane.querySelectorAll('[data-sub]').forEach(subEl => {
      let subHits = 0;
      subEl.querySelectorAll('[data-midx]').forEach(btn => {
        const m = members[+btn.dataset.midx];
        const hit = this.matches(m, q);
        btn.style.display = hit ? 'flex' : 'none';
        if (hit) subHits++;
      });
      subEl.style.display = subHits ? '' : 'none';
      hits += subHits;
    });
    pane.querySelectorAll('[data-sec]').forEach(secEl => {
      const anyVisible = Array.from(secEl.querySelectorAll('[data-sub]')).some(s => s.style.display !== 'none');
      secEl.style.display = anyVisible ? '' : 'none';
    });
    const msg = document.getElementById('listEmptyMsg');
    if (msg) {
      msg.style.display = (q && !hits) ? 'block' : 'none';
      msg.textContent = 'No company matches “' + this.state.q.trim() + '”.';
    }
  }

  renderSheet(cats) {
    const overlay = document.getElementById('sheetOverlay');
    overlay.style.display = this.state.sheetOpen ? 'flex' : 'none';
    if (!this.state.sheetOpen) return;
    const list = document.getElementById('sheetList');
    const rows = ['<button type="button" data-jump="__all" style="display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:0 12px; border:none; border-radius:10px; background:transparent; cursor:pointer; font:inherit; text-align:left; font-size:16px; font-weight:700; color:' + COLORS.blue + ';">All categories</button>'];
    cats.forEach(c => {
      const T = toneOf(c.slug);
      rows.push('<button type="button" data-jump="' + c.slug + '" style="display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:0 12px; border:none; border-radius:10px; background:transparent; cursor:pointer; font:inherit; text-align:left;">'
        + '<span style="flex:none; width:10px; height:10px; border-radius:3px; background:' + roleColor(T, 'chipBdOn') + ';"></span>'
        + '<span style="flex:1 1 auto; min-width:0; font-size:16px; font-weight:700; color:' + roleColor(T, 'ink') + ';">' + esc(c.meta.label) + '</span>'
        + '<span style="flex:none; font-size:13px; font-weight:600; color:var(--muted);">' + c.list.length + '</span></button>');
      c.groups.forEach(g => {
        if (!g.label || g.label === c.meta.label) return;
        rows.push('<button type="button" data-jump="' + c.slug + '" data-jump-sub="' + esc(g.label) + '" style="display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:0 12px 0 22px; border:none; border-radius:10px; background:transparent; cursor:pointer; font:inherit; text-align:left;">'
          + '<span style="flex:none; width:10px; height:10px; border-radius:3px; background:' + roleColor(T, 'chipBd') + ';"></span>'
          + '<span style="flex:1 1 auto; min-width:0; font-size:14.5px; font-weight:600; color:' + roleColor(T, 'subInk') + ';">' + esc(g.label) + '</span>'
          + '<span style="flex:none; font-size:13px; font-weight:600; color:var(--muted);">' + g.items.length + '</span></button>');
      });
    });
    list.innerHTML = rows.join('');
    if (!list._bound) {
      list._bound = true;
      list.addEventListener('click', e => {
        const el = e.target.closest('[data-jump]');
        if (!el) return;
        if (el.dataset.jump === '__all') { this.setState({ sheetOpen: false, view: 'map' }, () => this.fit()); return; }
        this.goTo(el.dataset.jump, el.dataset.jumpSub || null);
      });
    }
  }

  renderDetail() {
    const panel = document.getElementById('detailPanel');
    const sel = this.state.sel;
    if (!sel) { panel.style.display = 'none'; panel.innerHTML = ''; return; }
    panel.style.display = 'flex';
    let host = '';
    if (sel.url) { try { host = new URL(sel.url).hostname.replace(/^www\./, ''); } catch (e) { host = sel.url; } }
    const catMeta = categories.find(c => c.slug === sel.cat) || { label: sel.cat };
    const logo = (sel.logo && !this.broken[sel.logo])
      ? '<img src="' + esc(sel.logo) + '" alt="" style="width:74px; height:44px; object-fit:contain; object-position:left center;">'
      : '<div style="width:74px; height:44px; display:flex; align-items:center; justify-content:flex-start; font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:28px; color:' + COLORS.blueMid + ';">' + esc(initialsOf(sel.name)) + '</div>';
    const officialLine = sel.official && sel.official !== sel.name ? '<span style="font-size:12px; color:var(--muted);">' + esc(sel.official) + '</span>' : '';
    const subTag = sel.subcat ? '<span style="font-size:11.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--charcoal); background:var(--pill-bg); border-radius:16px; padding:4px 11px;">' + esc(sel.subcat.replace(/_/g, ' ')) + '</span>' : '';
    const blogLine = sel.blog ? '<a href="' + esc(sel.blog) + '" target="_blank" rel="noopener" style="font-size:13px; font-weight:600;">Read the FDCA introduction post ↗</a>' : '';
    const flag = sel.rosterStatus === 'website-only' ? '<div style="font-size:11.5px; line-height:1.5; color:' + COLORS.warn + '; background:rgba(176,102,60,.07); border:1px solid rgba(176,102,60,.2); border-radius:6px; padding:9px 12px;">Listed on fdca.fi but not confirmed on the current FDCA roster. Membership pending confirmation by the FDCA office.</div>' : '';
    const companyComments = this.commentsFor('company', sel.name);
    panel.innerHTML = '<div style="display:flex; align-items:flex-start; gap:12px; padding:20px 20px 14px; border-bottom:1px solid var(--panel-border);">'
      + logo
      + '<button type="button" id="detailClose" aria-label="Close company details" style="margin-left:auto; background:var(--pill-bg); border:none; border-radius:50%; width:32px; height:32px; font-size:16px; color:var(--muted); cursor:pointer; line-height:1; padding-bottom:2px;">&times;</button></div>'
      + '<div style="padding:18px 20px 30px; overflow-y:auto; display:flex; flex-direction:column; gap:16px; animation:panelBody .24s cubic-bezier(.2,0,0,1) .1s both;">'
      + '<div style="display:flex; flex-direction:column; gap:4px;"><span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:27px; line-height:1.05; letter-spacing:.02em; text-transform:uppercase; color:' + COLORS.blueDark + ';">' + esc(sel.name) + '</span>' + officialLine + '</div>'
      + '<div style="display:flex; flex-wrap:wrap; gap:6px;"><span style="font-size:11.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:#FFFFFF; background:' + COLORS.blue + '; border-radius:16px; padding:4px 11px;">' + esc(catMeta.label) + '</span>' + subTag + '</div>'
      + '<p style="margin:0; font-size:13.5px; line-height:1.55; color:var(--secondary-text,#6B7280);">' + esc(sel.desc) + '</p>'
      + '<div style="display:flex; flex-direction:column; gap:8px; padding-top:4px;">' + (sel.url ? '<a href="' + esc(sel.url) + '" target="_blank" rel="noopener" style="font-size:13px; font-weight:600;">' + esc(host || 'No website on file') + ' ↗</a>' : '') + blogLine + '</div>'
      + flag
      + '<div style="display:flex; flex-direction:column; gap:8px; border-top:1px solid var(--panel-border); padding-top:14px;">'
      + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:700; font-size:13px; letter-spacing:.04em; text-transform:uppercase; color:var(--charcoal);">Comments — is this company in the right place?</span>'
      + '<div id="detailCommentList">' + this.renderCommentList(companyComments) + '</div>'
      + '<textarea id="detailCommentInput" maxlength="500" placeholder="Say something about this company…" style="resize:vertical; min-height:56px; border:1.5px solid var(--panel-border); border-radius:8px; padding:8px 10px; font-family:Barlow,sans-serif; font-size:13px; color:var(--charcoal);"></textarea>'
      + '<button type="button" id="detailCommentPost" style="align-self:flex-start; border:none; background:' + COLORS.blue + '; color:#FFFFFF; font-size:12.5px; font-weight:600; padding:7px 16px; border-radius:16px; cursor:pointer;">Post comment</button>'
      + '</div></div>';
    document.getElementById('detailClose').addEventListener('click', () => this.setState({ sel: null }));
    const postBtn = document.getElementById('detailCommentPost');
    const input = document.getElementById('detailCommentInput');
    postBtn.addEventListener('click', () => {
      this.postComment('company', sel.name, input.value, postBtn, () => {
        input.value = '';
        document.getElementById('detailCommentList').innerHTML = this.renderCommentList(this.commentsFor('company', sel.name));
      });
    });
  }

  renderCategoryPanel() {
    const panel = document.getElementById('categoryPanel');
    const slug = this.state.catPanel;
    if (!slug) { panel.style.display = 'none'; panel.innerHTML = ''; return; }
    panel.style.display = 'flex';
    const catMeta = categories.find(c => c.slug === slug) || { label: slug };
    const list = this.commentsFor('category', slug);
    panel.innerHTML = '<div style="display:flex; align-items:center; gap:12px; padding:20px 20px 14px; border-bottom:1px solid var(--panel-border);">'
      + '<span style="font-family:\'Barlow Condensed\',sans-serif; font-weight:800; font-size:20px; letter-spacing:.02em; text-transform:uppercase; color:' + COLORS.blueDark + ';">' + esc(catMeta.label) + '</span>'
      + '<button type="button" id="catPanelClose" aria-label="Close category comments" style="margin-left:auto; background:var(--pill-bg); border:none; border-radius:50%; width:32px; height:32px; font-size:16px; color:var(--muted); cursor:pointer; line-height:1; padding-bottom:2px;">&times;</button></div>'
      + '<div style="padding:18px 20px 30px; overflow-y:auto; display:flex; flex-direction:column; gap:8px; animation:panelBody .24s cubic-bezier(.2,0,0,1) .1s both;">'
      + '<span style="font-size:12.5px; color:var(--secondary-text,#6B7280);">Comments about the ' + esc(catMeta.label) + ' category as a whole — a company in the wrong subcategory, a missing one, anything about how this group is organised.</span>'
      + '<div id="catCommentList">' + this.renderCommentList(list) + '</div>'
      + '<textarea id="catCommentInput" maxlength="500" placeholder="Comment on this category…" style="resize:vertical; min-height:56px; border:1.5px solid var(--panel-border); border-radius:8px; padding:8px 10px; font-family:Barlow,sans-serif; font-size:13px; color:var(--charcoal);"></textarea>'
      + '<button type="button" id="catCommentPost" style="align-self:flex-start; border:none; background:' + COLORS.blue + '; color:#FFFFFF; font-size:12.5px; font-weight:600; padding:7px 16px; border-radius:16px; cursor:pointer;">Post comment</button>'
      + '</div>';
    document.getElementById('catPanelClose').addEventListener('click', () => this.setState({ catPanel: null }));
    const postBtn = document.getElementById('catCommentPost');
    const input = document.getElementById('catCommentInput');
    postBtn.addEventListener('click', () => {
      this.postComment('category', slug, input.value, postBtn, () => {
        input.value = '';
        document.getElementById('catCommentList').innerHTML = this.renderCommentList(this.commentsFor('category', slug));
      });
    });
  }

  mount() {
    this.loadComments();
    document.getElementById('mapTab').addEventListener('click', () => this.setView('map'));
    document.getElementById('listTab').addEventListener('click', () => this.setView('list'));
    document.getElementById('jumpBtn').addEventListener('click', () => this.setState({ sheetOpen: true }));
    document.getElementById('sheetDismiss').addEventListener('click', () => this.setState({ sheetOpen: false }));
    document.getElementById('sheetClose').addEventListener('click', () => this.setState({ sheetOpen: false }));
    document.getElementById('zoomInBtn').addEventListener('click', () => this.zoomCenter(this.isNarrow() ? 1.7 : 1.35));
    document.getElementById('zoomOutBtn').addEventListener('click', () => this.zoomCenter(1 / (this.isNarrow() ? 1.7 : 1.35)));
    document.getElementById('fitBtn').addEventListener('click', () => this.setState({ sheetOpen: false, view: 'map' }, () => this.fit()));
    this.render();
    this.bind();
  }
}

new Dash().mount();
</script>
</body>
</html>
"""


def main():
    categories, known_slugs = load_categories()
    members, skipped = load_members(known_slugs)
    tokens = load_design_tokens()
    colors = tokens["colors"]
    css = generate_css(colors)

    if skipped:
        print(f"Skipped {len(skipped)} members with unknown category: {skipped}")

    html = render_html(categories, members, css, colors)

    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(members)} members, {len(categories)} families)")


if __name__ == "__main__":
    main()
