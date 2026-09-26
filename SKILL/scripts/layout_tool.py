#!/usr/bin/env python3
"""Browser workbench for FDCA layout policies.

Run ``python3 SKILL/scripts/layout_tool.py --serve``. The local server solves
configurations in memory and never rewrites the production YAML. Each policy
set renders its landscape and portrait production grids side by side.
"""

from __future__ import annotations

import argparse
import errno
import json
import threading
import webbrowser
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import yaml

from build_dashboard import load_design_tokens
from catalogue_config import load_json
from layout_solver import CONFIG_PATH, OUTPUT_DIR, TAXONOMY_PATH, UnsupportedPolicyError, run

_CACHE: dict[str, dict] = {}


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def config_set(config: dict, path: str, value) -> dict:
    target = config
    keys = path.split(".")
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value
    return config


def options_to_override(options: dict) -> dict:
    geometry_language = options.get("geometry_language", "en")
    return {
        "layout_mode": {"value": options.get("mode", "rectangular")},
        "empty_category_policy": {"value": options.get("empty", "show")},
        "category_order": {"mode": options.get("order", "canonical_stable")},
        "capacity_headroom": {
            "mode": options.get("headroom", "percentage"),
            "fraction": max(0.0, min(0.2, float(options.get("fraction", 0.08)))),
            "slots": max(0, min(8, int(options.get("slots", 2)))),
            "minimum_slots": max(0, min(4, int(options.get("minimum_slots", 1)))),
            "maximum_fraction": max(0.0, min(0.5, float(options.get("maximum_fraction", 0.2)))),
        },
        "language_geometry": {
            "mode": options.get("language_geometry", "maximum_across_languages"),
            "active_language": geometry_language,
            "reference_language": geometry_language,
            "languages": ["en", "fi"],
        },
        "category_font": {
            "mode": options.get("font", "fixed"),
            "size_px": max(10, min(48, float(options.get("font_size", 24)))),
            "minimum_size_px": 10,
            "maximum_size_px": 16,
        },
        "category_title_max_lines": {
            "value": max(1, min(3, int(options.get("title_lines", 2))))
        },
        "layout_stability": {
            "mode": options.get("stability", "soft"),
            "use_previous_layout": options.get("stability", "soft") != "none",
            "near_optimal_tolerance": max(0.0, min(
                0.1, float(options.get("stability_tolerance", 0.02))
            )),
        },
        "reflow": {"mode": options.get("reflow", "on_constraint_change")},
        "short_labels": {
            "mode": options.get("short_labels", "diagnostics_only"),
            "automatic_alias_generation_allowed": options.get("short_labels") == "automatic",
        },
        "layout_selection": {
            "mode": options.get("selection", "configured"),
            "polyomino_minimum_absolute_gain": max(0.0, min(
                0.2, float(options.get("absolute_gain", 0.025))
            )),
            "polyomino_minimum_relative_gain": max(0.0, min(
                1.0, float(options.get("relative_gain", 0.2))
            )),
        },
        "solver": {"strategy": options.get("strategy", "heuristic")},
    }


def _reflow_decision(mode: str, event: str) -> tuple[bool, str]:
    structural = {"policy_change", "taxonomy_change", "label_geometry_change", "format_change"}
    if mode == "always":
        return True, "Recalculated because this policy reflows on every build event."
    if event in structural:
        return True, "Recalculated because the simulated change alters layout constraints."
    if mode == "on_any_count_change" and event in {"count_change", "capacity_overflow"}:
        return True, "Recalculated because a category count changed."
    if event == "capacity_overflow" and mode in {"on_capacity_overflow", "on_constraint_change"}:
        return True, "Recalculated because the current category capacity was exceeded."
    return False, "Kept the current production geometry; this simulated change does not trigger reflow."


def _production_layout(format_name: str) -> dict | None:
    suffix = "" if format_name == "landscape" else "-portrait"
    path = OUTPUT_DIR / f"layout{suffix}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def solve_options(options: dict) -> dict:
    override = options_to_override(options)
    event = options.get("event", "policy_change")
    should_reflow, reason = _reflow_decision(override["reflow"]["mode"], event)
    key = json.dumps([override, event, should_reflow], sort_keys=True, separators=(",", ":"))
    if key not in _CACHE:
        layouts = {}
        for format_name in ("landscape", "portrait"):
            layout = run(format_name, override) if should_reflow else _production_layout(format_name)
            if layout is None:
                layout = run(format_name, override)
                should_reflow = True
                reason = "Recalculated because no saved production geometry was available."
            layout = deepcopy(layout)
            layout["reflow_decision"] = {
                "recalculated": should_reflow, "event": event,
                "policy": override["reflow"]["mode"], "explanation": reason,
            }
            layouts[format_name] = layout
        _CACHE[key] = {"layouts": layouts, "reflow": layouts["landscape"]["reflow_decision"]}
        if len(_CACHE) > 36:
            _CACHE.pop(next(iter(_CACHE)))
    return _CACHE[key]


