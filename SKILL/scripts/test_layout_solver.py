#!/usr/bin/env python3
"""Regression checks for layout policy behavior and geometry."""

from __future__ import annotations

import json
import unittest

from layout_solver import PINNED_FAMILY, UnsupportedPolicyError, run
from layout_tool import TOOL_HTML, _reflow_decision, meta_payload, options_to_override


FAST = {"solver": {"strategy": "recursive_treemap", "max_iterations": 16, "refinement_passes": 2}}


def cells(rect: dict) -> set[tuple[int, int]]:
    return {(x, y) for x in range(rect["x"], rect["x"] + rect["w"])
            for y in range(rect["y"], rect["y"] + rect["h"])}


class LayoutSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rect = run("landscape", {**FAST, "layout_mode": {"value": "rectangular"}})
        cls.poly = run("landscape", {**FAST, "layout_mode": {"value": "polyomino"}})

    def test_fixed_anchors_and_no_category_overlap(self) -> None:
        for layout in (self.rect, self.poly):
            masthead = layout["anchors"]["masthead"]
            pinned = layout["anchors"][PINNED_FAMILY]
            self.assertEqual((masthead["x"], masthead["y"]), (0, 0))
            self.assertEqual(pinned["y"], 0)
            self.assertEqual(pinned["x"], masthead["x"] + masthead["w"])
            occupied = cells(masthead)
            for family in layout["categories"]:
                for category in family.get("subcats", []):
                    category_cells = cells(category)
                    self.assertFalse(occupied & category_cells, category["slug"])
                    occupied |= category_cells
            self.assertEqual(
                occupied,
                {(x, y) for x in range(layout["canvas"]["cells_w"])
                 for y in range(layout["canvas"]["cells_h"])},
            )
            self.assertEqual(layout["diagnostics"]["prohibited_void_cells"], 0)

    def test_compaction_shrinks_top_and_bottom_bands(self) -> None:
        masthead = self.rect["anchors"]["masthead"]
        pinned = self.rect["anchors"][PINNED_FAMILY]
        self.assertEqual(masthead["h"], pinned["h"])
        self.assertLessEqual(self.rect["canvas"]["cells_h"], 20)
        self.assertEqual(self.rect["diagnostics"]["family_bbox_hole_cells"], 0)

    def test_both_masters_are_solid_outer_rectangles(self) -> None:
        for format_name in ("landscape", "portrait"):
            for mode in ("rectangular", "polyomino"):
                layout = run(format_name, {
                    **FAST, "layout_mode": {"value": mode},
                    "layout_stability": {"mode": "none", "use_previous_layout": False},
                })
                self.assertEqual(layout["diagnostics"]["whole_canvas_unused_cells"], 0)
                self.assertEqual(layout["diagnostics"]["prohibited_void_cells"], 0)

    def test_polyomino_is_real_and_well_formed(self) -> None:
        self.assertNotEqual(
            [category.get("shape_rects") for category in self.rect["categories"]],
            [category.get("shape_rects") for category in self.poly["categories"]],
        )
        diag = self.poly["diagnostics"]
        self.assertEqual(diag["family_internal_slack_cells"], 0)
        self.assertEqual(diag["family_bbox_hole_cells"], 0)
        self.assertEqual(diag["disconnected_family_fragments"], 0)
        self.assertIn("polyomino", diag["layout_mode_explanation"].lower())
        for family in self.poly["categories"]:
            if not family["is_masthead"]:
                self.assertEqual(family["shape_diagnostics"]["components"], 1)
                self.assertEqual(family["shape_diagnostics"]["hole_cells"], 0)

    def test_headroom_changes_capacity(self) -> None:
        none = run("landscape", {**FAST, "capacity_headroom": {"mode": "none"}})
        percentage = run("landscape", {
            **FAST,
            "capacity_headroom": {"mode": "percentage", "fraction": 0.15, "minimum_slots": 1},
        })
        self.assertLess(none["diagnostics"]["total_dot_capacity"],
                        percentage["diagnostics"]["total_dot_capacity"])
        self.assertEqual(none["diagnostics"]["requested_headroom_slots"], 0)

    def test_empty_category_policy_changes_visible_taxonomy(self) -> None:
        show = run("landscape", {**FAST, "empty_category_policy": {"value": "show"}})
        hide = run("landscape", {**FAST, "empty_category_policy": {"value": "hide"}})
        self.assertGreater(show["diagnostics"]["category_count"], hide["diagnostics"]["category_count"])

    def test_category_order_is_honored(self) -> None:
        taxonomy = run("landscape", {**FAST, "category_order": {"mode": "taxonomy"}})
        count = run("landscape", {**FAST, "category_order": {"mode": "count_descending"}})
        def order(layout: dict, slug: str) -> list[str]:
            family = next(category for category in layout["categories"] if category["slug"] == slug)
            return [category["slug"] for category in family["subcats"]]
        self.assertNotEqual(order(taxonomy, "technology_vendors"),
                            order(count, "technology_vendors"))

    def test_deterministic_and_all_solver_strategies_available(self) -> None:
        again = run("landscape", {**FAST, "layout_mode": {"value": "rectangular"}})
        self.assertEqual(json.dumps(self.rect, sort_keys=True), json.dumps(again, sort_keys=True))
        constrained = run("landscape", {
            **FAST, "solver": {"strategy": "cp_sat", "max_iterations": 8, "refinement_passes": 1},
            "layout_stability": {"mode": "none", "use_previous_layout": False},
        })
        self.assertIn("constraint search", constrained["diagnostics"]["solver_backend"])
        with self.assertRaises(UnsupportedPolicyError):
            run("landscape", {"solver": {"strategy": "imaginary"}})

    def test_adaptive_headroom_and_reflow_are_executable(self) -> None:
        adaptive = run("landscape", {
            **FAST, "capacity_headroom": {"mode": "adaptive", "minimum_slots": 1,
                                           "maximum_fraction": 0.2},
        })
        self.assertGreater(adaptive["diagnostics"]["requested_headroom_slots"], 0)
        self.assertIn("size-adaptive", adaptive["diagnostics"]["headroom_basis"])
        self.assertFalse(_reflow_decision("on_constraint_change", "count_change")[0])
        self.assertTrue(_reflow_decision("on_constraint_change", "capacity_overflow")[0])

    def test_browser_workbench_exposes_comparison_controls(self) -> None:
        for text in ("data-pane=\"a\"", "data-pane=\"b\"", "headroom",
                     "Landscape master", "Portrait master", "English + Finnish",
                     "Search algorithms", "data-metric", "highlight_cells"):
            self.assertIn(text, TOOL_HTML)
        self.assertNotIn("overview_empty_footprint_pct+'%'", TOOL_HTML)
        layout_modes = next(policy for policy in meta_payload()["policies"]
                            if policy["key"] == "mode")["values"]
        self.assertIn("polyomino", layout_modes)
        strategies = next(policy for policy in meta_payload()["policies"]
                          if policy["key"] == "strategy")["values"]
        self.assertIn("cp_sat", strategies)
        override = options_to_override({"mode": "polyomino", "empty": "hide",
                                        "headroom": "adaptive", "strategy": "hybrid"})
        self.assertEqual(override["layout_mode"]["value"], "polyomino")
        self.assertEqual(override["empty_category_policy"]["value"], "hide")
        self.assertEqual(override["capacity_headroom"]["mode"], "adaptive")
        self.assertEqual(override["solver"]["strategy"], "hybrid")

    def test_metric_highlights_match_absolute_slot_counts(self) -> None:
        diagnostics = self.rect["diagnostics"]
        expected = {
            "overview_empty": "overview_empty_footprint_cells",
            "geometric_whitespace": "visual_whitespace_cells",
            "spare_slots": "spare_dot_capacity",
            "family_slack": "family_internal_slack_cells",
            "canvas_whitespace": "whole_canvas_unused_cells",
            "category_padding": "category_internal_padding_cells",
            "empty_bands": "family_bbox_empty_band_cells",
            "holes": "prohibited_void_cells",
        }
        for key, field in expected.items():
            self.assertEqual(len(diagnostics["highlight_cells"][key]), diagnostics[field])


if __name__ == "__main__":
    unittest.main()
