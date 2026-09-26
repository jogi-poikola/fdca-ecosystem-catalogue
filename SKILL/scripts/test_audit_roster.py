#!/usr/bin/env python3
"""Tests for the roster audit and the Looper sync. They read no network."""

import os
import unittest
from unittest import mock

import audit_roster as ar
import merge_member_list as mm
import sync_looper


def entry(name, url="", official=None, status="website-only", **extra):
    return {"display_name": name, "official_name": official, "roster_status": status,
            "url": url, "category": "data_center_operators", **extra}


ROSTER = ["Oulun DataCenter Oy", "Acme Oy"]
OULU = entry("Oulun DataCenter Oy", "https://www.datacentermap.com/finland/oulu/glesys-oulu/",
             official="Oulun DataCenter Oy", status="on-roster")
ACME = entry("Acme Oy", "https://acme.fi", official="Acme Oy", status="on-roster")


def verdicts(registry, logos):
    with mock.patch.dict(mm.ALIASES, clear=True), mock.patch.dict(mm.FORMER_NOTES, clear=True):
        result = ar.audit(registry, ROSTER, logos)
    return {row["name"]: row["verdict"] for row in result["entries"]}, result


class AuditTest(unittest.TestCase):
    def test_brand_of_a_roster_company_is_an_alias_candidate(self):
        glesys = entry("Glesys Finland Oy", "https://www.glesys.fi")
        found, _ = verdicts([glesys, OULU, ACME], [("Glesys FDCA", "https://x/glesys.png")])
        self.assertEqual(ar.ALIAS_CANDIDATE, found["Glesys Finland Oy"])

    def test_absent_from_roster_and_page_is_likely_former(self):
        found, _ = verdicts([entry("Virtutect", "https://www.virtutect.com"), ACME], [])
        self.assertEqual(ar.LIKELY_FORMER, found["Virtutect"])

    def test_on_the_page_but_not_the_roster_is_still_listed(self):
        found, _ = verdicts([entry("Virtutect", "https://www.virtutect.com"), ACME],
                            [("Virtutect FDCA", "https://x/v.png")])
        self.assertEqual(ar.STILL_LISTED, found["Virtutect"])

    def test_offline_gives_no_live_verdict(self):
        found, _ = verdicts([entry("Virtutect", "https://www.virtutect.com"), ACME], None)
        self.assertEqual(ar.UNKNOWN, found["Virtutect"])

    def test_a_description_mention_alone_is_not_an_alias(self):
        noisy = entry("Uptime Institute", "https://www.uptimeinstitute.com")
        acme = dict(ACME, web_search_content="We guarantee uptime for data centres.")
        found, _ = verdicts([noisy, acme], [])
        self.assertEqual(ar.LIKELY_FORMER, found["Uptime Institute"])

    def test_agreeing_catalogue_reports_nothing(self):
        found, result = verdicts([OULU, ACME], [("Acme FDCA", "https://x/a.png")])
        self.assertEqual({}, found)
        self.assertEqual([], result["unclaimed_logos"])

    def test_a_logo_no_entry_claims_is_reported(self):
        _, result = verdicts([OULU, ACME], [("Kumorion FDCA", "https://x/k.jpg")])
        self.assertEqual([("Kumorion FDCA", "https://x/k.jpg")], result["unclaimed_logos"])

    def test_a_former_entry_the_roster_now_lists_is_reinstated(self):
        former = entry("Acme Oy", "https://acme.fi", status="former")
        with mock.patch.dict(mm.ALIASES, clear=True), mock.patch.dict(mm.FORMER_NOTES, clear=True):
            result = ar.audit([former, OULU], ROSTER, [])
        self.assertEqual([ar.REINSTATE], [row["verdict"] for row in result["entries"]])

    def test_a_settled_former_entry_stays_quiet(self):
        former = entry("Virtutect", "https://www.virtutect.com", status="former")
        found, _ = verdicts([former, OULU, ACME], [])
        self.assertEqual({}, found)

    def test_current_registry_has_no_open_decision_offline(self):
        from catalogue_config import load_registry

        result = ar.audit(load_registry(), mm.load_list(), None)
        self.assertEqual([], result["entries"])


class SyncTest(unittest.TestCase):
    def run_sync(self, env, require=False):
        calls = []
        with mock.patch.object(sync_looper, "run", side_effect=calls.append), \
             mock.patch.dict(os.environ, env):
            if "LOOPER_MIRROR_CMD" not in env:
                os.environ.pop("LOOPER_MIRROR_CMD", None)
            ran = sync_looper.refresh_and_mirror(build=True, require=require)
        return ran, calls

    def test_mirror_runs_last_and_only_after_the_validation_gate(self):
        ran, calls = self.run_sync({"LOOPER_MIRROR_CMD": "mirror-it --now"})
        self.assertTrue(ran)
        self.assertEqual(["mirror-it", "--now"], calls[-1])
        self.assertIn("--check", calls[-2])
        self.assertIn("build_dashboard.py", calls[1][1])

    def test_unset_command_skips_the_mirror_without_failing(self):
        ran, calls = self.run_sync({})
        self.assertFalse(ran)
        self.assertTrue(all("mirror" not in " ".join(c) for c in calls))

    def test_require_fails_when_the_command_is_unset(self):
        with self.assertRaises(SystemExit):
            self.run_sync({}, require=True)


if __name__ == "__main__":
    unittest.main()
