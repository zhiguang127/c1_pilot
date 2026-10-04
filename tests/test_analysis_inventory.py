"""Completion boundary uses exact case IDs, not an integer count."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from validate_pilot import CASE_IDS, check_analysis_summary


class AnalysisInventoryTests(unittest.TestCase):
    def setUp(self):
        self.summary = {"semantic_audit_available_for_cases": sorted(CASE_IDS),
                        "top_five_failure_candidates": sorted(CASE_IDS)[:5]}

    def test_complete_case_id_list_is_accepted(self):
        check_analysis_summary(self.summary)

    def test_count_missing_duplicate_and_unknown_cases_rejected(self):
        for inventory in (24, sorted(CASE_IDS)[:-1], ["C001"] * 24,
                          sorted(CASE_IDS)[:-1] + ["C999"]):
            with self.subTest(inventory=inventory):
                value = deepcopy(self.summary)
                value["semantic_audit_available_for_cases"] = inventory
                with self.assertRaises(ValueError):
                    check_analysis_summary(value)

    def test_five_distinct_existing_failure_cases_required(self):
        for failures in (["C001"] * 5, ["C001", "C002", "C003", "C004", "C999"],
                         ["C001"]):
            value = deepcopy(self.summary)
            value["top_five_failure_candidates"] = failures
            with self.assertRaises(ValueError):
                check_analysis_summary(value)


if __name__ == "__main__":
    unittest.main()
