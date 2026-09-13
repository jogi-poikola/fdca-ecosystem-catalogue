#!/usr/bin/env python3
"""
FDCA Ecosystem Map — Layout Solver
===================================
Python port of the cell-grid treemap packer from build_dashboard.py.
Reads member registry + taxonomy + layout_config.yaml, produces a
cell-grid layout JSON consumed by the dashboard's JS renderer.

Output model follows INPUT/FDCA_LAYOUT_SPEC_v1.1.md §20:
  - Cell-grid coordinates (no pixel conversion — the JS does that)
  - Bilingual label data for both EN and FI
  - Dot grid dimensions per subcategory
  - Diagnostics block

Usage:
  python3 layout_solver.py                    # write OUTPUT/layout.json
  python3 layout_solver.py --format portrait  # write OUTPUT/layout-portrait.json
  python3 layout_solver.py --diagnostics      # print diagnostics to stdout
"""

from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

import yaml

from catalogue_config import load_json, taxonomy_index

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
CONFIG_PATH = Path(__file__).with_name("layout_config.yaml")
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
TAXONOMY_PATH = INPUT_DIR / "fdca-categories.json"

# ── Grid constants ──────────────────────────────────────────────
CELL_W, CELL_H = 168, 190
GAP, TIN = 14, 7
PITCH_X = CELL_W + GAP + TIN * 2  # 196
PITCH_Y = CELL_H + GAP + TIN * 2  # 226
CELL_RATIO = PITCH_Y / PITCH_X    # ≈1.153

# Pinned family slug
PINNED_FAMILY = "data_center_operators"

# ── Helpers ─────────────────────────────────────────────────────


def _load_config() -> dict:
    """Load layout_config.yaml, resolving the flat YAML keys into a
    nested structure matching the spec's §26 policy variables."""
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return raw


def _build_cats(taxonomy_indexes: dict, members: list[dict], families_order: list[str]) -> list[dict]:
    """Organize members into categories/groups for packing.

    Mirrors the JS buildCats() but returns both EN and FI label data
    so the solver can measure across languages (§5: bilingual geometry).
    """
    # Group members by family slug
    by_family: dict[str, list[dict]] = {}
    for m in members:
        fam = m.get("cat", "")
        by_family.setdefault(fam, []).append(m)

    # Build ordered category list (taxonomy order, but pinned first)
    order = [s for s in families_order if s in by_family]
    for s in by_family:
        if s not in order:
            order.append(s)

    cats = []
    families = taxonomy_indexes["family_by_slug"]
    for slug in order:
        family = families.get(slug, {})
        subcat_slugs = [
            c["slug"]
            for c in family.get("categories", [])
            if c["slug"] != slug
        ]
        list_members = by_family.get(slug, [])

        # Build subcategory groups for both languages
        subcat_map = {
            c["slug"]: c for c in family.get("categories", [])
        }

        groups_en = []
        groups_fi = []
        if subcat_slugs:
            for s_slug in subcat_slugs:
                g = [m for m in list_members if m.get("subcat") == s_slug]
                meta = subcat_map.get(s_slug, {})
                if g:
                    groups_en.append({
                        "slug": s_slug,
                        "label": meta.get("en", s_slug),
                        "description": meta.get("description_en", ""),
                        "items": g,
                    })
                    groups_fi.append({
                        "slug": s_slug,
                        "label": meta.get("fi", meta.get("en", s_slug)),
                        "description": meta.get("description_fi", ""),
                        "items": g,
                    })
            # Rest (members whose subcat slug doesn't match any subcategory)
            rest = [m for m in list_members if m.get("subcat") not in subcat_slugs]
            if rest:
                groups_en.append({
                    "slug": slug,
                    "label": family.get("en", slug),
                    "description": family.get("description_en", ""),
                    "items": rest,
                })
                groups_fi.append({
                    "slug": slug,
                    "label": family.get("fi", family.get("en", slug)),
                    "description": family.get("description_fi", ""),
                    "items": rest,
                })
        else:
            groups_en.append({
                "slug": slug,
                "label": family.get("en", slug),
                "description": family.get("description_en", ""),
                "items": list_members,
            })
            groups_fi.append({
                "slug": slug,
                "label": family.get("fi", family.get("en", slug)),
                "description": family.get("description_fi", ""),
                "items": list_members,
            })

        cats.append({
            "slug": slug,
            "label_en": family.get("en", slug),
            "label_fi": family.get("fi", family.get("en", slug)),
            "groups_en": groups_en,
            "groups_fi": groups_fi,
            "member_count": len(list_members),
        })

    # Sort: pinned first, then by member count descending
    cats.sort(key=lambda c: (0 if c["slug"] == PINNED_FAMILY else 1, -c["member_count"]))
    return cats


