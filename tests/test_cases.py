"""Behavioral regression checks for construction, time alignment and missingness."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from case_statistics import descriptive_statistics, model_input, paired_statistics
from generate_cases import generate_cases
from validate_cases import validate_case, validate_dataset, validate_matched_pairs


class WearableCasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = generate_cases()
        cls.schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/wearable_case.schema.json").read_text(encoding="utf-8"))

    def test_full_design_validates_and_is_reproducible(self):
        report = validate_dataset(self.cases, self.schema)
        self.assertTrue(report["valid"], report)
        self.assertEqual(self.cases, generate_cases())
        self.assertEqual(1008, report["daily_row_count"])

    def test_missing_day_not_zero_and_not_calendar_compressed(self):
        rows = [{"date": "2026-04-01", "metrics": {"steps": 10}},
                {"date": "2026-04-02", "metrics": {"steps": None}},
                {"date": "2026-04-03", "metrics": {"steps": 30}}]
        stats = descriptive_statistics(rows, "steps")
        self.assertEqual(20, stats["mean"])
        self.assertEqual(10, stats["slope_per_day"])
        self.assertIsNone(stats["adjacent_mean_abs_delta"])
        c008 = self.cases[7]
        self.assertEqual(13, c008["derived_statistics"]["metric_statistics"]["steps"]["window"]["valid_count"])
        broken = deepcopy(c008)
        broken["observations"]["window_daily"][8]["metrics"]["steps"] = 0
        self.assertTrue(any("wear requirement" in error or "missing reason" in error for error in validate_case(broken)))

    def test_statistics_and_dates_tampering_detected(self):
        broken = deepcopy(self.cases[0])
        broken["derived_statistics"]["metric_statistics"]["sleep_duration_minutes"]["window"]["mean"] += 1
        self.assertTrue(any("recomputed" in error for error in validate_case(broken)))
        broken = deepcopy(self.cases[0])
        broken["observations"]["window_daily"][1]["date"] = broken["observations"]["window_daily"][0]["date"]
        self.assertTrue(any("calendar period" in error for error in validate_case(broken)))

    def test_interval_totals_and_coverage_tampering_detected(self):
        broken = deepcopy(self.cases[0])
        row = broken["observations"]["window_daily"][0]
        row["low_movement_intervals"][0]["end_at"] = (datetime.fromisoformat(
            row["low_movement_intervals"][0]["end_at"]) + timedelta(minutes=1)).isoformat()
        self.assertTrue(any("do not add" in error for error in validate_case(broken)))
        broken = deepcopy(self.cases[12])
        broken["observations"]["window_daily"][1]["daytime_wear_minutes"] = 1100
        self.assertTrue(any("exceeds 1440" in error for error in validate_case(broken)))

    def test_matched_marginal_and_timing_changes_detected(self):
        self.assertTrue(all(result["valid"] for result in validate_matched_pairs(self.cases)))
        broken = deepcopy(self.cases)
        broken[4]["observations"]["window_daily"][0]["metrics"]["sleep_duration_minutes"] += 1
        self.assertTrue(any("multisets differ" in error for result in validate_matched_pairs(broken) for error in result["errors"]))
        broken = deepcopy(self.cases)
        broken[22]["observations"]["window_daily"] = deepcopy(broken[20]["observations"]["window_daily"])
        self.assertTrue(any("next-wake-date" in error for result in validate_matched_pairs(broken) for error in result["errors"]))

    def test_lag_is_calendar_not_row_shift(self):
        rows = [{"date": "2026-04-01", "metrics": {"steps": 1, "activity_duration_minutes": 3}},
                {"date": "2026-04-03", "metrics": {"steps": 2, "activity_duration_minutes": 6}},
                {"date": "2026-04-04", "metrics": {"steps": 3, "activity_duration_minutes": 9}}]
        result = paired_statistics(rows, "steps", "activity_duration_minutes", 1)
        self.assertEqual(1, result["paired_count"])
        self.assertIsNone(result["pearson_r"])

    def test_whitelist_excludes_design_information(self):
        view = model_input(self.cases[20])
        self.assertEqual({"window_days", "baseline_days", "periods", "observations", "derived_statistics", "metadata"}, set(view))
        self.assertEqual({"age_band", "timezone", "device", "quality_policy"}, set(view["metadata"]))
        view["observations"]["window_daily"][0]["metrics"]["steps"] = -1
        self.assertGreaterEqual(self.cases[20]["observations"]["window_daily"][0]["metrics"]["steps"], 0)


if __name__ == "__main__":
    unittest.main()
