"""Synthetic SOFTWARE fixtures only. No result in this file is research Gold."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.problem_reidentification.experiment_a.src import common
from research.problem_reidentification.experiment_a.src.conditions import applicability, aggregate
from research.problem_reidentification.experiment_a.src.data import audit, candidates, evidence_value, representation
from research.problem_reidentification.experiment_a.src.evaluation import classification, evaluate, trusted_gold
from research.problem_reidentification.experiment_a.src.matching import parse_json, validate_item, validate_structure, require_official_smoke, run


def software_fixture():
    """Artificial data for software tests; never exported as a study case."""
    return {"case_id": "SOFTWARE_FIXTURE", "subject_id": "TEST_NOT_A_PERSON", "context": {"symptoms": None, "population": "Adults"},
            "quality_notes": ["fixture"], "candidate_ids": ["FIXTURE"], "days": [
                {"day": d, "phase": "baseline" if d <= 28 else "current", "weekday": (d-1)%7+1,
                 "quality_flags": [], "metrics": {"sleep_minutes": 400.0 if d != 30 else None,
                    "resting_heart_rate_bpm": 0 if d == 29 else 60,
                    "sleep_start_clock": "23:59:00" if d % 2 else "00:01:00"}}
                for d in range(1, 43)]}


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        common.LOCAL.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=common.LOCAL)
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()


class FrozenDataTests(unittest.TestCase):
    def test_actual_legacy_and_p1_freezes(self):
        a = audit()
        self.assertEqual((a["legacy_hashes_verified"], a["cases"], a["participants"], a["a0_pairs"]), (77, 48, 16, 240))
        self.assertIsNone(a["formal_metrics"])

    def test_a0_references_original_release(self):
        cases, knowledge, release_id = candidates()
        self.assertEqual(len(knowledge), 5)
        self.assertTrue(all(len(c["days"]) == 42 for c in cases))
        self.assertEqual(release_id, "872d04eb05394b3f3ac37c05dcefe320181e9375a674ba7c4fb57c8853742604")

    def test_a1_frozen_before_predictions(self):
        f = common.verify(common.ROOT / "data/releases/a1-v1")
        self.assertEqual((f["unique_knowledge"], f["unique_pairs"]), (26, 1248))
        self.assertFalse(f["human_gold"])
        data = common.rows(common.ROOT / "data/releases/a1-v1/cases.jsonl")
        self.assertTrue(all(set(c) == {"case_id", "candidate_ids"} for c in data))


class RepresentationTests(unittest.TestCase):
    def test_zero_rhr_not_physiology(self):
        s = representation(software_fixture(), "statistics")["statistics"]["current"]["metrics"]
        self.assertEqual(s["resting_heart_rate_bpm"]["n"], 13)
        self.assertEqual(s["resting_heart_rate_bpm"]["mean"], 60)
        self.assertEqual(s["sleep_minutes"]["missing_or_unusable"], 1)

    def test_clock_midnight_is_circular(self):
        s = representation(software_fixture(), "statistics")["statistics"]["current"]["metrics"]["sleep_start_clock"]
        self.assertLess(min(s["circular_mean_minute"], 1440-s["circular_mean_minute"]), 0.001)
        self.assertGreater(s["circular_resultant_length"], .99)

    def test_current_has_no_baseline_statistics(self):
        v = representation(software_fixture(), "current")
        self.assertEqual(set(v["statistics"]), {"current"})
        self.assertNotIn("days", v)

    def test_full_retains_42_rows_and_quality(self):
        v = representation(software_fixture(), "full")
        self.assertEqual(len(v["days"]), 42)
        self.assertNotIn("subject_id", v)
        self.assertNotIn("case_id", v)
        self.assertIsNone(v["context"]["symptoms"])

    def test_invalid_reference_fails(self):
        with self.assertRaises(ValueError):
            evidence_value(software_fixture(), "d43.sleep_minutes")
        with self.assertRaises(ValueError):
            evidence_value(software_fixture(), "d29.fabricated")


class ThreeValuedLogicTests(unittest.TestCase):
    def test_unknown_and_false_differ(self):
        expr = {"op": "all", "args": [{"op": "condition", "id": "a"}, {"op": "condition", "id": "b"}]}
        self.assertEqual(applicability(expr, {"a": "satisfied", "b": "unknown"}), "insufficient_information")
        self.assertEqual(applicability(expr, {"a": "satisfied", "b": "violated"}), "not_applicable")

    def test_disjunction_and_optional(self):
        expr = {"op": "all", "args": [{"op": "any", "args": [{"op": "condition", "id": "a"},
                    {"op": "condition", "id": "b"}]}, {"op": "optional", "id": "c"}]}
        self.assertEqual(applicability(expr, {"a": "violated", "b": "satisfied", "c": "unknown"}), "applicable")

    def test_na_cannot_bypass_required(self):
        with self.assertRaises(ValueError):
            aggregate({"op": "condition", "id": "a"}, {"a": "not_applicable_to_condition"})

    def test_conditional_premise(self):
        expr = {"op": "if", "premise": {"op": "condition", "id": "p"}, "then": {"op": "condition", "id": "q"}}
        self.assertEqual(aggregate(expr, {"p": "violated", "q": "not_applicable_to_condition"}), "satisfied")
        self.assertEqual(aggregate(expr, {"p": "unknown", "q": "satisfied"}), "unknown")


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = {"applicability": {"observable_conditions": ["A source-supported software condition"]}}
        self.item = {"applicability": "applicable", "observations": ["d29.sleep_minutes"],
                     "conditions": ["observable_conditions.0"], "missing_information": [], "rationale": "Software fixture"}

    def test_unknown_needs_missing_information(self):
        self.item["applicability"] = "insufficient_information"
        with self.assertRaises(ValueError):
            validate_item(self.item, software_fixture(), self.knowledge)

    def test_single_fenced_json_with_native_agent_prose(self):
        self.assertEqual(parse_json('Native introduction\n```json\n{"fixture":true}\n```'), {"fixture": True})
        with self.assertRaises(ValueError):
            parse_json('```json\n{}\n```\n```json\n{}\n```')

    def test_model_cannot_cite_null_or_zero_rhr(self):
        for reference in ("d30.sleep_minutes", "d29.resting_heart_rate_bpm"):
            self.item["observations"] = [reference]
            with self.assertRaises(ValueError):
                validate_item(self.item, software_fixture(), self.knowledge)

    def test_unknown_condition_reference_rejected(self):
        self.item["conditions"] = ["invented.0"]
        with self.assertRaises(ValueError):
            validate_item(self.item, software_fixture(), self.knowledge)

    def test_valid_label_retained_even_when_evidence_is_invalid(self):
        self.item["observations"] = ["d30.sleep_minutes"]
        self.assertEqual(validate_structure(self.item)["applicability"], "applicable")
        with self.assertRaises(ValueError):
            validate_item(self.item, software_fixture(), self.knowledge)

    def test_current_view_cannot_cite_unseen_baseline(self):
        self.item["observations"] = ["d1.sleep_minutes"]
        with self.assertRaises(ValueError):
            validate_item(self.item, software_fixture(), self.knowledge, current_only=True)

    def test_required_na_is_parse_failure(self):
        self.item["condition_judgments"] = [{"condition_id": "observable_conditions.0", "status": "not_applicable_to_condition",
                                            "role": "necessary", "observations": [], "rationale": "fixture"}]
        with self.assertRaises(ValueError):
            validate_item(self.item, software_fixture(), self.knowledge, condition_mode=True)

    def test_external_authorization_required(self):
        with self.assertRaisesRegex(ValueError, "authorization"):
            run("a0", None, "direct", "unused")

    def test_batch_needs_cost_review(self):
        with self.assertRaisesRegex(ValueError, "batch"):
            run("a0", None, "direct", "unused", limit=48, external_authorized=True)


class ArtifactAndMetricTests(IsolatedTest):
    def test_no_gold_no_accuracy(self):
        report = evaluate("a0", None, None, None, self.path / "evaluation.json")
        self.assertIsNone(report["formal_metrics"])
        self.assertEqual(report["status"], "PENDING_HUMAN_ANNOTATION")

    def test_frozen_tampering_rejected(self):
        common.write(self.path / "test.json", {"synthetic_fixture": True})
        common.freeze(self.path, ["test.json"], {"version": "SOFTWARE_FIXTURE"})
        common.write(self.path / "test.json", {"synthetic_fixture": False}, overwrite=True)
        with self.assertRaises(ValueError):
            common.verify(self.path)

    def test_provisional_gold_rejected(self):
        common.write(self.path / "provenance.json", {"data_release_id": "fixture", "gold_kind": "PROVISIONAL_LLM_GOLD"})
        common.write_rows(self.path / "gold.jsonl", [])
        common.freeze(self.path, ["provenance.json", "gold.jsonl"], {"version": "SOFTWARE_FIXTURE"})
        with self.assertRaises(ValueError):
            trusted_gold(self.path, "fixture")

    def test_private_output_boundary(self):
        with self.assertRaises(ValueError):
            common.private_path(common.ROOT / "results/predictions.jsonl")

    def test_exclusive_version_writes(self):
        common.write(self.path / "artifact.json", {})
        with self.assertRaises(FileExistsError):
            common.write(self.path / "artifact.json", {})

    def test_known_three_class_metrics(self):
        report = classification(list(common.LABELS), ["applicable", "not_applicable", "applicable"])
        self.assertAlmostEqual(report["false_applicability_rate"], .5)
        self.assertEqual(report["unknown_detection_rate"], 0)
        self.assertEqual(report["classes"]["not_applicable"]["support"], 1)
        self.assertIsNone(report["missing_condition_error_rate"])

    def test_a1_packets_really_hide_ids_and_labels(self):
        from research.problem_reidentification.experiment_a.src.annotation import packets
        result = packets("a1", common.ROOT / "data/releases/a1-v1", self.path / "review")
        text = (self.path / "review/A/CASE-001.html").read_text(encoding="utf-8")
        self.assertNotIn('"subject_id"', text)
        self.assertNotIn("K006", text)
        self.assertNotIn("P1-", text)
        template = common.rows(self.path / "review/A/annotations.template.jsonl")[0]
        self.assertFalse(template["human_attestation"])
        self.assertEqual(template["status"], "draft")
        self.assertEqual(result["pairs_per_reviewer"], 1248)


if __name__ == "__main__":
    unittest.main()