def _compute_min_label_width(cats: list[dict]) -> int:
    """Compute MIN_LABEL_WIDTH in cells from the longest subcategory label
    across both languages. Barlow Condensed 700 uppercase ≈ 0.58 × fontSize px."""
    max_len = 0
    for c in cats:
        for g in c.get("groups_en", []):
            label = g.get("label", "")
            if label:
                max_len = max(max_len, len(label))
        for g in c.get("groups_fi", []):
            label = g.get("label", "")
            if label:
                max_len = max(max_len, len(label))
    px_needed = max(0, max_len) * 0.5 * 11.6 + 26
    return max(2, math.ceil(px_needed / PITCH_X))


def tile_int(items: list[dict], x0: int, y0: int, w0: int, h0: int) -> list[dict]:
    """Recursive area-proportional split along the longer axis.
    Port of JS tileInt(). items is [{idx, cells}, ...]."""
    out: list[dict] = []

    def rec(lst: list[dict], x: int, y: int, w: int, h: int) -> None:
        if not lst or w < 1 or h < 1:
            return
        if len(lst) == 1:
            out.append({"idx": lst[0]["idx"], "x": x, "y": y, "w": w, "h": h})
            return
        total = sum(i["cells"] for i in lst)
        acc = 0
        idx = 0
        for i in range(len(lst) - 1):
            acc += lst[i]["cells"]
            idx = i
            if acc >= total / 2:
                break
        A, B = lst[: idx + 1], lst[idx + 1 :]
        sa = sum(i["cells"] for i in A)
        sb = total - sa

        if w >= h:
            w1 = max(1, min(w - 1, round(w * sa / total)))
            while w1 < w - 1 and w1 * h < sa:
                w1 += 1
            while w1 > 1 and (w - w1) * h < sb:
                w1 -= 1
            rec(A, x, y, w1, h)
            rec(B, x + w1, y, w - w1, h)
        else:
            h1 = max(1, min(h - 1, round(h * sa / total)))
            while h1 < h - 1 and w * h1 < sa:
                h1 += 1
            while h1 > 1 and w * (h - h1) < sb:
                h1 -= 1
            rec(A, x, y, w, h1)
            rec(B, x, y + h1, w, h - h1)

    rec(items[:], x0, y0, w0, h0)
    return out


def _has_label(groups: list[dict], idx: int) -> bool:
    """Does group at idx have a display label?"""
    return bool(groups[idx].get("label"))


def pack_cat(cat: dict, wc: int, hc: int, min_label_width: int) -> dict | None:
    """Pack one family block's subcategory groups into wc×hc cells.
    Returns {leaves: [{idx, x, y, w, h}, ...], used_rows: int} or None on failure.
    Port of JS packCat()."""
    if hc < 2 or wc < 1:
        return None

    groups = cat.get("groups_en", [])  # use EN groups (labels exist for geometry)
    if not groups:
        return {"leaves": [], "used_rows": hc}

    # Initial demand: items + 2 extra cells for labeled groups
    dem = [
        (len(g["items"]) + (2 if g.get("label") else 0))
        for g in groups
    ]

    good = None
    for _ in range(18):  # max iterations
        items = [{"idx": i, "cells": dem[i]} for i in range(len(groups))]
        leaves = tile_int(items, 0, 0, wc, hc)

        ok = len(leaves) == len(groups)
        for leaf in leaves:
            g = groups[leaf["idx"]]
            hr = 1 if g.get("label") else 0
            cap = leaf["w"] * max(0, leaf["h"] - hr)
            if len(g["items"]) > cap:
                ok = False
                dem[leaf["idx"]] = len(g["items"]) + (hr + 1) * leaf["w"]
            elif hr and leaf["w"] < min_label_width:
                ok = False
                dem[leaf["idx"]] = min_label_width * (
                    1 + math.ceil(len(g["items"]) / min_label_width)
                )

        if ok:
            good = leaves
            # Refine demand to actual used cells
            next_dem = dem[:]
            for leaf in leaves:
                g = groups[leaf["idx"]]
                hr = 1 if g.get("label") else 0
                next_dem[leaf["idx"]] = leaf["w"] * (
                    hr + max(1, math.ceil(len(g["items"]) / leaf["w"]))
                )
            if all(next_dem[i] == dem[i] for i in range(len(dem))):
                break
            dem = next_dem

    if not good:
        return None

    # Reject layouts with too-narrow labeled subcategories
    for leaf in good:
        if _has_label(groups, leaf["idx"]) and leaf["w"] < min_label_width:
            return None

    used_rows = max(leaf["y"] + leaf["h"] for leaf in good)
    return {"leaves": good, "used_rows": used_rows}


