#!/usr/bin/env python3
"""Regression tests for the catalogue taxonomy and single-category contract."""

import unittest

from catalogue_config import (
    load_registry,
    load_rules,
    load_taxonomy,
    taxonomy_index,
    validate_registry,
    validate_taxonomy,
)
from validate_catalogue import guide_text, load_family_colours, summary_text, validate_design


class CatalogueContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_taxonomy()
        cls.rules = load_rules()
        cls.members = load_registry()

    def test_taxonomy_and_rules_are_consistent(self):
        self.assertEqual([], validate_taxonomy(self.taxonomy, self.rules))

    def test_every_company_has_one_publishable_category(self):
        self.assertEqual([], validate_registry(self.members, self.taxonomy, publish=True))
        self.assertTrue(all("subcategory" not in member for member in self.members))

    def test_family_is_derived_for_every_company(self):
        category_family = taxonomy_index(self.taxonomy)["category_family"]
        self.assertTrue(all(member["category"] in category_family for member in self.members))

    def test_design_owns_exactly_one_colour_per_family(self):
        self.assertEqual([], validate_design(self.taxonomy))
        self.assertEqual(
            {family["slug"] for family in self.taxonomy["families"]},
            set(load_family_colours()),
        )

    def test_generated_views_are_current(self):
        from catalogue_config import GUIDE_PATH, SUMMARY_PATH

        self.assertEqual(guide_text(self.taxonomy, self.rules, self.members), GUIDE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(summary_text(self.taxonomy, self.members), SUMMARY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
