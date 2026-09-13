#!/usr/bin/env python3
"""
FDCA Ecosystem Map — Layout Configuration Tool
================================================
Interactive tool for exploring how layout policy options influence the output.
Runs the layout solver with different configurations and compares diagnostics.

Usage:
  # Show current config and its diagnostics
  python3 layout_tool.py

  # Compare two layout modes
  python3 layout_tool.py --compare layout_mode rectangular polyomino

  # Test different empty category policies
  python3 layout_tool.py --compare empty_category_policy show hide

  # Test different capacity headroom settings
  python3 layout_tool.py --compare capacity_headroom.mode percentage none

  # Run diagnostics across all master formats
  python3 layout_tool.py --all-formats

  # Interactive mode (choose from menus)
  python3 layout_tool.py --interactive
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "OUTPUT"
CONFIG_PATH = Path(__file__).with_name("layout_config.yaml")

# Import the solver
from layout_solver import run as solve_layout


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def config_set(config: dict, path: str, value) -> dict:
    """Set a nested config key by dot-path, e.g. 'layout_mode.value'."""
    keys = path.split(".")
    target = config
    for k in keys[:-1]:
        target = target.setdefault(k, {})
    target[keys[-1]] = value
    return config


def config_get(config: dict, path: str):
    """Get a nested config key by dot-path."""
    keys = path.split(".")
    target = config
    for k in keys:
        if isinstance(target, dict):
            target = target.get(k)
        else:
            return None
    return target


def run_with_config(config: dict, format_name: str = "landscape") -> dict | None:
    """Run the solver with a temporary config override.

    Writes temp config, runs solver, restores original.
    """
    original = load_config()
    save_config(config)
    try:
        return solve_layout(format_name)
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None
    finally:
        save_config(original)


def print_diagnostics(diag: dict, indent: str = "  ") -> None:
    """Pretty-print layout diagnostics."""
    cc = diag.get("canvas_cells", {})
    cw = cc.get("cells_w", cc.get("w", "?"))
    ch = cc.get("cells_h", cc.get("h", "?"))
    cp = diag.get("canvas_px", {})
    pw = cp.get("w", "?")
    ph = cp.get("h", "?")
    print(f"{indent}Canvas:     {cw}×{ch} cells ({pw}×{ph} px)")
    print(f"{indent}Occupied:   {diag['occupied_area_pct']}%")
    print(f"{indent}Unused:     {diag['unused_area_pct']}%")
    print(f"{indent}Companies:  {diag['company_count']}")
    print(f"{indent}Dot capacity: {diag['total_dot_capacity']}"
          f" (spare: {diag['spare_dot_capacity']})")
    print(f"{indent}Max aspect: {diag['max_category_aspect_ratio']}")
    print(f"{indent}Mean aspect:{diag['mean_category_aspect_ratio']}")
    print(f"{indent}Categories: {diag.get('category_count', 'N/A')}")


def print_comparison(
    name_a: str, diag_a: dict | None,
    name_b: str, diag_b: dict | None,
) -> None:
    """Print a side-by-side comparison of two diagnostic sets."""
    print(f"\n{'Metric':<25} {name_a:<25} {name_b:<25} Δ")
    print("-" * 80)

    if not diag_a or not diag_b:
        print("  One or both configs failed to solve.")
        return

    metrics = [
        ("Unused area", "unused_area_pct", "%", False),
        ("Dot capacity", "total_dot_capacity", "", False),
        ("Spare dots", "spare_dot_capacity", "", True),
        ("Max aspect ratio", "max_category_aspect_ratio", "", False),
        ("Mean aspect ratio", "mean_category_aspect_ratio", "", False),
        ("Canvas (cells)", "canvas_cells", "", False),
    ]

    for label, key, unit, lower_is_better in metrics:
        va = diag_a.get(key, "N/A")
        vb = diag_b.get(key, "N/A")
        if isinstance(va, dict):
            cw_a = va.get("cells_w", va.get("w", "?"))
            ch_a = va.get("cells_h", va.get("h", "?"))
            va_str = f"{cw_a}×{ch_a}"
            if isinstance(vb, dict):
                cw_b = vb.get("cells_w", vb.get("w", "?"))
                ch_b = vb.get("cells_h", vb.get("h", "?"))
                vb_str = f"{cw_b}×{ch_b}"
            else:
                vb_str = str(vb)
            delta = ""
        elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            va_str = f"{va}{unit}"
            vb_str = f"{vb}{unit}"
            delta_val = vb - va
            if lower_is_better:
                winner = "← better" if delta_val > 0 else ("→ better" if delta_val < 0 else "same")
            else:
                winner = "← better" if delta_val < 0 else ("→ better" if delta_val > 0 else "same")
            delta = f"{delta_val:+.1f}{unit} {winner}"
        else:
            va_str = str(va)
            vb_str = str(vb)
            delta = ""
        print(f"{label:<25} {va_str:<25} {vb_str:<25} {delta}")


def cmd_show_current() -> None:
    """Show current configuration and run diagnostics."""
    config = load_config()
    print("Current layout configuration:\n")

    # Show key settings
    sections = [
        "layout_mode", "category_shape_mode", "empty_category_policy",
        "capacity_headroom", "language_geometry", "category_font",
        "category_title_max_lines", "category_order", "layout_stability",
        "reflow", "short_labels", "solver", "responsive_layout",
    ]
    for section in sections:
        val = config.get(section, {})
        if isinstance(val, dict) and "value" in val:
            status = val.get("status", "configurable")
            print(f"  {section}: {val['value']}  [{status}]")
        elif isinstance(val, dict) and "mode" in val:
            status = val.get("status", "configurable")
            print(f"  {section}: {val['mode']}  [{status}]")
        elif isinstance(val, dict):
            print(f"  {section}: {json.dumps(val)}")
        else:
            print(f"  {section}: {val}")

    print("\nRunning solver with current config...\n")
    for fmt in ["landscape", "portrait"]:
        layout = solve_layout(fmt)
        if layout:
            print(f"\n── {fmt.upper()} ──")
            print_diagnostics(layout["diagnostics"])


def cmd_compare(config_path: str, value_a: str, value_b: str) -> None:
    """Compare two values for a config key."""
    config = load_config()

    # Parse the comparison path (e.g., "layout_mode" or "capacity_headroom.mode")
    if "." in config_path:
        actual_key = config_path.split(".")[0]
        value_key = config_path.split(".")[-1]
    else:
        actual_key = config_path
        value_key = "value"

    print(f"Comparing {config_path}: {value_a} vs {value_b}\n")

    names = []
    diags = []
    for val in [value_a, value_b]:
        cfg = load_config()
        cfg = config_set(cfg, f"{actual_key}.{value_key}", val)
        print(f"Solving with {config_path} = {val}...")
        layout = run_with_config(cfg, "landscape")
        if layout:
            diag = layout["diagnostics"]
            diag["canvas_cells"] = layout["canvas"]
            names.append(str(val))
            diags.append(diag)
            print_diagnostics(diag, indent="    ")
        else:
            names.append(f"{val} (failed)")
            diags.append(None)

    if len(diags) == 2:
        print_comparison(names[0], diags[0], names[1], diags[1])


def cmd_all_formats() -> None:
    """Run diagnostics for all master formats."""
    config = load_config()
    masters = config.get("responsive_layout", {}).get("masters", {})

    results = {}
    for fmt in masters:
        print(f"\n── {fmt.upper()} ({masters[fmt]['width_ratio']}:{masters[fmt]['height_ratio']}) ──")
        layout = solve_layout(fmt)
        if layout:
            results[fmt] = layout["diagnostics"]
            print_diagnostics(layout["diagnostics"])

    if len(results) >= 2:
        formats = list(results.keys())
        print_comparison(
            formats[0], results[formats[0]],
            formats[1], results[formats[1]],
        )


def cmd_interactive() -> None:
    """Simple interactive menu for exploring configurations."""
    config = load_config()

    scenarios = {
        "1": {
            "name": "Show current diagnostics",
            "action": lambda: cmd_show_current(),
        },
        "2": {
            "name": "Compare layout modes (rectangular vs polyomino)",
            "action": lambda: cmd_compare("layout_mode", "rectangular", "polyomino"),
        },
        "3": {
            "name": "Compare empty category policies (show vs hide)",
            "action": lambda: cmd_compare("empty_category_policy", "show", "hide"),
        },
        "4": {
            "name": "Compare headroom modes (percentage vs none)",
            "action": lambda: cmd_compare("capacity_headroom.mode", "percentage", "none"),
        },
        "5": {
            "name": "Compare order modes (canonical_stable vs taxonomy)",
            "action": lambda: cmd_compare("category_order.mode", "canonical_stable", "taxonomy"),
        },
        "6": {
            "name": "Run all formats",
            "action": lambda: cmd_all_formats(),
        },
    }

    print("FDCA Layout Configuration Tool")
    print("=" * 50)
    print("\nAvailable scenarios:\n")
    for key, sc in scenarios.items():
        print(f"  [{key}] {sc['name']}")

    print("\n  [q] Quit")
    print()

    while True:
        try:
            choice = input("Select an option > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice.lower() == "q":
            break

        if choice in scenarios:
            print(f"\n── {scenarios[choice]['name']} ──\n")
            scenarios[choice]["action"]()
            print()
        else:
            print(f"Unknown option: {choice}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="FDCA Layout Configuration Tool — explore layout policy options",
    )
    parser.add_argument(
        "--compare", nargs=3,
        metavar=("CONFIG_PATH", "VALUE_A", "VALUE_B"),
        help="Compare two values for a config key",
    )
    parser.add_argument(
        "--all-formats", action="store_true",
        help="Run diagnostics for all master formats",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="Interactive menu mode",
    )
    args = parser.parse_args()

    if args.compare:
        cmd_compare(*args.compare)
    elif args.all_formats:
        cmd_all_formats()
    elif args.interactive:
        cmd_interactive()
    else:
        # Default: show current config and diagnostics
        cmd_show_current()


if __name__ == "__main__":
    main()