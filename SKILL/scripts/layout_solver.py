#!/usr/bin/env python3
"""Deterministic, policy-aware layout solver for the FDCA ecosystem map.

Primary categories are rectangles. Families are either their rectangular
bounding boxes or the connected union of those rectangles (polyomino mode).
The renderer-independent JSON reports whitespace separately from dot capacity.
"""

from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from itertools import combinations, permutations
from pathlib import Path

import yaml

from catalogue_config import load_json, taxonomy_index

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "INPUT"
OUTPUT_DIR = ROOT / "OUTPUT"
CONFIG_PATH = Path(__file__).with_name("layout_config.yaml")
REGISTRY_PATH = INPUT_DIR / "fdca-member-registry.json"
TAXONOMY_PATH = INPUT_DIR / "fdca-categories.json"

CELL_W, CELL_H = 168, 190
GAP, TIN = 14, 7
PITCH_X = CELL_W + GAP + TIN * 2
PITCH_Y = CELL_H + GAP + TIN * 2
CELL_RATIO = PITCH_Y / PITCH_X
PINNED_FAMILY = "data_center_operators"
SUPPORTED_STRATEGIES = {"recursive_treemap", "heuristic", "cp_sat", "hybrid"}


class UnsupportedPolicyError(ValueError):
    """Raised rather than silently ignoring a selected policy."""


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _merge(base: dict, override: dict | None) -> dict:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _policy_value(config: dict, key: str, default: str) -> str:
    value = config.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value", value.get("mode", default)))
    return str(value or default)


def _validate_config(config: dict) -> None:
    category_mode = _policy_value(config, "category_shape_mode", "rectangular")
    if category_mode != "rectangular":
        raise UnsupportedPolicyError(
            "category_shape_mode=polyomino conflicts with the FDCA locked visual contract: "
            "primary categories are rectangles and Tetris geometry belongs to family unions"
        )
    strategy = config.get("solver", {}).get("strategy", "heuristic")
    if strategy not in SUPPORTED_STRATEGIES:
        raise UnsupportedPolicyError(
            f"solver.strategy={strategy} is not implemented; supported strategies are "
            f"{', '.join(sorted(SUPPORTED_STRATEGIES))}"
        )
    headroom = config.get("capacity_headroom", {}).get("mode", "none")
    if headroom not in {"none", "fixed_slots", "percentage", "adaptive"}:
        raise UnsupportedPolicyError(f"Unknown capacity_headroom.mode={headroom}")


def _headroom_slots(count: int, config: dict) -> int:
    policy = config.get("capacity_headroom", {})
    mode = policy.get("mode", "none")
    if mode == "none" or count <= 0:
        return 0
    if mode == "fixed_slots":
        return max(0, int(policy.get("slots", policy.get("minimum_slots", 1))))
    if mode == "adaptive":
        # The catalogue does not yet retain historical category counts.  Use a
        # deterministic size-adaptive proxy: more absolute room for large
        # categories, bounded by the same documented maximum fraction.  The
        # diagnostic payload names this basis explicitly.
        minimum = max(0, int(policy.get("minimum_slots", 1)))
        maximum_fraction = max(0.0, float(policy.get("maximum_fraction", 0.2)))
        requested = max(minimum, math.ceil(math.sqrt(count)))
        maximum = max(minimum, math.ceil(count * maximum_fraction))
        return min(requested, maximum)
    fraction = max(0.0, float(policy.get("fraction", 0.08)))
    minimum = max(0, int(policy.get("minimum_slots", 1)))
    maximum_fraction = max(fraction, float(policy.get("maximum_fraction", 0.2)))
    requested = max(minimum, math.ceil(count * fraction))
    maximum = max(minimum, math.ceil(count * maximum_fraction))
    return min(requested, maximum)


def _automatic_short_label(label: str) -> str:
    """Return a deterministic experimental abbreviation for long labels."""
    if len(label) <= 25:
        return label
    words = label.replace("/", " / ").split()
    if len(words) >= 4:
        initials = "".join(word[0].upper() for word in words if word != "/")
        if 2 <= len(initials) <= 8:
            return initials
    kept = []
    length = 0
    for word in words:
        if kept and length + 1 + len(word) > 22:
            break
        kept.append(word)
        length += len(word) + (1 if len(kept) > 1 else 0)
    return " ".join(kept).rstrip(".,;:-") + "…"


def _policy_label(category: dict, language: str, config: dict) -> str:
    full = category.get(language, category.get("en", category["slug"]))
    policy = config.get("short_labels", {})
    mode = policy.get("mode", "disabled")
    if mode == "approved_aliases":
        return category.get(f"short_{language}", full)
    if mode == "automatic" and policy.get("automatic_alias_generation_allowed", False):
        return _automatic_short_label(full)
    return full


def _build_families(indexes: dict, members: list[dict], config: dict) -> list[dict]:
    by_category: dict[str, list[dict]] = {}
    for member in members:
        by_category.setdefault(member["category"], []).append(member)

    empty_policy = _policy_value(config, "empty_category_policy", "show")
    order_policy = config.get("category_order", {}).get("mode", "canonical_stable")
    families: list[dict] = []
    for family_index, family in enumerate(indexes["taxonomy"].get("families", [])):
        groups = []
        for category_index, category in enumerate(family.get("categories", [])):
            items = by_category.get(category["slug"], [])
            if not items and empty_policy == "hide":
                continue
            groups.append({
                "slug": category["slug"],
                "label_en": _policy_label(category, "en", config),
                "label_fi": _policy_label(category, "fi", config),
                "full_label_en": category.get("en", category["slug"]),
                "full_label_fi": category.get("fi", category.get("en", category["slug"])),
                "description_en": category.get("description_en", ""),
                "description_fi": category.get("description_fi", ""),
                "items": items,
                "count": len(items),
                "taxonomy_index": category_index,
                "visible": bool(items) or empty_policy == "show",
                "reserved": not items and empty_policy == "reserve",
            })
        if order_policy == "count_descending":
            groups.sort(key=lambda group: (-group["count"], group["taxonomy_index"]))
        elif order_policy == "solver_free":
            groups.sort(key=lambda group: (-group["count"], -len(group["label_fi"]), group["slug"]))
        elif order_policy == "canonical_stable":
            # Start in taxonomy order, then allow only adjacent, material
            # large-before-small swaps.  This keeps the mental map stable
            # while avoiding the most expensive shelf-packing inversions.
            for index in range(1, len(groups)):
                current = index
                while (current > 0 and groups[current]["count"] >
                       max(2, groups[current - 1]["count"] * 2)):
                    groups[current - 1], groups[current] = groups[current], groups[current - 1]
                    current -= 1
        families.append({
            "slug": family["slug"],
            "label_en": family.get("en", family["slug"]),
            "label_fi": family.get("fi", family.get("en", family["slug"])),
            "description_en": family.get("description_en", ""),
            "description_fi": family.get("description_fi", ""),
            "groups": groups,
            "member_count": sum(group["count"] for group in groups),
            "taxonomy_index": family_index,
        })
    families.sort(key=lambda family: (
        0 if family["slug"] == PINNED_FAMILY else 1,
        -family["member_count"], family["taxonomy_index"],
    ))
    return families


def _geometry_labels(group: dict, config: dict) -> list[str]:
    policy = config.get("language_geometry", {})
    mode = policy.get("mode", "maximum_across_languages")
    if mode == "active_language":
        language = policy.get("active_language", "en")
        return [group.get(f"label_{language}", group["label_en"])]
    if mode == "reference_language":
        language = policy.get("reference_language", "en")
        return [group.get(f"label_{language}", group["label_en"])]
    return [
        group.get(f"label_{language}", group["label_en"])
        for language in policy.get("languages", ["en", "fi"])
    ]


def _category_font_size(group: dict, config: dict) -> float:
    policy = config.get("category_font", {})
    base = float(policy.get("size_px", 14))
    minimum = float(policy.get("minimum_size_px", max(10, base - 3)))
    maximum = float(policy.get("maximum_size_px", base + 1))
    mode = policy.get("mode", "fixed")
    if mode == "global_adaptive":
        return max(minimum, min(maximum, base * 0.9))
    if mode == "per_category_adaptive":
        longest = max((len(label) for label in _geometry_labels(group, config)), default=0)
        reduction = max(0.0, (longest - 22) * 0.12)
        return max(minimum, min(maximum, base - reduction))
    return base


def _minimum_label_width(group: dict, config: dict) -> int:
    if not group["visible"]:
        return 2
    font = _category_font_size(group, config)
    max_lines = max(1, int(config.get("category_title_max_lines", {}).get("value", 2)))
    required_px = 0.0
    for label in _geometry_labels(group, config):
        words = label.split()
        longest_word = max((len(word) for word in words), default=1)
        line_chars = max(longest_word, math.ceil(len(label) / max_lines))
        required_px = max(required_px, line_chars * 0.58 * font + 26)
    return max(2, math.ceil(required_px / PITCH_X))