def search_options(options: dict) -> dict:
    """Benchmark deterministic positioning strategies across both masters."""
    base_options = {key: value for key, value in options.items() if not key.startswith("_")}
    variants = [
        ("Compact recursive", "recursive_treemap", "rectangular", "canonical_stable"),
        ("Compact free-order", "recursive_treemap", "rectangular", "solver_free"),
        ("Category-first Tetris", "recursive_treemap", "polyomino", "solver_free"),
        ("Beam packing", "heuristic", "rectangular", "solver_free"),
        ("Constrained search", "cp_sat", "rectangular", "solver_free"),
        ("Hybrid Tetris", "hybrid", "polyomino", "solver_free"),
    ]
    results = []
    for label, strategy, mode, order in variants:
        candidate_options = deepcopy(base_options)
        candidate_options.update({
            "strategy": strategy, "mode": mode, "order": order,
            "stability": "none", "reflow": "always", "event": "policy_change",
        })
        try:
            layouts = {
                format_name: run(format_name, options_to_override(candidate_options))
                for format_name in ("landscape", "portrait")
            }
        except (ValueError, UnsupportedPolicyError, RuntimeError) as error:
            results.append({"label": label, "error": str(error), "options": candidate_options})
            continue
        diagnostics = {name: layout["diagnostics"] for name, layout in layouts.items()}
        invalid = sum(
            diag["disconnected_family_fragments"]
            + diag["prohibited_void_cells"]
            + diag["one_cell_tendril_cells"]
            for diag in diagnostics.values()
        )
        overview_empty = sum(diag["overview_empty_footprint_cells"]
                             for diag in diagnostics.values())
        empty_bands = sum(diag["family_bbox_empty_band_cells"]
                          for diag in diagnostics.values())
        canvas_area = sum(layout["canvas"]["cells_w"] * layout["canvas"]["cells_h"]
                          for layout in layouts.values())
        score = [
            invalid, overview_empty, empty_bands, canvas_area,
            sum(diag["family_movement_cost_cells"] for diag in diagnostics.values()),
        ]
        results.append({
            "label": label, "options": candidate_options, "score": score,
            "mode": layouts["landscape"]["mode"],
            "strategy": layouts["landscape"]["solver_strategy"],
            "canvases": {name: layout["canvas"] for name, layout in layouts.items()},
            "overview_empty_slots": overview_empty,
            "empty_band_slots": empty_bands,
            "by_format": {
                name: {
                    "overview_empty_slots": diag["overview_empty_footprint_cells"],
                    "empty_band_slots": diag["family_bbox_empty_band_cells"],
                } for name, diag in diagnostics.items()
            },
        })
    valid = [result for result in results if "score" in result]
    valid.sort(key=lambda result: result["score"])
    if not valid:
        raise RuntimeError("No candidate layout strategy produced a valid result")
    return {"best": valid[0], "candidates": valid + [r for r in results if "error" in r]}