def dem_of(cat: dict, min_label_width: int, target_aspect: float) -> int:
    """Estimate cell demand for a category block. Port of JS demOf().
    target_aspect = (format_w/format_h) * CELL_RATIO — the format-aware
    cell-space aspect ratio that drives the canvas-shape estimate."""
    groups = cat.get("groups_en", [])
    n = cat["member_count"] + sum(1 for g in groups if g.get("label"))
    area = n + max(2, math.ceil(math.sqrt(n * target_aspect)))
    has_labeled = any(g.get("label") for g in groups)
    return max(area, min_label_width * 2) if has_labeled else area


def solve_layout(
    cats: list[dict],
    target_aspect: float,
    min_label_width: int,
    max_iterations: int = 30,
    refinement_passes: int = 5,
) -> dict | None:
    """Solve the full family-level layout. Port of JS layout().

    Returns plan dict:
      {res: [{idx, L: {x,y,w,h}, p: pack_result}, ...],
       W: int, H: int, title_h: int}
    or None if infeasible.
    """
    # Initial demand
    cdem = [dem_of(c, min_label_width, target_aspect) for c in cats]

    title_frac = 0.5  # fraction of width for masthead

    def build() -> dict | None:
        T = sum(cdem)
        W = max(8, round(math.sqrt(T * target_aspect)))
        title_w = max(2, min(W - 3, round(W * title_frac)))
        right_w = W - title_w

        # Items for tile-int (skip cat[0] which is the masthead placeholder)
        items = []
        for i in range(1, len(cats)):
            items.append({"idx": i, "cells": cdem[i]})

        # Split into top-right row (A) and bottom rows (B)
        # Estimate title height from aspect ratio
        h_aspect = max(4, round((title_w * PITCH_X) / (2.0 * PITCH_Y)))

        A: list[dict] = []
        B: list[dict] = []
        acc = 0
        for it in items:
            forced = len(A) == 0 and right_w >= 1
            if forced or acc + it["cells"] <= right_w * h_aspect:
                A.append(it)
                acc += it["cells"]
            else:
                B.append(it)

        # Compute needed title height
        need_a = sum(
            cats[it["idx"]]["member_count"]
            + sum(
                1 for g in cats[it["idx"]].get("groups_en", []) if g.get("label")
            )
            * max(1, round(right_w / max(1, len(A))))
            for it in A
        )
        h_lo = math.ceil((title_w * PITCH_X) / (2.8 * PITCH_Y))
        h_hi = math.floor((title_w * PITCH_X) / (1.5 * PITCH_Y))
        title_h = max(4, min(max(h_lo, math.ceil(need_a / max(1, right_w))), max(h_lo, h_hi)))

        # Trim A if too many cells for title height
        while len(A) > 1 and sum(it["cells"] for it in A) > right_w * title_h:
            B.insert(0, A.pop())

        sum_b = sum(it["cells"] for it in B)
        bottom_rows = max(2, math.ceil(sum_b / max(1, W)))

        # Tile-int top-right and bottom
        leaves: list[dict] = []
        if A:
            for leaf in tile_int(A, title_w, 0, right_w, title_h):
                leaves.append(leaf)
        if B:
            for leaf in tile_int(B, 0, title_h, W, bottom_rows):
                leaves.append(leaf)

        if len(leaves) != len(cats) - 1:
            return None

        # Pack each category
        result = [
            {
                "idx": 0,
                "L": {"x": 0, "y": 0, "w": title_w, "h": title_h},
                "p": {"leaves": [], "used_rows": title_h},
            }
        ]

        ok = True
        for leaf in leaves:
            cat_idx = leaf["idx"]
            p = pack_cat(cats[cat_idx], leaf["w"], leaf["h"], min_label_width)
            if not p:
                ok = False
                cdem[cat_idx] += max(2, leaf["w"])
                continue
            result.append({"idx": cat_idx, "L": leaf, "p": p})

        if not ok:
            return None
        return {
            "res": result,
            "W": W,
            "H": title_h + bottom_rows,
            "title_h": title_h,
            "title_w": title_w,
        }

    # Main iteration loop
    plan = None
    for _ in range(max_iterations):
        plan = build()
        if plan:
            break

    if plan:
        # Refinement passes: tighten demand to actual used rows
        for _ in range(refinement_passes):
            next_cdem = cdem[:]
            for r in plan["res"]:
                idx = r["idx"]
                if idx == 0:
                    continue
                next_cdem[idx] = r["L"]["w"] * r["p"]["used_rows"]
            next_cdem[0] = cdem[0]  # keep masthead demand
            if all(next_cdem[i] == cdem[i] for i in range(len(cdem))):
                break
            prev_cdem = cdem[:]
            cdem = next_cdem
            p2 = build()
            if not p2:
                cdem = prev_cdem
                break
            plan = p2

    # Fallback: simple proportional demand
    if not plan:
        cdem = [c["member_count"] * 3 + 6 for c in cats]
        plan = build()

    return plan


