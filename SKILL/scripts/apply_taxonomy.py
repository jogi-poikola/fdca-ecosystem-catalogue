#!/usr/bin/env python3
"""Compatibility entry point for validating registry classifications.

Taxonomy 4.0 stores one primary category per company. Historical migrations
are explicit scripts; this command never guesses or silently remaps a member.
"""

import argparse

from catalogue_config import (
    fail_on_errors,
    load_registry,
    load_rules,
    load_taxonomy,
    validate_registry,
    validate_taxonomy,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compatibility flag; validation never writes")
    parser.parse_args()
    taxonomy = load_taxonomy()
    rules = load_rules()
    members = load_registry()
    errors = validate_taxonomy(taxonomy, rules)
    errors += validate_registry(members, taxonomy, publish=True)
    fail_on_errors(errors)
    print(
        f"Registry valid: {len(members)} companies, taxonomy {taxonomy['version']}, "
        f"rules {rules['version']}, one primary category each."
    )


if __name__ == "__main__":
    main()