POLICIES = [
    {"key": "mode", "label": "Family geometry", "values": ["rectangular", "polyomino", "auto"],
     "help": "Rectangular uses family boxes. Polyomino tests whether their rectangular category boxes can form connected Tetris-like family unions; auto compares both.",
     "tradeoff": "The whole map must remain a solid rectangle. If no hole-free interlock exists, polyomino honestly resolves to the rectangular exact cover instead of exposing grey notches."},
    {"key": "strategy", "label": "Solver strategy", "values": ["recursive_treemap", "heuristic", "cp_sat", "hybrid"],
     "help": "Changes how the solver searches category shapes, family orders and exact-cover placements.",
     "tradeoff": "Every strategy must satisfy the same no-void outer rectangle; broader searches may improve fit but take longer."},
    {"key": "empty", "label": "Empty categories", "values": ["show", "hide", "reserve"],
     "help": "Show draws zero-company boxes; hide removes them; reserve keeps invisible space for future entries.",
     "tradeoff": "Showing aids taxonomy comprehension; hiding is denser; reserving is stable but visually unexplained."},
    {"key": "headroom", "label": "Spare capacity", "values": ["none", "fixed_slots", "percentage", "adaptive"],
     "help": "Controls extra member slots. Adaptive uses a bounded size-based proxy until historical counts exist.",
     "tradeoff": "More spare slots reduce future reflow but enlarge current category boxes."},
    {"key": "order", "label": "Category order", "values": ["taxonomy", "count_descending", "solver_free", "canonical_stable"],
     "help": "Chooses source order, largest-first order, fully solver-oriented order, or limited stable reordering.",
     "tradeoff": "More freedom can pack better while making positions less familiar between releases."},
    {"key": "selection", "label": "Auto-mode selection", "values": ["configured", "best_efficiency", "threshold"],
     "help": "When family geometry is auto, chooses rectangular by policy, the lowest-whitespace result, or a gain threshold.",
     "tradeoff": "Threshold avoids switching visual style for a negligible efficiency gain."},
    {"key": "language_geometry", "label": "Text geometry", "values": ["active_language", "maximum_across_languages", "reference_language"],
     "help": "Sizes boxes for the displayed language, the larger EN/FI requirement, or one fixed reference language.",
     "tradeoff": "Maximum-across-languages keeps EN/FI geometry identical and is the production-safe choice."},
    {"key": "geometry_language", "label": "Geometry language", "values": ["en", "fi"],
     "help": "Sets the active or reference language used by the text-geometry policy.",
     "tradeoff": "This has no effect when maximum-across-languages is selected."},
    {"key": "font", "label": "Category font", "values": ["fixed", "global_adaptive", "per_category_adaptive"],
     "help": "Uses one fixed size, one globally reduced size, or a label-specific fitted size.",
     "tradeoff": "Per-category fitting is compact but weakens typographic consistency."},
    {"key": "title_lines", "label": "Title lines", "values": ["1", "2", "3"],
     "help": "Maximum wrapped lines allowed when estimating category title width.",
     "tradeoff": "One line is clean but wide; three lines are compact but disrupt the visual rhythm."},
    {"key": "stability", "label": "Layout stability", "values": ["none", "soft", "threshold", "locked"],
     "help": "Controls how strongly saved production family positions influence the new feasible solve.",
     "tradeoff": "Stronger stability preserves the mental map, sometimes at an efficiency cost."},
    {"key": "reflow", "label": "Reflow policy", "values": ["always", "on_any_count_change", "on_capacity_overflow", "on_constraint_change"],
     "help": "Decides whether the simulated data event recalculates the grid or retains current production geometry.",
     "tradeoff": "Less frequent reflow is stable and fast, but can postpone packing improvements."},
    {"key": "event", "label": "Simulated change", "values": ["policy_change", "count_change", "capacity_overflow", "taxonomy_change", "label_geometry_change", "format_change"],
     "help": "Supplies the event evaluated by the selected reflow policy.",
     "tradeoff": "A retained result intentionally shows the saved production layout, not a silently ignored solve."},
    {"key": "short_labels", "label": "Short labels", "values": ["disabled", "diagnostics_only", "approved_aliases", "automatic"],
     "help": "Uses full names, measures alias potential, uses taxonomy-approved aliases, or tests deterministic experimental abbreviations.",
     "tradeoff": "Short labels can tighten boxes; automatic wording is experimental and not a production editorial decision."},
]


def meta_payload() -> dict:
    taxonomy = load_json(TAXONOMY_PATH)
    tones = load_design_tokens()["familyColors"]
    return {
        "families": [{
            "slug": family["slug"], "label_en": family["en"], "label_fi": family["fi"],
            "hue": tones[family["slug"]]["hue"], "chroma": tones[family["slug"]]["chromaK"],
        } for family in taxonomy.get("families", [])],
        "policies": POLICIES,
        "invariants": [
            "The masthead and all family regions exactly cover one rectangular outer canvas: no grey interior cells or stepped outer edge.",
            "Category boxes stay rectangular so titles, member order and click targets remain readable.",
            "Polyomino/Tetris geometry applies to connected family unions, where it can remove bounding-box waste.",
            "Both production masters are always rendered: landscape and portrait.",
        ],
    }