def _shape_candidates(group: dict, config: dict, target_aspect: float) -> list[dict]:
    count = group["count"]
    headroom = _headroom_slots(count, config)
    required = count + headroom
    label_rows = 1 if group["visible"] else 0
    min_width = _minimum_label_width(group, config)
    if group["reserved"]:
        return [{"w": min_width, "h": 1, "label_rows": 0, "dot_rows": 0,
                 "capacity": 0, "headroom": 0, "area": min_width,
                 "font_size_px": _category_font_size(group, config)}]
    if required == 0:
        height = max(1, label_rows)
        return [{"w": min_width, "h": height, "label_rows": label_rows, "dot_rows": 0,
                 "capacity": 0, "headroom": 0, "area": min_width * height,
                 "font_size_px": _category_font_size(group, config)}]

    ideal = math.sqrt(required * max(0.25, target_aspect))
    max_width = max(min_width, min(required, math.ceil(ideal * 2.2) + 2))
    candidates = []
    for width in range(min_width, max_width + 1):
        rows = math.ceil(required / width)
        height = label_rows + rows
        pixel_aspect = width * PITCH_X / max(1, height * PITCH_Y)
        candidates.append({
            "w": width, "h": height, "label_rows": label_rows, "dot_rows": rows,
            "capacity": width * rows, "headroom": headroom, "area": width * height,
            "aspect_penalty": abs(math.log(max(0.05, pixel_aspect))),
            "font_size_px": _category_font_size(group, config),
        })
    maximum_aspect = 7.0 if group["slug"] == PINNED_FAMILY else 3.5
    readable = [shape for shape in candidates
                if 0.28 <= width_aspect(shape) <= maximum_aspect]
    if readable:
        candidates = readable
    candidates.sort(key=lambda shape: (
        shape["area"], shape["aspect_penalty"], shape["capacity"] - required, shape["w"],
    ))
    selected = candidates[:9]
    widest = max(candidates, key=lambda shape: shape["w"])
    if widest not in selected:
        selected.append(widest)
    return selected


def width_aspect(shape: dict) -> float:
    """Rendered rectangle aspect ratio, accounting for non-square grid cells."""
    return shape["w"] * PITCH_X / max(1, shape["h"] * PITCH_Y)


def _cells_for_rect(x: int, y: int, width: int, height: int) -> set[tuple[int, int]]:
    return {(cx, cy) for cx in range(x, x + width) for cy in range(y, y + height)}


def _components(cells: set[tuple[int, int]]) -> int:
    remaining = set(cells)
    result = 0
    while remaining:
        result += 1
        stack = [remaining.pop()]
        while stack:
            x, y = stack.pop()
            for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
    return result