def build_layout_json(
    plan: dict,
    cats: list[dict],
    families_order: list[str],
    config: dict,
    format_name: str,
    taxonomy_indexes: dict,
) -> dict:
    """Convert the solver plan into the layout JSON output model (§20)."""

    # Map group slugs to taxonomy data for EN/FI labels
    families = taxonomy_indexes["family_by_slug"]

    categories_out = []
    for r in plan["res"]:
        idx = r["idx"]
        cat = cats[idx]
        slug = cat["slug"]
        family = families.get(slug, {})
        L = r["L"]

        # Build subcategory entries
        subcats_out = []
        if idx > 0 and r["p"]["leaves"]:  # not masthead
            groups = cat.get("groups_en", [])
            groups_fi = cat.get("groups_fi", [])
            for leaf in r["p"]["leaves"]:
                g = groups[leaf["idx"]]
                g_fi = groups_fi[leaf["idx"]] if leaf["idx"] < len(groups_fi) else g
                items_n = len(g["items"])
                cols = leaf["w"]
                rows = max(1, math.ceil(items_n / max(1, cols)))
                capacity = cols * rows

                subcats_out.append({
                    "slug": g["slug"],
                    "label_en": g.get("label", ""),
                    "label_fi": g_fi.get("label", ""),
                    "x": L["x"] + leaf["x"],
                    "y": L["y"] + leaf["y"],
                    "w": leaf["w"],
                    "h": leaf["h"],
                    "dots": {
                        "count": items_n,
                        "capacity": capacity,
                        "cols": cols,
                        "rows": rows,
                    },
                })

        categories_out.append({
            "slug": slug,
            "family": slug,
            "label_en": family.get("en", slug),
            "label_fi": family.get("fi", family.get("en", slug)),
            "x": L["x"],
            "y": L["y"],
            "w": L["w"],
            "h": r["p"]["used_rows"],
            "is_masthead": idx == 0,
            "subcats": subcats_out,
            "member_count": cat["member_count"],
        })

    # Compute diagnostics (§21)
    total_cells = plan["W"] * plan["H"]
    occupied_cells = sum(
        c["w"] * c["h"] for c in categories_out if not c["is_masthead"]
    )
    masthead_cells = sum(
        c["w"] * c["h"] for c in categories_out if c["is_masthead"]
    )
    total_area = total_cells
    unused_cells = total_area - occupied_cells - masthead_cells
    unused_pct = round(unused_cells / max(1, total_area) * 100, 1)

    total_companies = sum(c["member_count"] for c in cats)
    total_dot_capacity = sum(
        s["dots"]["capacity"]
        for c in categories_out
        for s in c.get("subcats", [])
    )
    # Category aspect ratios
    aspects = [
        c["w"] / max(1, c["h"])
        for c in categories_out
        if not c["is_masthead"] and c["w"] > 0 and c["h"] > 0
    ]

    diagnostics = {
        "occupied_area_pct": round((occupied_cells + masthead_cells) / max(1, total_area) * 100, 1),
        "unused_area_pct": unused_pct,
        "company_count": total_companies,
        "total_dot_capacity": total_dot_capacity,
        "spare_dot_capacity": total_dot_capacity - total_companies,
        "max_category_aspect_ratio": round(max(aspects), 1) if aspects else 0,
        "mean_category_aspect_ratio": round(sum(aspects) / len(aspects), 2) if aspects else 0,
        "canvas_cells": {"w": plan["W"], "h": plan["H"]},
        "cell_pitch": {"x": PITCH_X, "y": PITCH_Y},
        "canvas_px": {"w": plan["W"] * PITCH_X, "h": plan["H"] * PITCH_Y},
    }

    # Anchor positions
    masthead_cat = next((c for c in categories_out if c["is_masthead"]), None)
    pinned_cat = next((c for c in categories_out if c["slug"] == PINNED_FAMILY), None)

    return {
        "format": format_name,
        "mode": config.get("layout_mode", {}).get("value", "rectangular"),
        "canvas": {"cells_w": plan["W"], "cells_h": plan["H"]},
        "anchors": {
            "masthead": {
                "x": masthead_cat["x"],
                "y": masthead_cat["y"],
                "w": masthead_cat["w"],
                "h": masthead_cat["h"],
            } if masthead_cat else None,
            PINNED_FAMILY: {
                "x": pinned_cat["x"],
                "y": pinned_cat["y"],
                "w": pinned_cat["w"],
                "h": pinned_cat["h"],
            } if pinned_cat else None,
        },
        "categories": categories_out,
        "diagnostics": diagnostics,
    }