TOOL_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FDCA layout workbench</title><style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600;700&display=swap');
:root{font-family:Barlow,ui-sans-serif,system-ui,sans-serif;color:#171929;background:#eef1f5;--blue:#053ab8;--ink:#11182a;--line:#d8dde6}*{box-sizing:border-box}body{margin:0}.top{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:13px 20px;display:flex;align-items:center;gap:18px;justify-content:space-between}.top h1{font:800 21px/1 'Barlow Condensed',sans-serif;letter-spacing:.03em;text-transform:uppercase;margin:0;color:#020381}.top p{margin:4px 0 0;color:#687180;font-size:12px}.actions{display:flex;align-items:center;gap:8px}.actions label{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700}.btn,select,input{border:1px solid #c8d0dc;background:#fff;border-radius:7px;color:var(--ink)}.btn{padding:8px 11px;cursor:pointer;font-weight:600}.btn:hover{border-color:var(--blue)}select,input{width:100%;padding:7px 8px;font:600 12px Barlow,sans-serif}main{padding:16px;max-width:1900px;margin:auto}.scenario{background:#fff;border:1px solid var(--line);border-radius:13px;overflow:hidden;margin-bottom:16px}.scenario-head{display:flex;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid #e7eaf0}.badge{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border-radius:8px;background:#020381;color:#fff;font:800 17px 'Barlow Condensed'}.scenario-head h2{font-size:15px;margin:0}.status{margin-left:auto;font-size:11px;color:#5f6876}.status.error{color:#9d2525}.controls{padding:12px 14px;display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:9px;background:#fbfcfd;border-bottom:1px solid #e7eaf0}.control{min-width:0;border:1px solid #e1e5eb;border-radius:8px;background:#fff;padding:8px}.control-name{display:block;font-size:10px;font-weight:800;letter-spacing:.055em;text-transform:uppercase;color:#4f5868;margin-bottom:5px}.control p{font-size:10px;line-height:1.3;color:#66707e;margin:6px 0 0}.control em{display:block;color:#8a6370;font-style:normal;margin-top:3px}.advanced{border-bottom:1px solid #e7eaf0;background:#fbfcfd}.advanced summary{cursor:pointer;padding:9px 14px;font-size:11px;font-weight:700;color:#4e5868}.numbers{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:9px;padding:0 14px 12px}.number label{font-size:10px;font-weight:700;color:#66707e}.previews{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(115px,.62fr);gap:12px;padding:12px}.preview{min-width:0}.preview-title{display:flex;align-items:baseline;gap:6px;margin:0 2px 6px}.preview-title h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin:0}.preview-title span{font-size:10px;color:#6c7481;margin-left:auto}.preview-title button{font-size:9px;padding:3px 6px}.map-frame{background:#e3e5ea;border:1px solid #cbd1dc;border-radius:8px;padding:6px;min-height:180px;display:flex;align-items:center;justify-content:center;overflow:hidden}.map-frame svg{display:block;width:100%;height:auto;max-height:66vh}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;padding:0 12px 12px}.metric{border:1px solid #e1e5ec;border-radius:7px;padding:7px}.metric b{display:block;font-size:14px}.metric span{font-size:9px;color:#687180;text-transform:uppercase;letter-spacing:.04em}.explain{margin:0 12px 12px;padding:9px 11px;border-left:3px solid #6b78a5;background:#f4f6fa;font-size:11px;line-height:1.45;color:#4f5969}.details{padding:0 12px 12px}.details summary{font-size:11px;color:#4e5868;cursor:pointer}.details pre{font-size:10px;white-space:pre-wrap;background:#f6f8fa;padding:8px;border-radius:6px;max-height:300px;overflow:auto}.invariants{background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 16px}.invariants h2{font-size:13px;margin:0 0 6px}.invariants ul{margin:0;padding-left:18px;font-size:11px;line-height:1.6;color:#56606f}dialog{width:min(96vw,1500px);height:min(92vh,1000px);border:1px solid var(--line);border-radius:12px;padding:10px;background:#eef1f5}dialog::backdrop{background:rgba(7,12,31,.58)}.zoom-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.zoom-content{height:calc(100% - 42px);overflow:auto;display:flex;align-items:flex-start;justify-content:center}.zoom-content svg{min-width:1000px;max-width:none;background:#e3e5ea}@media(max-width:1250px){.controls{grid-template-columns:repeat(4,1fr)}}@media(max-width:800px){.top{position:static;align-items:flex-start;flex-direction:column}.controls{grid-template-columns:repeat(2,1fr)}.metrics{grid-template-columns:repeat(3,1fr)}.numbers{grid-template-columns:repeat(2,1fr)}.map-frame{min-height:130px}}
.metrics{grid-template-columns:repeat(4,1fr);gap:5px;padding:7px 0 0}.metric{appearance:none;text-align:left;cursor:pointer;background:#fff;color:var(--ink);border:1px solid #dce2ea}.metric:hover,.metric:focus-visible{border-color:#3d55a5;outline:none}.metric.active{border-color:#d77716;background:#fff4df;box-shadow:0 0 0 2px rgba(215,119,22,.15)}.metric-note{margin:5px 1px 0;color:#757e8c;font-size:9px}.preset-note{font-size:10px;color:#6b7482}#searchResults{margin-bottom:12px}#searchResults p,#searchResults li{font-size:11px;color:#56606f}#searchResults ul{margin:6px 0 0;padding-left:18px}@media(max-width:800px){.metrics{grid-template-columns:repeat(2,1fr)}}
</style></head><body><header class="top"><div><h1>FDCA layout workbench</h1><p>Production box-grid geometry · lightweight member placeholders · configuration stays unchanged</p></div><div class="actions"><label>Visible text <select id="displayLang"><option value="en">English</option><option value="fi">Finnish</option><option value="both">English + Finnish</option></select></label><button class="btn" id="search">Search algorithms → B</button><button class="btn" id="copy">Copy A → B</button><button class="btn" id="swap">Swap</button></div></header><main><section id="searchResults" class="invariants" hidden></section><div id="scenarios"></div><section class="invariants"><h2>Fixed visual requirements</h2><ul id="invariants"></ul></section></main><dialog id="zoomDialog"><div class="zoom-top"><strong id="zoomTitle"></strong><button class="btn" id="zoomClose">Close</button></div><div class="zoom-content" id="zoomContent"></div></dialog>
<script>
const PX=196,PY=218,CW=168,CH=190,GAP=14,TIN=7;
const defaults={mode:'rectangular',strategy:'recursive_treemap',empty:'hide',headroom:'none',fraction:.08,slots:2,minimum_slots:1,maximum_fraction:.2,order:'canonical_stable',selection:'configured',absolute_gain:.025,relative_gain:.2,language_geometry:'maximum_across_languages',geometry_language:'en',font:'fixed',font_size:24,title_lines:'2',stability:'none',stability_tolerance:.02,reflow:'on_constraint_change',event:'policy_change',short_labels:'disabled'};
const stableDefaults={...defaults,empty:'show',headroom:'percentage',stability:'soft',short_labels:'diagnostics_only'};
const state={meta:null,displayLang:'en',panes:{a:{...defaults},b:{...stableDefaults}}};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const policy=k=>state.meta.policies.find(p=>p.key===k);
function control(p,s){return `<div class="control"><span class="control-name">${esc(p.label)}</span><select data-key="${p.key}">${p.values.map(v=>`<option value="${v}" ${String(s[p.key])===String(v)?'selected':''}>${esc(v.replaceAll('_',' '))}</option>`).join('')}</select><p>${esc(p.help)}<em>${esc(p.tradeoff)}</em></p></div>`}
function controls(s){const primary=['mode','strategy','empty','headroom','order','selection','language_geometry'];const secondary=['geometry_language','font','title_lines','stability','reflow','event','short_labels'];return `<div class="controls">${primary.map(k=>control(policy(k),s)).join('')}</div><details class="advanced"><summary>More policies: language, typography, stability, reflow and labels</summary><div class="controls">${secondary.map(k=>control(policy(k),s)).join('')}</div><div class="numbers"><div class="number"><label>Headroom percentage<input data-key="fraction" type="number" min="0" max="0.2" step="0.01" value="${s.fraction}"></label></div><div class="number"><label>Fixed spare slots<input data-key="slots" type="number" min="0" max="8" value="${s.slots}"></label></div><div class="number"><label>Minimum spare slots<input data-key="minimum_slots" type="number" min="0" max="4" value="${s.minimum_slots}"></label></div><div class="number"><label>Maximum fraction<input data-key="maximum_fraction" type="number" min="0" max="0.5" step="0.01" value="${s.maximum_fraction}"></label></div><div class="number"><label>Base font px<input data-key="font_size" type="number" min="10" max="48" value="${s.font_size}"></label></div><div class="number"><label>Stability tolerance<input data-key="stability_tolerance" type="number" min="0" max="0.1" step="0.01" value="${s.stability_tolerance}"></label></div><div class="number"><label>Auto absolute gain<input data-key="absolute_gain" type="number" min="0" max="0.2" step="0.005" value="${s.absolute_gain}"></label></div><div class="number"><label>Auto relative gain<input data-key="relative_gain" type="number" min="0" max="1" step="0.05" value="${s.relative_gain}"></label></div></div></details>`}
function tone(slug,role){const f=state.meta.families.find(x=>x.slug===slug)||{hue:262,chroma:.4};const v={surface:[.972,.019],group:[.992,.01],border:[.88,.048],groupBorder:[.93,.026],ink:[.415,.115],mark:[.62,.115]}[role];return `oklch(${v[0]} ${v[1]*f.chroma} ${f.hue})`}
function label(c){if(state.displayLang==='fi')return c.label_fi||c.label_en;if(state.displayLang==='both')return `${c.label_en||''} / ${c.label_fi||c.label_en||''}`;return c.label_en||c.label_fi||''}
function svgLayout(l,highlight=''){const W=l.canvas.cells_w*PX,H=l.canvas.cells_h*PY;let out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(l.format)} solved FDCA layout">`;
for(const f of l.categories){const fx=f.x*PX,fy=f.y*PY,fw=f.w*PX-GAP,fh=f.h*PY-GAP;if(f.is_masthead){const ops=(l.categories.find(x=>x.slug==='data_center_operators')||{}).member_count||0,total=l.diagnostics.company_count;const en=`The Finnish Data Center Association is the full ecosystem association for Finland’s data center industry, representing ${total} member organisations: ${ops} data center operators and ${total-ops} supply chain organisations.`;const fi=`Datakeskusteollisuus on koko Suomen datakeskusalan ekosysteemiyhdistys, johon kuuluu ${total} jäsenorganisaatiota: ${ops} datakeskusoperaattoria ja ${total-ops} toimitusketjun organisaatiota.`;const body=state.displayLang==='fi'?fi:state.displayLang==='both'?en+' / '+fi:en;const placeholder=state.displayLang==='fi'?`Hae ${total} yrityksestä — nimi, palvelu, teknologia`:`Search ${total} companies — name, service, technology`;out+=`<rect x="${fx}" y="${fy}" width="${fw}" height="${fh}" rx="14" fill="#fff" stroke="#cfd5df" stroke-width="2"/><foreignObject x="${fx+70}" y="${fy+55}" width="${Math.max(1,fw-140)}" height="${Math.max(1,fh-110)}"><div xmlns="http://www.w3.org/1999/xhtml" style="height:100%;display:flex;flex-direction:column;justify-content:space-between;gap:36px;color:#020381;font-family:Barlow,sans-serif"><strong style="font:800 112px/1 Barlow Condensed,sans-serif;letter-spacing:.03em">FDCA</strong><span style="font:500 46px/1.35 Barlow,sans-serif;max-width:95%">${esc(body)}</span><div style="height:112px;border:3px solid #d8dde6;border-radius:58px;display:flex;align-items:center;padding:0 44px;color:#8b919b;font-size:34px">⌕ &nbsp; ${esc(placeholder)}</div></div></foreignObject>`;continue}
for(const s of f.shape_rects||[]){out+=`<rect x="${(f.x+s.x)*PX}" y="${(f.y+s.y)*PY}" width="${s.w*PX-GAP}" height="${s.h*PY-GAP}" rx="12" fill="${tone(f.slug,'surface')}" stroke="${tone(f.slug,'border')}" stroke-width="2"/>`}
for(const c of f.subcats||[]){if(c.reserved||c.visible===false)continue;const x=c.x*PX,y=c.y*PY,w=c.w*PX-GAP,h=c.h*PY-GAP;out+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" fill="${tone(f.slug,'group')}" stroke="${tone(f.slug,'groupBorder')}" stroke-width="2"/>`;const fs=Math.max(12,Number(c.font_size_px||24));out+=`<foreignObject x="${x+13}" y="${y}" width="${Math.max(1,w-26)}" height="${PY-GAP}"><div xmlns="http://www.w3.org/1999/xhtml" style="height:100%;display:flex;align-items:center;overflow:hidden;font:700 ${fs}px/.98 Barlow Condensed,sans-serif;letter-spacing:.035em;text-transform:uppercase;color:${tone(f.slug,'ink')};overflow-wrap:anywhere">${esc(label(c))}</div></foreignObject>`;for(let k=0;k<c.dots.count;k++){const tx=(c.x+(k%c.w))*PX+TIN,ty=(c.y+1+Math.floor(k/c.w))*PY+TIN;out+=`<circle cx="${tx+CW/2}" cy="${ty+CH/2}" r="19" fill="${tone(f.slug,'mark')}" opacity=".86"/>`}}
}const cells=(l.diagnostics.highlight_cells||{})[highlight]||[];if(cells.length){out+=`<g aria-label="${esc(highlight)} highlighted grid slots">`;for(const c of cells){out+=`<rect x="${c.x*PX+4}" y="${c.y*PY+4}" width="${PX-12}" height="${PY-12}" rx="18" fill="#ffb13b" fill-opacity=".48" stroke="#a95000" stroke-width="7"/>`}out+='</g>'}return out+'</svg>'}
const metricDefs=[['overview_empty','Overview empty slots','overview_empty_footprint_cells','All suboptimally used slots: visual padding, reserved cells and unused dot positions.'],['geometric_whitespace','Visual growth slots','visual_whitespace_cells','Visible grid area reserved beyond category content; dot capacity is counted separately.'],['spare_slots','Unused dot slots','spare_dot_capacity','Allocated member positions that currently contain no company.'],['category_padding','Category growth slots','category_internal_padding_cells','Extra cells inside category rectangles, beyond their title and current dot rows.'],['family_slack','Family slack slots','family_internal_slack_cells','Empty slots inside a rectangular family boundary but outside category boxes.'],['canvas_whitespace','Canvas empty slots','whole_canvas_unused_cells','Grey cells not assigned to the masthead or any family. An accepted layout must have zero.'],['empty_bands','Empty-band slots','family_bbox_empty_band_cells','Slots in long empty runs inside family bounds.'],['holes','Prohibited void slots','prohibited_void_cells','Any grey canvas void or enclosed family hole. An accepted layout must have zero.']];
function metrics(d,active){return metricDefs.map(([key,label,field,help])=>`<button class="metric ${active===key?'active':''}" data-metric="${key}" title="${esc(help)}" aria-pressed="${active===key}"><b>${d[field]}</b><span>${label}</span></button>`).join('')}
function scenarioBody(id){const name=id==='a'?'Recommended compact baseline':'Reserved-capacity stress test',note=id==='b'?'<span class="preset-note">Shows empty categories and adds spare member capacity</span>':'';return `<div class="scenario-head"><span class="badge">${id.toUpperCase()}</span><h2>${name}</h2>${note}<button class="btn" data-reset="1">Reset</button><span class="status">Waiting to solve…</span></div>${controls(state.panes[id])}<div class="previews"><article class="preview" data-format="landscape"><div class="preview-title"><h3>Landscape master</h3><span></span><button class="btn" data-expand="landscape">Open large</button></div><div class="map-frame"></div><div class="metrics"></div><p class="metric-note">Click a metric to highlight its exact landscape grid slots.</p></article><article class="preview" data-format="portrait"><div class="preview-title"><h3>Portrait master</h3><span></span><button class="btn" data-expand="portrait">Open large</button></div><div class="map-frame"></div><div class="metrics"></div><p class="metric-note">Click a metric to highlight its exact portrait grid slots.</p></article></div><p class="explain"></p><details class="details"><summary>Full diagnostics for both masters</summary><pre></pre></details>`}
function renderResult(id,data){const pane=document.querySelector(`[data-pane="${id}"]`);for(const fmt of ['landscape','portrait']){const l=data.layouts[fmt],p=pane.querySelector(`[data-format="${fmt}"]`),active=p.dataset.highlight||'';p.querySelector('.map-frame').innerHTML=svgLayout(l,active);p.querySelector('.metrics').innerHTML=metrics(l.diagnostics,active);p.querySelectorAll('[data-metric]').forEach(button=>button.onclick=()=>{p.dataset.highlight=p.dataset.highlight===button.dataset.metric?'':button.dataset.metric;renderResult(id,data)});p.querySelector('.preview-title span').textContent=`${l.canvas.cells_w}×${l.canvas.cells_h} cells · ${l.mode}`};const d=data.layouts.landscape.diagnostics;pane.querySelector('.explain').textContent=`Layout explanation: ${data.reflow.explanation} ${d.layout_mode_explanation} ${d.masthead_height_explanation} Solver: ${d.solver_strategy_explanation}`;pane.querySelector('pre').textContent=JSON.stringify({reflow:data.reflow,landscape:data.layouts.landscape.diagnostics,portrait:data.layouts.portrait.diagnostics},null,2);pane.querySelector('.status').textContent=`${data.layouts.landscape.mode} · ${data.layouts.landscape.solver_strategy} · ${d.company_count} companies`}
async function solve(id){const pane=document.querySelector(`[data-pane="${id}"]`),status=pane.querySelector('.status');status.className='status';status.textContent='Solving both masters…';try{const r=await fetch('/api/solve',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(state.panes[id])}),d=await r.json();if(!r.ok)throw new Error(d.error||'Solve failed');state.panes[id]._result=d;renderResult(id,d)}catch(e){status.className='status error';status.textContent=e.message}}
let timers={};function bind(id){const pane=document.querySelector(`[data-pane="${id}"]`);pane.innerHTML=scenarioBody(id);pane.querySelector('[data-reset]').addEventListener('click',()=>{state.panes[id]={...(id==='a'?defaults:stableDefaults)};bind(id)});pane.querySelectorAll('[data-key]').forEach(i=>i.addEventListener('input',()=>{const k=i.dataset.key;state.panes[id][k]=i.type==='number'?Number(i.value):i.value;clearTimeout(timers[id]);timers[id]=setTimeout(()=>solve(id),180)}));pane.querySelectorAll('[data-expand]').forEach(b=>b.addEventListener('click',()=>{const result=state.panes[id]._result;if(!result)return;const fmt=b.dataset.expand,preview=pane.querySelector(`[data-format="${fmt}"]`);document.getElementById('zoomTitle').textContent=`Policy ${id.toUpperCase()} · ${fmt}`;document.getElementById('zoomContent').innerHTML=svgLayout(result.layouts[fmt],preview.dataset.highlight||'');document.getElementById('zoomDialog').showModal()}));solve(id)}
function mount(){document.getElementById('scenarios').innerHTML='<section class="scenario" data-pane="a"></section><section class="scenario" data-pane="b"></section>';document.getElementById('invariants').innerHTML=state.meta.invariants.map(x=>`<li>${esc(x)}</li>`).join('');bind('a');bind('b')}
document.getElementById('displayLang').onchange=e=>{state.displayLang=e.target.value;for(const id of ['a','b'])if(state.panes[id]._result)renderResult(id,state.panes[id]._result)};
document.getElementById('zoomClose').onclick=()=>document.getElementById('zoomDialog').close();
document.getElementById('search').onclick=async()=>{const button=document.getElementById('search'),panel=document.getElementById('searchResults');button.disabled=true;button.textContent='Searching…';panel.hidden=false;panel.innerHTML='<h2>Algorithm search</h2><p>Running both masters through several deterministic positioning strategies…</p>';try{const response=await fetch('/api/search',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(state.panes.a)}),data=await response.json();if(!response.ok)throw new Error(data.error||'Search failed');const best=data.best,summary=c=>`landscape ${c.by_format.landscape.overview_empty_slots}, portrait ${c.by_format.portrait.overview_empty_slots}`;panel.innerHTML=`<h2>Algorithm search · best copied to B</h2><p><strong>${esc(best.label)}</strong> found ${best.overview_empty_slots} total suboptimal slots across both masters (${summary(best)}). Ranking prioritizes valid geometry, then absolute empty slots and empty-band slots.</p><ul>${data.candidates.map(c=>c.error?`<li>${esc(c.label)}: ${esc(c.error)}</li>`:`<li>${esc(c.label)} — ${c.overview_empty_slots} total empty slots (${summary(c)}), ${c.empty_band_slots} empty-band slots</li>`).join('')}</ul>`;state.panes.b={...best.options};bind('b')}catch(error){panel.innerHTML=`<h2>Algorithm search failed</h2><p>${esc(error.message)}</p>`}finally{button.disabled=false;button.textContent='Search algorithms → B'}};
document.getElementById('copy').onclick=()=>{state.panes.b=structuredClone(state.panes.a);delete state.panes.b._result;bind('b')};document.getElementById('swap').onclick=()=>{[state.panes.a,state.panes.b]=[state.panes.b,state.panes.a];bind('a');bind('b')};fetch('/api/meta').then(r=>r.json()).then(m=>{state.meta=m;mount()});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/meta":
            self._json(meta_payload())
        elif path in {"/", "/index.html"}:
            body = TOOL_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/api/solve", "/api/search"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            options = json.loads(self.rfile.read(length) or b"{}")
            self._json(search_options(options) if path == "/api/search" else solve_options(options))
        except (ValueError, UnsupportedPolicyError, RuntimeError) as error:
            self._json({"error": str(error)}, 422)
        except Exception as error:
            self._json({"error": f"Unexpected solver error: {error}"}, 500)

    def log_message(self, fmt: str, *args) -> None:
        print(f"layout-tool: {fmt % args}")