def _empty_shape_regions(cells: set[tuple[int, int]], width: int,
                         height: int) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Return enclosed holes and cells in substantial empty bands."""
    empty = {(x, y) for x in range(width) for y in range(height)} - cells
    outside = set()
    stack = [cell for cell in empty if cell[0] in (0, width - 1) or cell[1] in (0, height - 1)]
    outside.update(stack)
    while stack:
        x, y = stack.pop()
        for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbour in empty and neighbour not in outside:
                outside.add(neighbour)
                stack.append(neighbour)
    band_cells = set()
    horizontal_threshold = max(2, math.ceil(width * 0.4))
    vertical_threshold = max(2, math.ceil(height * 0.4))
    for y in range(height):
        run = []
        for x in range(width + 1):
            if x < width and (x, y) not in cells:
                run.append((x, y))
            else:
                if len(run) >= horizontal_threshold:
                    band_cells.update(run)
                run = []
    for x in range(width):
        run = []
        for y in range(height + 1):
            if y < height and (x, y) not in cells:
                run.append((x, y))
            else:
                if len(run) >= vertical_threshold:
                    band_cells.update(run)
                run = []
    return empty - outside, band_cells - cells


def _shape_metrics(cells: set[tuple[int, int]], width: int, height: int) -> dict:
    if not cells:
        return {"components": 0, "holes": 0, "tendrils": 0, "perimeter": 0, "empty_bands": 0}
    perimeter = 0
    tendrils = 0
    for x, y in cells:
        neighbours = sum((nx, ny) in cells for nx, ny in (
            (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)
        ))
        perimeter += 4 - neighbours
        if neighbours <= 1:
            tendrils += 1
    holes, band_cells = _empty_shape_regions(cells, width, height)
    return {
        "components": _components(cells), "holes": len(holes),
        "tendrils": tendrils, "perimeter": perimeter, "empty_bands": len(band_cells),
    }


def _family_candidate(family: dict, candidate_lists: list[list[dict]], width: int) -> dict | None:
    if not family["groups"]:
        return None
    placements = []
    x = y = row_height = used_width = 0
    for group_index, shapes in enumerate(candidate_lists):
        options = []
        for shape in shapes:
            if shape["w"] > width:
                continue
            if x == 0 or x + shape["w"] <= width:
                resulting_row_height = max(row_height, shape["h"])
                total_height = y + resulting_row_height
                options.append((
                    total_height,
                    total_height * width - sum(p["area"] for p in placements) - shape["area"],
                    0,
                    shape,
                ))
            if x > 0:
                total_height = y + row_height + shape["h"]
                options.append((
                    total_height,
                    total_height * width - sum(p["area"] for p in placements) - shape["area"],
                    1,
                    shape,
                ))
        if not options:
            return None
        _, _, new_row, shape = min(options, key=lambda option: (option[0], option[1], option[3]["area"]))
        if new_row:
            y += row_height
            x = 0
            row_height = 0
        placements.append({"group_index": group_index, "x": x, "y": y, **shape})
        x += shape["w"]
        used_width = max(used_width, x)
        row_height = max(row_height, shape["h"])
    height = y + row_height
    cells = set()
    for placement in placements:
        cells |= _cells_for_rect(placement["x"], placement["y"], placement["w"], placement["h"])
    metrics = _shape_metrics(cells, used_width, height)
    return {
        "w": used_width, "h": height, "placements": placements, "cells": cells,
        "area": len(cells), "bbox_area": used_width * height,
        "slack": used_width * height - len(cells),
        **metrics,
    }


def _family_candidates(family: dict, config: dict, target_aspect: float, limit: int) -> list[dict]:
    candidate_lists = [_shape_candidates(group, config, target_aspect) for group in family["groups"]]
    minimum_width = max(min(shape["w"] for shape in choices) for choices in candidate_lists)
    minimum_area = sum(min(shape["area"] for shape in choices) for choices in candidate_lists)
    maximum_width = max(
        minimum_width,
        math.ceil(math.sqrt(minimum_area * max(0.4, target_aspect))) + 12,
    )
    candidates = []
    signatures = set()
    for width in range(minimum_width, maximum_width + 1):
        candidate = _family_candidate(family, candidate_lists, width)
        if not candidate:
            continue
        signature = tuple((p["group_index"], p["x"], p["y"], p["w"], p["h"])
                          for p in candidate["placements"])
        if signature in signatures:
            continue
        signatures.add(signature)
        candidate["family"] = family
        candidates.append(candidate)
    valid = [candidate for candidate in candidates
             if candidate["components"] == 1 and candidate["holes"] == 0]
    pool = valid or candidates
    for candidate in pool:
        candidate["selection_score"] = (
            candidate["bbox_area"]
            + candidate["slack"] * 1.5
            + candidate["perimeter"] * 0.08
            + abs(math.log(max(0.05, candidate["w"] / max(1, candidate["h"])))) * 120
        )
    pool.sort(key=lambda candidate: (
        candidate["tendrils"] > 0, candidate["selection_score"], candidate["w"]
    ))
    selected = pool[:max(1, limit - 2)]
    if pool:
        selected.extend([min(pool, key=lambda candidate: candidate["w"]),
                         max(pool, key=lambda candidate: candidate["w"])])
    unique = []
    seen = set()
    for candidate in selected:
        signature = (candidate["w"], candidate["h"], candidate["slack"])
        if signature not in seen:
            seen.add(signature)
            unique.append(candidate)
    return unique[:limit]


def _tile_integer(items: list[dict], x0: int, y0: int, width: int,
                  height: int) -> list[dict]:
    """Port of the compact integer treemap previously embedded in the UI."""
    output: list[dict] = []

    def recurse(pool: list[dict], x: int, y: int, w: int, h: int) -> None:
        if not pool or w < 1 or h < 1:
            return
        if len(pool) == 1:
            output.append({"item": pool[0], "x": x, "y": y, "w": w, "h": h})
            return
        total = sum(item["cells"] for item in pool)
        accumulated = 0
        split = 0
        for index, item in enumerate(pool[:-1]):
            accumulated += item["cells"]
            split = index
            if accumulated >= total / 2:
                break
        first, second = pool[:split + 1], pool[split + 1:]
        first_sum = sum(item["cells"] for item in first)
        second_sum = total - first_sum
        if w >= h:
            first_width = max(1, min(w - 1, round(w * first_sum / max(1, total))))
            while first_width < w - 1 and first_width * h < first_sum:
                first_width += 1
            while first_width > 1 and (w - first_width) * h < second_sum:
                first_width -= 1
            recurse(first, x, y, first_width, h)
            recurse(second, x + first_width, y, w - first_width, h)
        else:
            first_height = max(1, min(h - 1, round(h * first_sum / max(1, total))))
            while first_height < h - 1 and w * first_height < first_sum:
                first_height += 1
            while first_height > 1 and w * (h - first_height) < second_sum:
                first_height -= 1
            recurse(first, x, y, w, first_height)
            recurse(second, x, y + first_height, w, h - first_height)

    recurse(items[:], x0, y0, width, height)
    return output


def _compact_family_placements(placements: list[dict], family: dict,
                               config: dict, width: int,
                               height: int) -> list[dict]:
    """Remove/reinsert category rectangles to close avoidable lower gaps.

    The recursive treemap supplies a feasible first layout, but trimming each
    category to its real dot rows can leave small boxes stranded along the
    bottom edge.  This deterministic local search keeps every category
    rectangular while moving it through all feasible positions in the family
    leaf.  Connectivity, holes and full empty bands are part of the score, so
    the result is also a useful category-first polyomino candidate.
    """
    result = [dict(placement) for placement in placements]

    def occupied(items: list[dict]) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for item in items:
            cells |= _cells_for_rect(item["x"], item["y"], item["w"], item["h"])
        return cells

    def score(items: list[dict]) -> tuple:
        cells = occupied(items)
        used_height = max((item["y"] + item["h"] for item in items), default=0)
        metrics = _shape_metrics(cells, width, max(1, used_height))
        return (
            metrics["components"] > 1,
            metrics["holes"],
            used_height,
            metrics["empty_bands"],
            width * used_height - len(cells),
            metrics["perimeter"],
            sum(item["y"] for item in items),
            sum(item["x"] for item in items),
        )

    for _ in range(max(2, len(result) * 2)):
        changed = False
        order = sorted(range(len(result)), key=lambda index: (
            -(result[index]["y"] + result[index]["h"]),
            -result[index]["y"], result[index]["x"],
        ))
        for index in order:
            current = result[index]
            other_cells = occupied(result[:index] + result[index + 1:])
            best = dict(current)
            best_score = score(result)
            group = family["groups"][current["group_index"]]
            shapes = _shape_candidates(group, config, width / max(1, height))
            current_shape = {key: current[key] for key in (
                "w", "h", "label_rows", "dot_rows", "capacity", "headroom",
                "area", "font_size_px",
            )}
            if not any((shape["w"], shape["h"]) ==
                       (current["w"], current["h"]) for shape in shapes):
                shapes.append(current_shape)
            for shape in shapes:
                if shape["w"] > width or shape["h"] > height:
                    continue
                for y in range(0, height - shape["h"] + 1):
                    for x in range(0, width - shape["w"] + 1):
                        candidate_cells = _cells_for_rect(x, y, shape["w"], shape["h"])
                        if candidate_cells & other_cells:
                            continue
                        if other_cells and not any(
                            (nx, ny) in other_cells
                            for cx, cy in candidate_cells
                            for nx, ny in ((cx - 1, cy), (cx + 1, cy),
                                           (cx, cy - 1), (cx, cy + 1))
                        ):
                            continue
                        trial = [dict(item) for item in result]
                        trial[index] = {
                            "group_index": current["group_index"], "x": x, "y": y,
                            **shape,
                        }
                        trial_score = score(trial)
                        if trial_score < best_score:
                            best, best_score = trial[index], trial_score
            if any(best.get(key) != current.get(key) for key in ("x", "y", "w", "h")):
                result[index] = best
                changed = True
        if not changed:
            break
    return result


def _search_family_shape(family: dict, config: dict, width: int,
                         height: int, beam_width: int = 24) -> dict | None:
    """Pack rectangular subcategories into a connected family polyomino.

    This is a category-first bottom-left beam search: it chooses among valid
    dot-grid shapes for every category and keeps a connected orthogonal union
    throughout.  Unlike the former shelf generator, later boxes can occupy
    notches beside and above earlier boxes.
    """
    if not family["groups"]:
        return None
    shape_sets: dict[int, list[dict]] = {}
    for index, group in enumerate(family["groups"]):
        shapes = _shape_candidates(group, config, width / max(1, height))
        unique = []
        seen = set()
        for shape in shapes:
            signature = (shape["w"], shape["h"])
            if signature in seen or shape["w"] > width or shape["h"] > height:
                continue
            seen.add(signature)
            unique.append(shape)
        shape_sets[index] = unique[:4]
        if not shape_sets[index]:
            return None

    sequence = sorted(range(len(family["groups"])), key=lambda index: (
        -min(shape["area"] for shape in shape_sets[index]),
        -family["groups"][index]["count"], index,
    ))
    states = [{"occupied": set(), "placements": [], "height": 0,
               "spare": 0, "perimeter": 0}]
    for sequence_index, group_index in enumerate(sequence):
        group = family["groups"][group_index]
        next_states = []
        signatures = set()
        for state in states:
            for shape in shape_sets[group_index]:
                x_values = [0] if sequence_index == 0 else range(0, width - shape["w"] + 1)
                for x in x_values:
                    feasible_y = None
                    for y in range(0, height - shape["h"] + 1):
                        cells = _cells_for_rect(x, y, shape["w"], shape["h"])
                        if cells & state["occupied"]:
                            continue
                        if state["occupied"] and not any(
                            neighbour in state["occupied"]
                            for cx, cy in cells
                            for neighbour in ((cx - 1, cy), (cx + 1, cy),
                                              (cx, cy - 1), (cx, cy + 1))
                        ):
                            continue
                        feasible_y = y
                        break
                    if feasible_y is None:
                        continue
                    cells = _cells_for_rect(x, feasible_y, shape["w"], shape["h"])
                    new_occupied = state["occupied"] | cells
                    new_height = max(state["height"], feasible_y + shape["h"])
                    placement = {
                        "group_index": group_index, "x": x, "y": feasible_y, **shape,
                    }
                    spare = state["spare"] + max(
                        0, shape["capacity"] - group["count"] - shape["headroom"]
                    )
                    signature = tuple(sorted(new_occupied))
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    next_states.append({
                        "occupied": new_occupied,
                        "placements": state["placements"] + [placement],
                        "height": new_height,
                        "spare": spare,
                        "partial_score": (
                            new_height,
                            width * new_height - len(new_occupied) + spare,
                            spare,
                            sum(item["y"] for item in state["placements"]) + feasible_y,
                            sum(item["x"] for item in state["placements"]) + x,
                        ),
                    })
        if not next_states:
            return None
        next_states.sort(key=lambda state: state["partial_score"])
        states = next_states[:beam_width]

    candidates = []
    for state in states:
        used_height = state["height"]
        metrics = _shape_metrics(state["occupied"], width, used_height)
        if metrics["components"] != 1 or metrics["holes"]:
            continue
        candidates.append({
            "w": width, "h": used_height,
            "placements": sorted(state["placements"], key=lambda item: item["group_index"]),
            "cells": state["occupied"], "area": len(state["occupied"]),
            "bbox_area": width * used_height,
            "slack": width * used_height - len(state["occupied"]),
            "spare": state["spare"], **metrics,
        })
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (
        candidate["h"], candidate["slack"] + candidate["spare"],
        candidate["empty_bands"], candidate["perimeter"], candidate["spare"],
    ))


def _legacy_family_shape_uncached(family: dict, width: int, height: int,
                                  config: dict) -> dict | None:
    if not family["groups"] or width < 1 or height < 1:
        return None
    requirements = [group["count"] + _headroom_slots(group["count"], config)
                    for group in family["groups"]]
    demands = [required + (2 if group["visible"] else 0)
               for group, required in zip(family["groups"], requirements)]
    good = None
    for _ in range(18):
        leaves = _tile_integer([
            {"group_index": index, "cells": max(1, demand)}
            for index, demand in enumerate(demands)
        ], 0, 0, width, height)
        if len(leaves) != len(family["groups"]):
            return None
        ok = True
        for leaf in leaves:
            index = leaf["item"]["group_index"]
            group = family["groups"][index]
            label_rows = 1 if group["visible"] else 0
            capacity = leaf["w"] * max(0, leaf["h"] - label_rows)
            if requirements[index] > capacity:
                ok = False
                demands[index] = requirements[index] + (label_rows + 1) * leaf["w"]
            elif group["visible"] and leaf["w"] < _minimum_label_width(group, config):
                ok = False
                minimum = _minimum_label_width(group, config)
                demands[index] = minimum * (1 + math.ceil(requirements[index] / minimum))
        if ok:
            good = leaves
            next_demands = demands[:]
            for leaf in leaves:
                index = leaf["item"]["group_index"]
                group = family["groups"][index]
                label_rows = 1 if group["visible"] else 0
                dot_rows = math.ceil(requirements[index] / max(1, leaf["w"]))
                if group["visible"] and not requirements[index]:
                    dot_rows = 0
                next_demands[index] = leaf["w"] * (label_rows + dot_rows)
            if next_demands == demands:
                break
            demands = next_demands
    if not good:
        return None

    placements = []
    occupied = set()
    for leaf in good:
        index = leaf["item"]["group_index"]
        group = family["groups"][index]
        label_rows = 1 if group["visible"] else 0
        dot_rows = math.ceil(requirements[index] / max(1, leaf["w"]))
        if group["visible"] and not requirements[index]:
            dot_rows = 0
        actual_height = max(1, label_rows + dot_rows)
        placement = {
            "group_index": index, "x": leaf["x"], "y": leaf["y"],
            "w": leaf["w"], "h": actual_height, "label_rows": label_rows,
            "dot_rows": dot_rows, "capacity": leaf["w"] * dot_rows,
            "headroom": requirements[index] - group["count"],
            "area": leaf["w"] * actual_height,
            "font_size_px": _category_font_size(group, config),
        }
        placements.append(placement)
        occupied |= _cells_for_rect(leaf["x"], leaf["y"], leaf["w"], actual_height)
    placements = _compact_family_placements(placements, family, config, width, height)
    occupied = set()
    for placement in placements:
        occupied |= _cells_for_rect(
            placement["x"], placement["y"], placement["w"], placement["h"]
        )
    used_height = max((placement["y"] + placement["h"] for placement in placements), default=1)
    metrics = _shape_metrics(occupied, width, used_height)
    compact = {
        "w": width, "h": used_height, "placements": placements, "cells": occupied,
        "area": len(occupied), "bbox_area": width * used_height,
        "slack": width * used_height - len(occupied), **metrics,
    }
    compact["spare"] = sum(
        max(0, placement["capacity"] - family["groups"][placement["group_index"]]["count"]
            - placement["headroom"])
        for placement in placements
    )
    searched = _search_family_shape(family, config, width, height)
    if not searched:
        return compact
    quality = lambda candidate: (
        candidate["components"] > 1, candidate["holes"], candidate["h"],
        candidate["slack"] + candidate.get("spare", 0),
        candidate["empty_bands"], candidate["perimeter"],
    )
    return min((compact, searched), key=quality)


_LEGACY_SHAPE_CACHE: dict[tuple, dict | None] = {}


def _legacy_family_shape(family: dict, width: int, height: int,
                         config: dict) -> dict | None:
    policy_signature = json.dumps({
        "capacity_headroom": config.get("capacity_headroom", {}),
        "language_geometry": config.get("language_geometry", {}),
        "category_font": config.get("category_font", {}),
        "category_title_max_lines": config.get("category_title_max_lines", {}),
        "short_labels": config.get("short_labels", {}),
    }, sort_keys=True, separators=(",", ":"))
    group_signature = tuple(
        (group["slug"], group["count"], group["visible"], group["reserved"],
         group["label_en"], group["label_fi"])
        for group in family["groups"]
    )
    key = (family["slug"], width, height, group_signature, policy_signature)
    if key not in _LEGACY_SHAPE_CACHE:
        _LEGACY_SHAPE_CACHE[key] = _legacy_family_shape_uncached(
            family, width, height, config
        )
        if len(_LEGACY_SHAPE_CACHE) > 512:
            _LEGACY_SHAPE_CACHE.pop(next(iter(_LEGACY_SHAPE_CACHE)))
    return deepcopy(_LEGACY_SHAPE_CACHE[key])


_TILED_SHAPE_CACHE: dict[tuple, dict | None] = {}


def _tiled_family_shape_uncached(family: dict, width: int, height: int,
                                 config: dict) -> dict | None:
    """Tile a rectangular family allocation completely with category boxes.

    The former compacting pass shortened category boxes after the integer
    treemap had already produced an exact cover.  That reintroduced the grey
    bands and holes the treemap was meant to eliminate.  Here each leaf keeps
    its allocated rectangle; dot capacity remains based only on the rows the
    category actually needs, so visual growth space is not confused with dot
    slots.
    """
    if not family["groups"] or width < 1 or height < 1:
        return None
    requirements = [group["count"] + _headroom_slots(group["count"], config)
                    for group in family["groups"]]
    demands = [required + (2 if group["visible"] else 0)
               for group, required in zip(family["groups"], requirements)]
    leaves = None
    for _ in range(24):
        trial = _tile_integer([
            {"group_index": index, "cells": max(1, demand)}
            for index, demand in enumerate(demands)
        ], 0, 0, width, height)
        if len(trial) != len(family["groups"]):
            return None
        valid = True
        next_demands = demands[:]
        for leaf in trial:
            index = leaf["item"]["group_index"]
            group = family["groups"][index]
            label_rows = 1 if group["visible"] else 0
            if group["visible"] and leaf["w"] < _minimum_label_width(group, config):
                valid = False
                minimum = _minimum_label_width(group, config)
                next_demands[index] = minimum * (
                    label_rows + max(1, math.ceil(requirements[index] / minimum))
                )
                continue
            available = leaf["w"] * max(0, leaf["h"] - label_rows)
            if requirements[index] > available:
                valid = False
                next_demands[index] = requirements[index] + (label_rows + 1) * leaf["w"]
        if valid:
            leaves = trial
            break
        demands = next_demands
    if leaves is None:
        return None

    placements = []
    category_padding = 0
    spare = 0
    for leaf in leaves:
        index = leaf["item"]["group_index"]
        group = family["groups"][index]
        label_rows = 1 if group["visible"] else 0
        dot_rows = math.ceil(requirements[index] / max(1, leaf["w"]))
        if group["visible"] and not requirements[index]:
            dot_rows = 0
        content_height = max(1, label_rows + dot_rows)
        if content_height > leaf["h"]:
            return None
        unused = leaf["w"] * (leaf["h"] - content_height)
        category_padding += unused
        capacity = leaf["w"] * dot_rows
        spare += max(0, capacity - group["count"] -
                     (requirements[index] - group["count"]))
        placements.append({
            "group_index": index, "x": leaf["x"], "y": leaf["y"],
            "w": leaf["w"], "h": leaf["h"], "label_rows": label_rows,
            "dot_rows": dot_rows, "content_h": content_height,
            "category_padding": unused, "capacity": capacity,
            "headroom": requirements[index] - group["count"],
            "area": leaf["w"] * leaf["h"],
            "font_size_px": _category_font_size(group, config),
        })
    occupied = _cells_for_rect(0, 0, width, height)
    metrics = _shape_metrics(occupied, width, height)
    return {
        "w": width, "h": height, "placements": placements,
        "cells": occupied, "area": width * height,
        "bbox_area": width * height, "slack": 0,
        "category_padding": category_padding, "spare": spare, **metrics,
    }


def _tiled_family_shape(family: dict, width: int, height: int,
                        config: dict) -> dict | None:
    policy_signature = json.dumps({
        "capacity_headroom": config.get("capacity_headroom", {}),
        "language_geometry": config.get("language_geometry", {}),
        "category_font": config.get("category_font", {}),
        "category_title_max_lines": config.get("category_title_max_lines", {}),
        "short_labels": config.get("short_labels", {}),
    }, sort_keys=True, separators=(",", ":"))
    group_signature = tuple(
        (group["slug"], group["count"], group["visible"], group["reserved"],
         group["label_en"], group["label_fi"])
        for group in family["groups"]
    )
    key = (family["slug"], width, height, group_signature, policy_signature)
    if key not in _TILED_SHAPE_CACHE:
        _TILED_SHAPE_CACHE[key] = _tiled_family_shape_uncached(
            family, width, height, config
        )
        if len(_TILED_SHAPE_CACHE) > 1024:
            _TILED_SHAPE_CACHE.pop(next(iter(_TILED_SHAPE_CACHE)))
    return deepcopy(_TILED_SHAPE_CACHE[key])


def _solve_legacy(families: list[dict], target_aspect: float,
                  config: dict, mode: str) -> dict:
    """Exact-cover integer treemap with the two fixed top-left anchors.

    Every accepted candidate tiles the complete outer rectangle: masthead and
    family allocations are disjoint and their union equals W x H.  This is a
    stronger invariant than merely reporting zero holes inside each family.
    """
    pinned = next(family for family in families if family["slug"] == PINNED_FAMILY)

    def demand_of(family: dict) -> int:
        required = sum(group["count"] + _headroom_slots(group["count"], config)
                       for group in family["groups"])
        header_rows = sum(group["visible"] for group in family["groups"])
        value = required + header_rows
        area = value + max(2, math.ceil(math.sqrt(max(1, value) * target_aspect)))
        visible = [group for group in family["groups"] if group["visible"]]
        minimum = max((_minimum_label_width(group, config) for group in visible), default=1)
        return max(area, minimum * 2)

    family_demands = {family["slug"]: demand_of(family) for family in families}
    total_demand = sum(family_demands.values()) + demand_of(pinned)
    ideal_width = max(10, round(math.sqrt(total_demand * target_aspect)))
    landscape = target_aspect >= 1
    width_pool = (list(range(max(24, ideal_width - 4), ideal_width + 19))
                  if landscape else
                  list(range(max(12, ideal_width - 2), ideal_width + 11)))
    maximum_iterations = max(16, int(config.get("solver", {}).get("max_iterations", 30)))
    if len(width_pool) > maximum_iterations:
        width_pool = sorted({
            width_pool[round(index * (len(width_pool) - 1) /
                             max(1, maximum_iterations - 1))]
            for index in range(maximum_iterations)
        })
    other_families = [family for family in families if family is not pinned]
    top_extra_sets = ([tuple()] if not landscape else [
        selection
        for size in range(0, min(2, len(other_families)) + 1)
        for selection in combinations(other_families, size)
    ])
    aspect_limit = 0.18 if landscape else 0.36
    geometry_specs = []
    for width in width_pool:
        ideal_height = max(12, round(width / target_aspect))
        lower_height_delta = 6 if landscape else 16
        for height in range(max(12, ideal_height - lower_height_delta), ideal_height + 9):
            if height < 9:
                continue
            min_title_fraction, max_title_fraction = ((0.36, 0.55) if landscape
                                                       else (0.55, 0.68))
            title_low = max(6, math.ceil(width * min_title_fraction))
            title_high = min(width - 3, math.floor(width * max_title_fraction))
            for title_width in range(title_low, title_high + 1):
                title_content_height = max(
                    4, math.ceil(title_width * PITCH_X / (2.8 * PITCH_Y))
                )
                for top_height in range(title_content_height,
                                        min(10, height - 4) + 1):
                    for extras in top_extra_sets:
                        top_demand = sum(family_demands[family["slug"]]
                                         for family in (pinned, *extras))
                        bottom_demand = sum(
                            family_demands[family["slug"]]
                            for family in other_families if family not in extras
                        )
                        if (top_demand > (width - title_width) * top_height or
                                bottom_demand > width * (height - top_height)):
                            continue
                        aspect_error = abs(math.log(
                            max(0.05, (width / height) / target_aspect)
                        ))
                        preferred_title_fraction = 0.42 if landscape else 0.62
                        title_error = abs(title_width / width - preferred_title_fraction)
                        geometry_specs.append((
                            (aspect_error > aspect_limit, width * height,
                             round(aspect_error, 4), top_height,
                             round(title_error, 4), len(extras)),
                            width, height, title_width, top_height, extras,
                        ))

    candidates = []
    for geometry_quality, width, height, title_width, top_height, extras in sorted(
            geometry_specs, key=lambda item: item[0]):
        top_families = [pinned, *extras]
        bottom_families = [family for family in other_families
                           if family not in extras]
        top_items = [{"family": family,
                      "cells": family_demands[family["slug"]]}
                     for family in top_families]
        bottom_items = [{"family": family,
                         "cells": family_demands[family["slug"]]}
                        for family in bottom_families]
        top_leaves = _tile_integer(
            top_items, title_width, 0, width - title_width, top_height
        )
        bottom_leaves = _tile_integer(
            bottom_items, 0, top_height, width, height - top_height
        )
        if (len(top_leaves) != len(top_items) or
                len(bottom_leaves) != len(bottom_items)):
            continue
        placements = []
        feasible = True
        for leaf in [*top_leaves, *bottom_leaves]:
            family = leaf["item"]["family"]
            shape = _tiled_family_shape(
                family, leaf["w"], leaf["h"], config
            )
            if not shape:
                feasible = False
                break
            region = _cells_for_rect(
                leaf["x"], leaf["y"], leaf["w"], leaf["h"]
            )
            placements.append({
                "family": family, "shape": shape,
                "x": leaf["x"], "y": leaf["y"],
                "region_cells": region,
            })
        if not feasible or len(placements) != len(families):
            continue
        title = {"x": 0, "y": 0, "w": title_width, "h": top_height}
        occupied = _cells_for_rect(0, 0, title_width, top_height)
        for item in placements:
            if occupied & item["region_cells"]:
                feasible = False
                break
            occupied |= item["region_cells"]
        if not feasible or len(occupied) != width * height:
            continue
        pinned_item = next(
            item for item in placements
            if item["family"]["slug"] == PINNED_FAMILY
        )
        others = [item for item in placements if item is not pinned_item]
        category_padding = sum(
            item["shape"].get("category_padding", 0)
            for item in placements
        )
        plan = {
            "W": width, "H": height, "title": title,
            "pinned": pinned_item, "families": others,
            "occupied": occupied,
            "quality": (*geometry_quality[:4], category_padding,
                        *geometry_quality[4:], width),
            "outer_exact_cover": True,
        }
        plan["movement_cost"] = _movement_cost(plan, config)
        candidates.append(plan)
        # A small frontier retains a padding-space choice without evaluating
        # thousands of lower-ranked exact-cover geometries in the workbench.
        if len(candidates) >= 8:
            break
    if not candidates:
        raise RuntimeError(f"No feasible hole-free {mode} exact-cover layout was found")
    candidates.sort(key=lambda plan: (plan["quality"], plan["movement_cost"]))
    return candidates[0]


def _translated(cells: set[tuple[int, int]], dx: int, dy: int) -> set[tuple[int, int]]:
    return {(x + dx, y + dy) for x, y in cells}


def _placement_options(shape: dict, occupied: set[tuple[int, int]], canvas_width: int,
                       min_y: int, max_y: int, mode: str, limit: int) -> list[dict]:
    local_cells = (_cells_for_rect(0, 0, shape["w"], shape["h"])
                   if mode == "rectangular" else shape["cells"])
    local_cells_list = tuple(local_cells)
    occupied_height = max((cy + 1 for _, cy in occupied), default=0)
    options = []
    # Only the lowest feasible y for each x can be part of a bottom-left
    # optimum; testing every higher translation multiplied solve time without
    # ever improving height or whitespace.
    for x in range(0, canvas_width - shape["w"] + 1):
        for y in range(min_y, max_y + 2):
            if any((cx + x, cy + y) in occupied for cx, cy in local_cells_list):
                continue
            cells = {(cx + x, cy + y) for cx, cy in local_cells_list}
            new_height = max(occupied_height, y + shape["h"])
            options.append({"x": x, "y": y, "cells": cells, "height": new_height})
            break
    options.sort(key=lambda option: (option["height"], option["y"], option["x"]))
    return options[:limit]


def _pack_remaining(families: list[dict], candidates_by_slug: dict[str, list[dict]],
                    occupied: set[tuple[int, int]], width: int, anchor_height: int,
                    mode: str, strategy: str, refinement_passes: int) -> list[dict] | None:
    if strategy == "recursive_treemap":
        orders = [tuple(families)]
        beam_width, candidate_limit, placement_limit = 1, 2, 1
    elif strategy == "heuristic":
        base = tuple(families)
        orders = [base, tuple(reversed(base))]
        beam_width = max(5, min(7, 4 + refinement_passes))
        candidate_limit, placement_limit = 3, 2
    elif strategy == "cp_sat":
        # Dependency-free deterministic constraint search.  With four
        # non-pinned families the complete order space is only 24; a wider
        # beam then explores substantially more shape/position assignments.
        orders = list(permutations(families))[:3]
        beam_width = max(5, min(7, 4 + refinement_passes))
        candidate_limit, placement_limit = 4, 2
    else:  # hybrid
        base = tuple(families)
        order_pool = [base, tuple(reversed(base))]
        order_pool.extend(permutations(families))
        orders = list(dict.fromkeys(tuple(item["slug"] for item in order) for order in order_pool))
        by_slug = {family["slug"]: family for family in families}
        orders = [tuple(by_slug[slug] for slug in order) for order in orders[:3]]
        beam_width = max(6, min(8, 5 + refinement_passes))
        candidate_limit, placement_limit = 4, 2
    final_states = []
    for order in orders:
        states = [{"occupied": set(occupied), "height": anchor_height, "placements": []}]
        for family in order:
            next_states = []
            for state in states:
                family_shapes = candidates_by_slug[family["slug"]]
                if len(family_shapes) > candidate_limit:
                    family_shapes = family_shapes[:candidate_limit - 1] + [family_shapes[-1]]
                for shape in family_shapes:
                    if shape["w"] > width:
                        continue
                    for option in _placement_options(
                        shape, state["occupied"], width, 0, state["height"] + 1,
                        mode, placement_limit,
                    ):
                        next_states.append({
                            "occupied": state["occupied"] | option["cells"],
                            "height": option["height"],
                            "placements": state["placements"] + [{
                                "family": family, "shape": shape,
                                "x": option["x"], "y": option["y"],
                                "region_cells": option["cells"],
                            }],
                        })
            if not next_states:
                states = []
                break
            next_states.sort(key=lambda state: (
                state["height"], width * state["height"] - len(state["occupied"]),
                sum(item["shape"]["perimeter"] for item in state["placements"]),
            ))
            states = next_states[:beam_width]
        final_states.extend(states[:3])
    if not final_states:
        return None
    final_states.sort(key=lambda state: (
        state["height"], width * state["height"] - len(state["occupied"]),
    ))
    return final_states[:8]


def _interlock_polyomino_plan(plan: dict, target_aspect: float,
                              config: dict) -> dict:
    """Repack category-first family unions so their notches can interlock."""
    pinned = plan["pinned"]
    width = plan["W"]
    pinned_x = plan["title"]["w"]
    if pinned_x + pinned["shape"]["w"] > width:
        return plan
    pinned_cells = _translated(pinned["shape"]["cells"], pinned_x, 0)
    anchored = _cells_for_rect(
        plan["title"]["x"], plan["title"]["y"],
        plan["title"]["w"], plan["title"]["h"],
    ) | pinned_cells
    remaining_items = plan["families"]
    family_order = [item["family"] for item in remaining_items]
    candidates = {item["family"]["slug"]: [item["shape"]] for item in remaining_items}
    states = _pack_remaining(
        family_order, candidates, anchored, width,
        max(plan["title"]["h"], pinned["shape"]["h"]),
        "polyomino", "hybrid", max(4, int(config.get("solver", {}).get("refinement_passes", 5))),
    )
    if not states:
        return plan
    alternatives = []
    for state in states:
        height = state["height"]
        whole_unused = width * height - len(state["occupied"])
        # A Tetris candidate is only publishable when the family unions still
        # cover the complete rectangular canvas.  Compact but visibly grey
        # notches are not an improvement.
        if whole_unused:
            continue
        aspect_error = abs(math.log(max(0.05, (width / height) / target_aspect)))
        candidate = {
            "W": width, "H": height, "title": plan["title"],
            "pinned": {
                "family": pinned["family"], "shape": pinned["shape"],
                "x": pinned_x, "y": 0, "region_cells": pinned_cells,
            },
            "families": state["placements"], "occupied": state["occupied"],
            "quality": (
                round(aspect_error, 4), whole_unused, whole_unused,
                sum(item["shape"]["perimeter"] for item in state["placements"]), width,
            ),
        }
        candidate["movement_cost"] = _movement_cost(candidate, config)
        alternatives.append(candidate)
    if not alternatives:
        return plan
    best = min(alternatives, key=lambda candidate: (
        candidate["H"],
        candidate["W"] * candidate["H"] - len(candidate["occupied"]),
        candidate["quality"][0], candidate["movement_cost"],
    ))
    original_key = (
        plan["H"], plan["W"] * plan["H"] - len(plan["occupied"]),
        plan["quality"][0], plan.get("movement_cost", 0),
    )
    return best if (
        best["H"], best["W"] * best["H"] - len(best["occupied"]),
        best["quality"][0], best.get("movement_cost", 0),
    ) < original_key else plan


def _previous_positions(config: dict) -> dict[str, tuple[int, int, int, int]]:
    previous = config.get("_previous_layout") or {}
    return {
        item["slug"]: (item["x"], item["y"], item["w"], item["h"])
        for item in previous.get("categories", [])
        if not item.get("is_masthead")
    }


def _movement_cost(plan: dict, config: dict) -> int:
    previous = _previous_positions(config)
    if not previous:
        return 0
    total = 0
    for item in [plan["pinned"], *plan["families"]]:
        old = previous.get(item["family"]["slug"])
        if old:
            total += sum(abs(a - b) for a, b in zip(
                (item["x"], item["y"], item["shape"]["w"], item["shape"]["h"]), old
            ))
    return total


def _solve_mode(families: list[dict], target_aspect: float, config: dict, mode: str) -> dict:
    strategy = config.get("solver", {}).get("strategy", "heuristic")
    # The solid outer rectangle is a hard publishing invariant, so every
    # strategy uses the same exact-cover feasibility layer.  Strategy still
    # controls search breadth/order elsewhere, but may not opt back into the
    # former free-placement path that produced grey canvas voids.
    plan = _solve_legacy(families, target_aspect, config, mode)
    return (_interlock_polyomino_plan(plan, target_aspect, config)
            if mode == "polyomino" else plan)

    # Retained candidate-packing implementation for controlled experiments;
    # it is intentionally unreachable from publish/workbench solves until it
    # can guarantee an exact outer cover.
    max_iterations = max(8, int(config.get("solver", {}).get("max_iterations", 30)))
    refinement_passes = max(0, int(config.get("solver", {}).get("refinement_passes", 5)))
    family_limit = {
        "recursive_treemap": 3,
        "heuristic": 7,
        "cp_sat": 4,
        "hybrid": 5,
    }[strategy]
    candidates_by_slug = {
        family["slug"]: _family_candidates(family, config, target_aspect, family_limit)
        for family in families
    }
    pinned = next(family for family in families if family["slug"] == PINNED_FAMILY)
    others = [family for family in families if family["slug"] != PINNED_FAMILY]
    minimum_area = sum(min(candidate["area"] for candidate in candidates_by_slug[family["slug"]])
                       for family in families)
    # Category area already includes title bands and growth headroom.  The
    # masthead replaces (rather than doubles) the pinned family's top band.
    ideal_width = max(10, round(math.sqrt(minimum_area * target_aspect)))
    width_pool = list(range(max(10, ideal_width - 14), ideal_width + 25))
    strategy_width_limits = {
        "recursive_treemap": max_iterations,
        "heuristic": 6,
        "cp_sat": 4,
        "hybrid": 4,
    }
    width_limit = min(max_iterations, strategy_width_limits[strategy])
    if len(width_pool) > width_limit:
        width_pool = sorted({
            width_pool[round(index * (len(width_pool) - 1) / max(1, width_limit - 1))]
            for index in range(width_limit)
        })
    solved = []
    for width in width_pool:
        for pinned_shape in candidates_by_slug[pinned["slug"]]:
            if pinned_shape["w"] >= width - 3:
                continue
            title_w = max(6, round(width * 0.36))
            # The operator family is a coordinated top-row anchor immediately
            # beside the masthead, not a separate canvas-corner pin.
            pinned_x = title_w
            if pinned_x + pinned_shape["w"] > width:
                continue
            title_h = max(4, math.ceil(title_w * PITCH_X / (2.55 * PITCH_Y)))
            title_cells = _cells_for_rect(0, 0, title_w, title_h)
            pinned_cells = _cells_for_rect(pinned_x, 0, pinned_shape["w"], pinned_shape["h"])
            initial = title_cells | pinned_cells
            anchor_height = max(title_h, pinned_shape["h"])
            states = _pack_remaining(others, candidates_by_slug, initial, width, anchor_height,
                                     mode, strategy, refinement_passes)
            for state in states or []:
                height = state["height"]
                whole_unused = width * height - len(state["occupied"])
                family_slack = pinned_shape["slack"] + sum(
                    item["shape"]["slack"] for item in state["placements"])
                visual_unused = whole_unused + (family_slack if mode == "rectangular" else 0)
                aspect_error = abs(math.log(max(0.05, (width / height) / target_aspect)))
                solved.append({
                    "W": width, "H": height,
                    "title": {"x": 0, "y": 0, "w": title_w, "h": title_h},
                    "pinned": {"family": pinned, "shape": pinned_shape,
                               "x": pinned_x, "y": 0, "region_cells": pinned_cells},
                    "families": state["placements"], "occupied": state["occupied"],
                    "quality": (round(aspect_error, 4), visual_unused, whole_unused,
                                sum(item["shape"]["perimeter"] for item in state["placements"]), width),
                })
    if not solved:
        raise RuntimeError(f"No feasible {mode} layout was found")
    for plan in solved:
        plan["movement_cost"] = _movement_cost(plan, config)
    solved.sort(key=lambda plan: (
        plan["quality"][0] > 0.18, round(plan["quality"][0], 2),
        plan["quality"][1], plan["quality"][2], plan["quality"][3], plan["quality"][4],
    ))
    stability = config.get("layout_stability", {}).get("mode", "none")
    if not _previous_positions(config) or stability == "none":
        return solved[0]
    if stability == "locked":
        return min(solved, key=lambda plan: (plan["movement_cost"], plan["quality"]))
    if stability == "threshold":
        best = solved[0]
        tolerance = max(0.0, float(config.get("layout_stability", {}).get(
            "near_optimal_tolerance", 0.02)))
        best_pct = best["quality"][1] / max(1, best["W"] * best["H"])
        eligible = [plan for plan in solved
                    if plan["quality"][1] / max(1, plan["W"] * plan["H"])
                    <= best_pct + tolerance]
        return min(eligible, key=lambda plan: (plan["movement_cost"], plan["quality"]))
    # soft: whitespace/aspect remain dominant, with movement breaking close
    # alternatives.  Rounded buckets prevent tiny geometric gains from
    # completely rearranging the map.
    return min(solved, key=lambda plan: (
        plan["quality"][0] > 0.18,
        round(plan["quality"][0], 2),
        round(plan["quality"][1] / max(1, plan["W"] * plan["H"]), 2),
        plan["movement_cost"], plan["quality"],
    ))


def _diagnostics(plan: dict, mode: str, categories: list[dict], config: dict) -> dict:
    total_cells = plan["W"] * plan["H"]
    masthead_cells = plan["title"]["w"] * plan["title"]["h"]
    masthead_content_min_height = max(
        4, math.ceil(plan["title"]["w"] * PITCH_X / (2.8 * PITCH_Y))
    )
    family_items = [plan["pinned"], *plan["families"]]
    category_cells = sum(item["shape"]["area"] for item in family_items)
    rectangular_regions = sum(item["shape"]["bbox_area"] for item in family_items)
    family_regions = rectangular_regions if mode == "rectangular" else category_cells
    whole_unused = max(0, total_cells - masthead_cells - family_regions)
    internal_slack = rectangular_regions - category_cells if mode == "rectangular" else 0
    reserved_cells = sum(
        subcat["w"] * subcat["h"] for category in categories
        for subcat in category.get("subcats", []) if subcat.get("reserved")
    )
    visual_whitespace = whole_unused + internal_slack + reserved_cells
    dot_capacity = sum(subcat["dots"]["capacity"] for category in categories
                       for subcat in category.get("subcats", []))
    company_count = sum(category["member_count"] for category in categories
                        if not category["is_masthead"])
    requested_headroom = sum(subcat["dots"].get("requested_headroom", 0)
                             for category in categories for subcat in category.get("subcats", []))
    aspects = [subcat["w"] * PITCH_X / max(1, subcat["h"] * PITCH_Y)
               for category in categories for subcat in category.get("subcats", [])
               if not subcat.get("reserved")]
    shortened_labels = sum(
        subcat.get("label_en") != subcat.get("full_label_en") or
        subcat.get("label_fi") != subcat.get("full_label_fi")
        for category in categories for subcat in category.get("subcats", [])
    )
    strategy = config.get("solver", {}).get("strategy", "heuristic")
    strategy_backends = {
        "recursive_treemap": "deterministic exact-cover recursive integer treemap",
        "heuristic": "deterministic exact-cover heuristic search",
        "cp_sat": "dependency-free deterministic exact-cover constraint search",
        "hybrid": "exact-cover heuristic seed with deterministic constraint refinement",
    }
    stability = config.get("layout_stability", {}).get("mode", "none")
    interlock_cells = set()
    for index, item in enumerate(family_items):
        own_cells = _translated(item["shape"]["cells"], item["x"], item["y"])
        for other_index, other in enumerate(family_items):
            if index == other_index:
                continue
            other_bbox = _cells_for_rect(other["x"], other["y"], other["shape"]["w"], other["shape"]["h"])
            other_cells = _translated(other["shape"]["cells"], other["x"], other["y"])
            interlock_cells |= own_cells & (other_bbox - other_cells)
    if mode == "polyomino" and not interlock_cells:
        mode_explanation = (
            "No non-rectangular interlock satisfies the mandatory exact-cover constraint for "
            "this dataset. The category-first polyomino union therefore resolves to the same "
            "solid rectangle as rectangular mode instead of publishing grey voids."
        )
    elif mode == "polyomino":
        mode_explanation = f"Polyomino packing places {len(interlock_cells)} cells inside other family bounding-box voids."
    else:
        mode_explanation = (
            "Rectangular mode uses an exact-cover treemap: masthead and family rectangles "
            "cover every canvas cell, while extra category rows are reported as growth space."
        )
    pct = lambda value: round(value / max(1, total_cells) * 100, 1)
    overview_empty = visual_whitespace + max(0, dot_capacity - company_count)

    all_canvas_cells = _cells_for_rect(0, 0, plan["W"], plan["H"])
    masthead_region = _cells_for_rect(
        plan["title"]["x"], plan["title"]["y"],
        plan["title"]["w"], plan["title"]["h"],
    )
    family_bbox_cells: set[tuple[int, int]] = set()
    category_union_cells: set[tuple[int, int]] = set()
    reserved_region_cells: set[tuple[int, int]] = set()
    category_padding_region_cells: set[tuple[int, int]] = set()
    spare_slot_cells: set[tuple[int, int]] = set()
    hole_region_cells: set[tuple[int, int]] = set()
    empty_band_region_cells: set[tuple[int, int]] = set()
    for family in categories:
        if family.get("is_masthead"):
            continue
        family_bbox_cells |= _cells_for_rect(
            family["x"], family["y"], family["w"], family["h"]
        )
        local_union: set[tuple[int, int]] = set()
        for subcat in family.get("subcats", []):
            subcat_cells = _cells_for_rect(
                subcat["x"], subcat["y"], subcat["w"], subcat["h"]
            )
            category_union_cells |= subcat_cells
            local_union |= {(x - family["x"], y - family["y"])
                            for x, y in subcat_cells}
            if subcat.get("reserved"):
                reserved_region_cells |= subcat_cells
                continue
            dots = subcat.get("dots", {})
            columns = max(1, int(dots.get("cols", subcat["w"])))
            content_rows = max(1, int(dots.get(
                "content_rows", (1 if subcat.get("visible") else 0) +
                int(dots.get("rows", 0))
            )))
            if content_rows < subcat["h"]:
                category_padding_region_cells |= _cells_for_rect(
                    subcat["x"], subcat["y"] + content_rows,
                    subcat["w"], subcat["h"] - content_rows,
                )
            for slot in range(int(dots.get("count", 0)), int(dots.get("capacity", 0))):
                spare_slot_cells.add((
                    subcat["x"] + slot % columns,
                    subcat["y"] + 1 + slot // columns,
                ))
        holes, bands = _empty_shape_regions(local_union, family["w"], family["h"])
        hole_region_cells |= _translated(holes, family["x"], family["y"])
        empty_band_region_cells |= _translated(bands, family["x"], family["y"])
    rendered_family_cells = (family_bbox_cells if mode == "rectangular"
                             else category_union_cells)
    whole_canvas_cells = all_canvas_cells - masthead_region - rendered_family_cells
    family_slack_cells = ((family_bbox_cells - category_union_cells)
                          if mode == "rectangular" else set())
    prohibited_void_cells = whole_canvas_cells | hole_region_cells
    geometric_cells = (whole_canvas_cells | family_slack_cells |
                       reserved_region_cells | category_padding_region_cells)
    overview_cells = geometric_cells | spare_slot_cells
    category_padding = len(category_padding_region_cells)
    visual_whitespace = len(geometric_cells)
    overview_empty = len(overview_cells)

    def serialise_cells(cells: set[tuple[int, int]]) -> list[dict[str, int]]:
        return [{"x": x, "y": y} for x, y in sorted(cells, key=lambda cell: (cell[1], cell[0]))]

    return {
        "occupied_area_pct": round(100.0 - pct(visual_whitespace), 1),
        "unused_area_pct": pct(visual_whitespace),
        "visual_whitespace_cells": visual_whitespace,
        "visual_whitespace_pct": pct(visual_whitespace),
        "overview_empty_footprint_cells": overview_empty,
        "overview_empty_footprint_pct": pct(overview_empty),
        "whole_canvas_unused_cells": whole_unused,
        "whole_canvas_unused_pct": pct(whole_unused),
        "family_internal_slack_cells": internal_slack,
        "family_internal_slack_pct": pct(internal_slack),
        "reserved_empty_category_cells": reserved_cells,
        "category_internal_padding_cells": category_padding,
        "prohibited_void_cells": len(prohibited_void_cells),
        "family_bbox_void_cells": rectangular_regions - category_cells,
        "family_bbox_hole_cells": sum(item["shape"]["holes"] for item in family_items),
        "family_bbox_empty_band_cells": sum(item["shape"]["empty_bands"] for item in family_items),
        "disconnected_family_fragments": sum(max(0, item["shape"]["components"] - 1)
                                               for item in family_items),
        "one_cell_tendril_cells": sum(item["shape"]["tendrils"] for item in family_items),
        "polyomino_interlock_cells": len(interlock_cells) if mode == "polyomino" else 0,
        "layout_mode_explanation": mode_explanation,
        "company_count": company_count,
        "total_dot_capacity": dot_capacity,
        "spare_dot_capacity": dot_capacity - company_count,
        "requested_headroom_slots": requested_headroom,
        "grid_rounding_spare_slots": dot_capacity - company_count - requested_headroom,
        "max_category_aspect_ratio": round(max(aspects), 2) if aspects else 0,
        "mean_category_aspect_ratio": round(sum(aspects) / len(aspects), 2) if aspects else 0,
        "category_count": sum(len(category.get("subcats", [])) for category in categories),
        "visible_category_count": sum(not subcat.get("reserved") for category in categories
                                      for subcat in category.get("subcats", [])),
        "canvas_cells": {"w": plan["W"], "h": plan["H"]},
        "cell_pitch": {"x": PITCH_X, "y": PITCH_Y},
        "canvas_px": {"w": plan["W"] * PITCH_X, "h": plan["H"] * PITCH_Y},
        "masthead_height_cells": plan["title"]["h"],
        "masthead_content_min_height_cells": masthead_content_min_height,
        "masthead_alignment_rows": max(
            0, plan["title"]["h"] - masthead_content_min_height
        ),
        "masthead_height_explanation": (
            "The masthead starts at its bilingual content minimum and may grow only when the "
            "immediately adjacent top-strip families require it for a hole-free exact cover."
        ),
        "solver_backend": plan.get("solver_backend_override", strategy_backends[strategy]),
        "solver_strategy_explanation": (
            "The cp_sat policy uses the repository's dependency-free constrained-search "
            "backend because OR-Tools is not required or installed."
            if strategy == "cp_sat" else
            plan.get("solver_backend_override", strategy_backends[strategy])
        ),
        "headroom_basis": (
            "current-count size-adaptive proxy (historical category counts are not yet stored)"
            if config.get("capacity_headroom", {}).get("mode") == "adaptive"
            else config.get("capacity_headroom", {}).get("mode", "none")
        ),
        "shortened_label_count": shortened_labels,
        "short_label_explanation": (
            f"{shortened_labels} category labels use a shorter display form."
            if shortened_labels else
            "No shorter approved or experimental label changed this dataset."
        ),
        "layout_stability_mode": stability,
        "previous_layout_available": bool(_previous_positions(config)),
        "family_movement_cost_cells": plan.get("movement_cost", 0),
        "unsupported_or_inactive_policies": [],
        "highlight_cells": {
            "overview_empty": serialise_cells(overview_cells),
            "geometric_whitespace": serialise_cells(geometric_cells),
            "spare_slots": serialise_cells(spare_slot_cells),
            "family_slack": serialise_cells(family_slack_cells),
            "canvas_whitespace": serialise_cells(whole_canvas_cells),
            "category_padding": serialise_cells(category_padding_region_cells),
            "empty_bands": serialise_cells(empty_band_region_cells),
            "holes": serialise_cells(prohibited_void_cells),
        },
    }


def _build_layout_json(plan: dict, mode: str, format_name: str, config: dict) -> dict:
    categories = [{
        "slug": "__masthead__", "family": "__masthead__", "label_en": "", "label_fi": "",
        **plan["title"], "is_masthead": True,
        "shape_rects": [{"x": 0, "y": 0, "w": plan["title"]["w"], "h": plan["title"]["h"]}],
        "subcats": [], "member_count": 0,
    }]
    for item in [plan["pinned"], *plan["families"]]:
        family, shape = item["family"], item["shape"]
        x0, y0 = item["x"], item["y"]
        subcats = []
        for placement in shape["placements"]:
            group = family["groups"][placement["group_index"]]
            subcats.append({
                "slug": group["slug"], "label_en": group["label_en"], "label_fi": group["label_fi"],
                "full_label_en": group["full_label_en"], "full_label_fi": group["full_label_fi"],
                "description_en": group["description_en"], "description_fi": group["description_fi"],
                "x": x0 + placement["x"], "y": y0 + placement["y"],
                "w": placement["w"], "h": placement["h"],
                "visible": group["visible"], "reserved": group["reserved"],
                "dots": {"count": group["count"], "capacity": placement["capacity"],
                         "cols": placement["w"], "rows": placement["dot_rows"],
                         "content_rows": placement.get(
                             "content_h", placement["label_rows"] + placement["dot_rows"]
                         ),
                         "requested_headroom": placement["headroom"]},
                "font_size_px": placement["font_size_px"],
            })
        shape_rects = ([{"x": 0, "y": 0, "w": shape["w"], "h": shape["h"]}]
                       if mode == "rectangular" else
                       [{"x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"]}
                        for p in shape["placements"]])
        categories.append({
            "slug": family["slug"], "family": family["slug"],
            "label_en": family["label_en"], "label_fi": family["label_fi"],
            "x": x0, "y": y0, "w": shape["w"], "h": shape["h"], "is_masthead": False,
            "shape_rects": shape_rects, "subcats": subcats, "member_count": family["member_count"],
            "shape_diagnostics": {
                "area_cells": shape["area"], "bbox_cells": shape["bbox_area"],
                "bbox_void_cells": shape["slack"], "hole_cells": shape["holes"],
                "empty_band_cells": shape["empty_bands"], "perimeter": shape["perimeter"],
                "components": shape["components"], "one_cell_tendril_cells": shape["tendrils"],
                "category_padding_cells": shape.get("category_padding", 0),
            },
        })
    diagnostics = _diagnostics(plan, mode, categories, config)
    masthead = categories[0]
    pinned = next(category for category in categories if category["slug"] == PINNED_FAMILY)
    return {
        "format": format_name, "mode": mode,
        "requested_mode": _policy_value(config, "layout_mode", "rectangular"),
        "solver_strategy": config.get("solver", {}).get("strategy", "heuristic"),
        "canvas": {"cells_w": plan["W"], "cells_h": plan["H"]},
        "anchors": {
            "masthead": {key: masthead[key] for key in ("x", "y", "w", "h")},
            PINNED_FAMILY: {key: pinned[key] for key in ("x", "y", "w", "h")},
        },
        "policies_applied": {
            "empty_category_policy": _policy_value(config, "empty_category_policy", "show"),
            "capacity_headroom": deepcopy(config.get("capacity_headroom", {})),
            "category_order": config.get("category_order", {}).get("mode", "canonical_stable"),
            "language_geometry": config.get("language_geometry", {}).get("mode", "maximum_across_languages"),
            "category_font": deepcopy(config.get("category_font", {})),
            "layout_stability": deepcopy(config.get("layout_stability", {})),
            "reflow": deepcopy(config.get("reflow", {})),
            "short_labels": deepcopy(config.get("short_labels", {})),
            "layout_selection": deepcopy(config.get("layout_selection", {})),
            "category_shape_mode": "rectangular",
        },
        "categories": categories, "diagnostics": diagnostics,
    }


def _select_auto(rectangular: dict, polyomino: dict, config: dict) -> dict:
    selection = config.get("layout_selection", {})
    policy = selection.get("mode", "threshold")
    rect_pct = rectangular["diagnostics"]["visual_whitespace_pct"]
    poly_pct = polyomino["diagnostics"]["visual_whitespace_pct"]
    gain_points = rect_pct - poly_pct
    relative_gain = gain_points / max(0.1, rect_pct)
    if policy == "best_efficiency":
        chosen = polyomino if poly_pct < rect_pct else rectangular
    elif policy == "threshold":
        absolute = float(selection.get("polyomino_minimum_absolute_gain", 0.025)) * 100
        relative = float(selection.get("polyomino_minimum_relative_gain", 0.2))
        chosen = polyomino if gain_points >= absolute and relative_gain >= relative else rectangular
    else:
        chosen = rectangular
    chosen = deepcopy(chosen)
    chosen["alternatives"] = {
        "rectangular": rectangular["diagnostics"], "polyomino": polyomino["diagnostics"],
        "polyomino_gain_percentage_points": round(gain_points, 2),
        "polyomino_relative_gain": round(relative_gain, 3), "selection_policy": policy,
    }
    return chosen


def run(format_name: str = "landscape", config_override: dict | None = None) -> dict:
    """Solve one master layout without mutating layout_config.yaml."""
    config = _merge(_load_config(), config_override)
    _validate_config(config)
    if config.get("layout_stability", {}).get("use_previous_layout", False):
        suffix = "" if format_name == "landscape" else f"-{format_name}"
        previous_path = OUTPUT_DIR / f"layout{suffix}.json"
        if previous_path.exists():
            try:
                config["_previous_layout"] = json.loads(previous_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                config["_previous_layout"] = None
    taxonomy = load_json(TAXONOMY_PATH)
    indexes = taxonomy_index(taxonomy)
    indexes["taxonomy"] = taxonomy
    registry = load_json(REGISTRY_PATH)
    members = [member for member in registry if member.get("category") in indexes["category_slugs"]]
    families = _build_families(indexes, members, config)
    masters = config.get("responsive_layout", {}).get("masters", {})
    master = masters.get(format_name, masters.get("landscape", {}))
    target_aspect = (float(master.get("width_ratio", 16)) /
                     max(1.0, float(master.get("height_ratio", 9)))) * CELL_RATIO
    requested_mode = _policy_value(config, "layout_mode", "rectangular")
    if requested_mode == "auto":
        rectangular = _build_layout_json(
            _solve_mode(families, target_aspect, config, "rectangular"),
            "rectangular", format_name, config,
        )
        polyomino = _build_layout_json(
            _solve_mode(families, target_aspect, config, "polyomino"),
            "polyomino", format_name, config,
        )
        return _select_auto(rectangular, polyomino, config)
    if requested_mode not in {"rectangular", "polyomino"}:
        raise UnsupportedPolicyError(f"Unknown layout_mode={requested_mode}")
    return _build_layout_json(
        _solve_mode(families, target_aspect, config, requested_mode),
        requested_mode, format_name, config,
    )


def _print_diagnostics(layout: dict) -> None:
    diag = layout["diagnostics"]
    print(f"\nDiagnostics ({layout['format']}, {layout['mode']}):")
    print(f"  Canvas:             {diag['canvas_cells']['w']}×{diag['canvas_cells']['h']} cells "
          f"({diag['canvas_px']['w']}×{diag['canvas_px']['h']} px)")
    print(f"  Overview empty:     {diag['overview_empty_footprint_cells']} slots "
          f"(geometric emptiness plus spare dot slots)")
    print(f"  Geometric empty:    {diag['visual_whitespace_cells']} slots")
    print(f"    whole canvas:     {diag['whole_canvas_unused_cells']} slots")
    print(f"    family internal:  {diag['family_internal_slack_cells']} slots")
    print(f"    category growth:  {diag['category_internal_padding_cells']} slots")
    print(f"  Prohibited voids:   {diag['prohibited_void_cells']} slots")
    print(f"  Family bbox holes:  {diag['family_bbox_hole_cells']} cells")
    print(f"  Empty bands:        {diag['family_bbox_empty_band_cells']} cells")
    print(f"  Companies:          {diag['company_count']}")
    print(f"  Dot capacity:       {diag['total_dot_capacity']} "
          f"(spare {diag['spare_dot_capacity']}; requested headroom {diag['requested_headroom_slots']})")
    print(f"  Category aspect:    max {diag['max_category_aspect_ratio']}, mean {diag['mean_category_aspect_ratio']}")
    if diag["unsupported_or_inactive_policies"]:
        print("  Inactive policies:")
        for policy in diag["unsupported_or_inactive_policies"]:
            print(f"    - {policy}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FDCA policy-aware layout solver")
    parser.add_argument("--format", default="landscape", choices=["landscape", "portrait"])
    parser.add_argument("--mode", choices=["rectangular", "polyomino", "auto"])
    parser.add_argument("--strategy", choices=sorted(SUPPORTED_STRATEGIES))
    parser.add_argument("--output")
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    override = {}
    if args.mode:
        override["layout_mode"] = {"value": args.mode}
    if args.strategy:
        override["solver"] = {"strategy": args.strategy}
    layout = run(args.format, override)
    suffix = f"-{args.format}" if args.format != "landscape" else ""
    output = Path(args.output) if args.output else OUTPUT_DIR / f"layout{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    if args.diagnostics:
        _print_diagnostics(layout)


if __name__ == "__main__":
    main()