def run(format_name: str = "landscape") -> dict:
    """Main entry point: load data, solve layout, return layout JSON."""
    config = _load_config()

    # Load data
    taxonomy = load_json(TAXONOMY_PATH)
    index_data = taxonomy_index(taxonomy)
    members_raw = load_json(REGISTRY_PATH)

    # Build members list (simplified — just cat/subcat mapping)
    members = []
    for m in members_raw:
        category = m.get("category", "")
        if category not in index_data["category_slugs"]:
            continue
        family = index_data["category_family"][category]
        members.append({
            "name": m.get("display_name", "?"),
            "cat": family,
            "subcat": "" if category == family else category,
        })

    # Get family order from taxonomy
    families_order = [
        f["slug"] for f in taxonomy.get("families", [])
    ]

    # Determine target aspect ratio
    masters = config.get("responsive_layout", {}).get("masters", {})
    if format_name == "portrait":
        master = masters.get("portrait", {})
    else:
        master = masters.get("landscape", {})

    w_ratio = master.get("width_ratio", 16)
    h_ratio = master.get("height_ratio", 9)
    target = (w_ratio / h_ratio) * CELL_RATIO

    # Build categories
    cats = _build_cats(index_data, members, families_order)
    min_label_width = _compute_min_label_width(cats)

    # Insert masthead placeholder at position 0
    title_cat = {
        "slug": "__masthead__",
        "label_en": "",
        "label_fi": "",
        "groups_en": [],
        "groups_fi": [],
        "member_count": 0,
        "is_title": True,
        "mirror_of": PINNED_FAMILY,
    }
    cats = [title_cat] + cats

    # Solve
    max_iters = config.get("solver", {}).get("max_iterations", 30)
    ref_passes = config.get("solver", {}).get("refinement_passes", 5)
    plan = solve_layout(cats, target, min_label_width, max_iters, ref_passes)

    if not plan:
        raise RuntimeError(
            "Layout solver could not find a feasible solution. "
            "Try increasing max_iterations or adjusting constraints."
        )

    # Strip the masthead placeholder from cats for output
    cats_no_title = cats[1:]

    layout = build_layout_json(
        plan, [title_cat] + cats_no_title, families_order,
        config, format_name, index_data,
    )

    return layout


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FDCA Layout Solver")
    parser.add_argument(
        "--format", default="landscape",
        choices=["landscape", "portrait"],
        help="Output format (default: landscape)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: OUTPUT/layout-<format>.json)",
    )
    parser.add_argument(
        "--diagnostics", action="store_true",
        help="Print diagnostics to stdout",
    )
    args = parser.parse_args()

    layout = run(args.format)

    # Write output
    output_path = args.output
    if not output_path:
        suffix = f"-{args.format}" if args.format != "landscape" else ""
        output_path = OUTPUT_DIR / f"layout{suffix}.json"

    OUTPUT_DIR.mkdir(exist_ok=True)
    Path(output_path).write_text(
        json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {output_path}")

    if args.diagnostics:
        diag = layout["diagnostics"]
        print(f"\nDiagnostics ({args.format}):")
        print(f"  Canvas:     {diag['canvas_cells']['w']}×{diag['canvas_cells']['h']} cells"
              f" ({diag['canvas_px']['w']}×{diag['canvas_px']['h']} px)")
        print(f"  Occupied:   {diag['occupied_area_pct']}%")
        print(f"  Unused:     {diag['unused_area_pct']}%")
        print(f"  Companies:  {diag['company_count']}")
        print(f"  Dot cap:    {diag['total_dot_capacity']} (spare: {diag['spare_dot_capacity']})")
        print(f"  Max aspect: {diag['max_category_aspect_ratio']}")
        print(f"  Mean aspect:{diag['mean_category_aspect_ratio']}")
        print(f"  Categories: {len(layout['categories'])}")


if __name__ == "__main__":
    main()