def print_diagnostics(name: str, layout: dict) -> None:
    diag = layout["diagnostics"]
    print(f"{name}: {layout['mode']} {diag['canvas_cells']['w']}×{diag['canvas_cells']['h']} · "
          f"overview empty {diag['overview_empty_footprint_cells']} slots · "
          f"geometric empty {diag['visual_whitespace_cells']} slots · "
          f"family slack {diag['family_internal_slack_cells']} slots · "
          f"spare dots {diag['spare_dot_capacity']} slots")


def compare(path: str, first: str, second: str, format_name: str) -> None:
    layouts = []
    for value in (first, second):
        override = deepcopy(load_config())
        config_set(override, path if "." in path else f"{path}.value", value)
        layouts.append(run(format_name, override))
    print_diagnostics(first, layouts[0])
    print_diagnostics(second, layouts[1])


def serve(host: str, port: int, open_browser: bool) -> None:
    server = None
    for candidate in range(port, port + 20):
        try:
            server = HTTPServer((host, candidate), Handler)
            if candidate != port:
                print(f"Port {port} is already in use; using {candidate} instead.")
            break
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
    if server is None:
        raise OSError(
            errno.EADDRINUSE,
            f"No available port found in the range {port}-{port + 19}",
        )
    url = f"http://{host}:{server.server_port}/"
    print(f"FDCA layout workbench: {url}")
    print("Press Ctrl-C to stop. Production configuration is not modified.")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="FDCA browser layout workbench")
    parser.add_argument("--serve", action="store_true", help="launch the browser workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--compare", nargs=3, metavar=("POLICY", "A", "B"))
    parser.add_argument("--format", default="landscape", choices=["landscape", "portrait"])
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare, args.format)
    else:
        serve(args.host, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
