"""Independent invariants for complete blinded provisional LLM annotation."""

import json
from concurrent.futures import Future
from io import StringIO
from pathlib import Path
import sys
import random
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import annotate_relevance as annotation
from evaluate import read_gold
import llm_client


def annotation_row(case_id, item_id, value):
    return {"case_id": case_id, "knowledge_id": item_id, "relevance": value}


class AnnotationTests(unittest.TestCase):
    def test_complete_2304_pair_agreement(self):
        rows = [annotation_row(f"C{case:03}", f"K{item:03}", (case + item) % 3)
                for case in range(1, 25) for item in range(1, 97)]
        result = annotation.agreement(rows, rows)
        self.assertEqual(result["pairs"], 2304)
        self.assertEqual(result["exact_agreement"], 1)
        self.assertEqual(result["linear_weighted_cohen_kappa"], 1)
        self.assertEqual(result["confusion_matrix_rows_a_columns_b"], [[768, 0, 0], [0, 768, 0], [0, 0, 768]])
        self.assertEqual(result["non_zero_disagreement_rate"], 0)

    def test_linear_weighted_kappa_and_nonzero_denominators(self):
        a = [annotation_row("C001", f"K{index:03}", value) for index, value in enumerate([0, 0, 1, 2], 1)]
        b = [annotation_row("C001", f"K{index:03}", value) for index, value in enumerate([0, 1, 1, 0], 1)]
        result = annotation.agreement(a, b)
        self.assertEqual(result["confusion_matrix_rows_a_columns_b"], [[1, 1, 0], [0, 1, 0], [1, 0, 0]])
        self.assertEqual(result["exact_agreement"], 0.5)
        self.assertAlmostEqual(result["linear_weighted_cohen_kappa"], 0)
        self.assertEqual(result["non_zero_disagreement_rate"], 0.5)
        self.assertAlmostEqual(result["nonzero_union_disagreement_rate"], 2 / 3)

    def test_all_zero_kappa_and_nonzero_union_undefined(self):
        rows = [annotation_row("C001", "K001", 0), annotation_row("C001", "K002", 0)]
        result = annotation.agreement(rows, rows)
        self.assertEqual(result["exact_agreement"], 1)
        self.assertIsNone(result["linear_weighted_cohen_kappa"])
        self.assertIsNone(result["nonzero_union_disagreement_rate"])

    def test_judge_coverage_difference_is_error(self):
        with self.assertRaises(ValueError):
            annotation.agreement([annotation_row("C001", "K001", 0)], [annotation_row("C001", "K002", 0)])

    def test_case_validator_rejects_duplicate_missing_and_empty_evidence(self):
        mapping = {"ref1": "K001", "ref2": "K002"}
        valid = {"labels": [{"item_ref": ref, "relevance": 0, "rationale": "No observable necessary condition.",
                             "raw_data_evidence": "Only date-stamped steps are observed.",
                             "item_condition_evidence": "Item requires symptoms absent from the available context."}
                            for ref in mapping]}
        annotation.validate_complete_labels(valid, mapping)
        duplicate = {"labels": [valid["labels"][0], valid["labels"][0]]}
        with self.assertRaises(ValueError):
            annotation.validate_complete_labels(duplicate, mapping)
        with self.assertRaises(ValueError):
            annotation.validate_complete_labels({"labels": valid["labels"][:1]}, mapping)
        valid["labels"][0]["rationale"] = " "
        with self.assertRaises(ValueError):
            annotation.validate_complete_labels(valid, mapping)

    def test_item_blinding_omits_id_domain_keywords_provenance(self):
        item = {"id": "K001", "title": "Example", "content": "Source-supported example.", "applicability": {},
                "source": "Example authority", "source_url": "https://example.org", "source_locator": "heading",
                "domain": "case_sensitive_secret", "keywords": ["secret"], "provenance": {"secret": "secret"}}
        mapping, visible = annotation.blinded_items([item], 1729)
        self.assertEqual(set(mapping.values()), {"K001"})
        self.assertFalse(set(visible[0]) & {"id", "domain", "keywords", "provenance"})

    def test_judge_prompt_case_view_is_strictly_blinded(self):
        case = {"id": "C001", "case_type": "secret_case_type", "window_days": 14, "baseline_days": 28,
                "periods": {}, "observations": {}, "derived_statistics": {},
                "designer_notes": {"stratum": "B", "secret": "DESIGNER_LEAK"},
                "metadata": {"age_band": "18-60", "timezone": "Asia/Shanghai", "device": {}, "quality_policy": {},
                             "synthetic": True, "data_origin": "ORIGIN_LEAK"}}
        item = {"id": "K001", "title": "Example", "content": "Source-supported example.", "applicability": {},
                "source": "Example authority", "source_url": "https://example.org", "source_locator": "heading"}
        captured = {}

        def fake_call(prompt, schema, model, task_id, config, **kwargs):
            captured["prompt"] = prompt
            captured["task_id"] = task_id
            reference = schema["properties"]["labels"]["items"]["properties"]["item_ref"]["enum"][0]
            result = {"labels": [{"item_ref": reference, "relevance": 0, "status": "labeled",
                                   "rationale": "The needed context is unavailable.", "raw_data_evidence": "No symptom observations.",
                                   "item_condition_evidence": "The item requires observed symptoms."}]}
            if "validate_result" in kwargs:
                kwargs["validate_result"](result)
            return result, {"model": model, "input_sha256": "hash"}

        experiment = {"seed": 1729, "llm": {"judge_a_model": "model-a", "judge_b_model": "model-b"}}
        with patch.object(annotation, "call_model", side_effect=fake_call):
            rows = annotation.judge_case(case, [item], "judge_a", experiment)
        payload = json.loads(captured["prompt"].split("\nDATA=", 1)[1])
        self.assertEqual(set(payload["wearable"]), {"window_days", "baseline_days", "periods", "observations", "derived_statistics", "metadata"})
        for forbidden in ("C001", "secret_case_type", "DESIGNER_LEAK", "ORIGIN_LEAK", "designer_notes"):
            self.assertNotIn(forbidden, captured["prompt"])
        self.assertEqual(rows[0]["case_id"], "C001")
        self.assertIn(annotation.ANNOTATION_REVISION, captured["task_id"])
        self.assertEqual(rows[0]["annotation_revision"], annotation.ANNOTATION_REVISION)

    def test_missing_gold_label_never_becomes_zero(self):
        with patch.object(Path, "open", return_value=StringIO("case_id,knowledge_id,relevance\nC001,K001,0\n")):
            with self.assertRaises(ValueError):
                read_gold(Path("labels.csv"), {"C001"}, {"K001", "K002"})

    def test_cached_model_response_rejects_changed_input_before_calling_backend(self):
        config = {"backend": "codex_exec_chatgpt_login"}
        schema = llm_client.object_schema({"value": {"type": "integer"}})
        with patch.object(llm_client, "api_call_model") as run:
            with self.assertRaises(llm_client.LLMError):
                llm_client.call_model("prompt", schema, "model", "test", config)
            run.assert_not_called()

    def test_duplicate_pairs_are_not_silently_deduplicated(self):
        row = annotation_row("C001", "K001", 0)
        with self.assertRaises(ValueError):
            annotation.agreement([row, row], [row])
        with self.assertRaises(ValueError):
            annotation.validate_pair_matrix([row, row], {"C001"}, {"K001"})

    def test_matrix_requires_every_pair_and_only_valid_ids(self):
        rows = [annotation_row("C001", "K001", 0)]
        with self.assertRaises(ValueError):
            annotation.validate_pair_matrix(rows, {"C001"}, {"K001", "K002"})
        with self.assertRaises(ValueError):
            annotation.validate_pair_matrix(rows, {"C002"}, {"K001"})

    def test_pending_annotation_remains_null_until_adjudication(self):
        pending = {"labels": [{"item_ref": "r1", "status": "needs_review", "relevance": None,
                                "rationale": "Conflicting source conditions need review.",
                                "raw_data_evidence": "Observed comparison is incomplete.",
                                "item_condition_evidence": "The condition is internally ambiguous."}]}
        annotation.validate_complete_labels(pending, {"r1": "K001"})
        with self.assertRaises(ValueError):
            annotation.validate_complete_labels(pending, {"r1": "K001"}, require_resolved=True)
        rows = [annotation_row("C001", "K001", None) | {"status": "needs_review"}]
        annotation.validate_pair_matrix(rows, {"C001"}, {"K001"}, allow_pending=True)
        with self.assertRaises(ValueError):
            annotation.validate_pair_matrix(rows, {"C001"}, {"K001"})

    def test_pending_agreement_uses_resolved_denominator(self):
        a = [annotation_row("C001", "K001", None), annotation_row("C001", "K002", 1)]
        b = [annotation_row("C001", "K001", 0), annotation_row("C001", "K002", 1)]
        result = annotation.agreement(a, b)
        self.assertEqual(result["pairs"], 2)
        self.assertEqual(result["resolved_pairs"], 1)
        self.assertEqual(result["pending_either"], 1)
        self.assertEqual(result["exact_agreement"], 1)
        empty = annotation.agreement([], [])
        self.assertIsNone(empty["exact_agreement"])
        self.assertIsNone(empty["linear_weighted_cohen_kappa"])

    def test_practice_cases_are_independent_series_without_design_fields(self):
        practice = annotation.calibration_cases({"age_band": "18-60", "timezone": "Asia/Shanghai",
                                                "device": {}, "quality_policy": {}})
        self.assertEqual([case["id"] for case in practice], ["P001", "P002", "P003"])
        for case in practice:
            self.assertNotIn("designer_notes", case)
            self.assertNotIn("case_type", case)
            self.assertEqual(len(case["observations"]["baseline_daily"]), 28)
            self.assertEqual(len(case["observations"]["window_daily"]), 14)
            self.assertTrue(case["periods"]["baseline"]["start_date"].startswith("2025-"))
        self.assertEqual(practice[0]["derived_statistics"]["metric_statistics"]["sleep_duration_minutes"]["window"]["mean"], 330)
        self.assertTrue(any(row["metrics"]["steps"] is None for row in practice[2]["observations"]["window_daily"]))

    def test_short_refs_are_assigned_after_unchanged_seeded_shuffle(self):
        items = [{"id": f"K{index:03}", "title": f"Knowledge{index}", "content": "body", "applicability": {},
                  "source": "authority", "source_url": "https://example.org", "source_locator": "heading"}
                 for index in range(1, 97)]
        expected = list(items)
        random.Random(1729).shuffle(expected)
        mapping, visible = annotation.blinded_items(items, 1729)
        self.assertEqual(list(mapping), [f"item_{index:03}" for index in range(1, 97)])
        self.assertEqual(list(mapping.values()), [item["id"] for item in expected])
        self.assertEqual([item["title"] for item in visible], [item["title"] for item in expected])
        self.assertNotEqual(list(mapping.values()), [item["id"] for item in items])
        self.assertTrue(all("id" not in item for item in visible))

    def test_collector_drains_every_future_and_checkpoints_success_after_failure(self):
        failure, success = Future(), Future()
        failure.set_exception(ValueError("mistyped item reference"))
        success.set_result([annotation_row("C002", "K001", 0)])
        pending = {failure: ("C001", "judge_a"), success: ("C002", "judge_a")}
        with patch.object(annotation, "as_completed", return_value=[failure, success]), \
             patch.object(annotation, "write_json") as write, patch("builtins.print"):
            with self.assertRaises(RuntimeError):
                annotation.collect_checkpointed(pending, "judges", Path("checkpoints"), Path("failures.json"))
        checkpoint_calls = [call for call in write.call_args_list if call.args[0] == Path("checkpoints/judge_a_C002.json")]
        self.assertEqual(len(checkpoint_calls), 1)
        final = write.call_args_list[-1].args[1]
        self.assertTrue(final["all_jobs_handled"])
        self.assertEqual(final["completed_case_jobs"], 1)
        self.assertEqual(len(final["failures"]), 1)
        self.assertEqual(final["failures"][0]["case_id"], "C001")

    def test_failed_judge_collection_does_not_write_complete_csv(self):
        cases = [{"id": f"C{index:03}"} for index in range(1, 25)]
        items = [{"id": f"K{index:03}", "status": "verified"} for index in range(1, 97)]
        experiment = {"seed": 1729, "llm": {"max_workers": 2}}
        with patch.object(sys, "argv", ["annotate_relevance.py", "--stage", "judges", "--case-limit", "2"]), \
             patch.object(annotation, "read_jsonl", side_effect=[cases, items]), \
             patch.object(annotation, "read_json", return_value=experiment), \
             patch.object(annotation, "judge_case", return_value=[]), \
             patch.object(annotation, "collect_checkpointed", side_effect=RuntimeError("submitted jobs handled, one failure")), \
             patch.object(annotation, "write_csv") as write:
            with self.assertRaises(RuntimeError):
                annotation.main()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
