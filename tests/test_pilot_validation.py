"""Offline integrity tests; no live pilot artifacts or model calls are consumed."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import validate_pilot as validator
from io_utils import ROOT


def ranking(size=20):
    return [{"rank": number, "knowledge_id": f"K{number:03d}", "score": 0.0}
            for number in range(1, size + 1)]


def representation_fixture():
    import tiktoken
    config = {"revision": "fixture-v1", "repeats": 3, "representation_output_tokens": 256,
              "llm": {"generator_model": "fixture-model", "backend": "fixture-backend"}}
    cases = [{"id": case_id} for case_id in sorted(validator.CASE_IDS)]
    state = {"config": config, "cases": cases, "inputs": {case["id"]: "a" * 64 for case in cases}}
    encoder = tiktoken.get_encoding("cl100k_base")
    records = []
    for case in cases:
        for baseline in sorted(validator.BASELINES):
            for repeat in (1, 2, 3):
                queries = ["sleep duration", "sleep timing", "activity variation", "baseline change", "temporal relation"] if baseline == "B3" else []
                text = "\n".join(queries) if queries else "facts" if baseline == "B4" else "Stable sleep and activity."
                records.append({"case_id": case["id"], "baseline_id": baseline, "repeat_id": repeat,
                                "text": text, "queries": queries, "input_sha256": "a" * 64,
                                "output_tokens": len(encoder.encode(text)),
                                "metadata": {"status": "completed", "configuration_revision": "fixture-v1",
                                             "knowledge_corpus_visible": False, "designer_fields_visible": False,
                                             "official_PHIA_execution": False, "token_counter": "cl100k_base",
                                             "model": None if baseline == "B4" else "fixture-model",
                                             "backend": "deterministic" if baseline == "B4" else "fixture-backend",
                                             "budget_tokens": None if baseline == "B4" else 256,
                                             "independent_fresh_context_repeat": baseline != "B4"}})
    manifest = {"input_hashes": state["inputs"], "same_input_for_all_conditions": True,
                "configuration_revision": "fixture-v1"}
    return state, records, manifest


def retrieval_fixture():
    state, representations, _ = representation_fixture()
    state["representations"] = representations
    state["representation_index"] = validator.unique_index(representations, ("case_id", "baseline_id", "repeat_id"))
    state["corpus"] = [{"id": item_id, "title": "Fixture title", "content": "Fixture content"}
                       for item_id in sorted(validator.KNOWLEDGE_IDS)]
    config = validator.normalize_config({"top_k": 20, "query_max_tokens": 512, "rrf_k": 60,
                                         "dense": {"model": "fixture-model", "revision": "f" * 40, "max_length": 512}})
    config_hash = validator.sha256_json(config)
    corpus_hash = validator.sha256_json(state["corpus"])
    records = {retriever: [] for retriever in validator.RETRIEVERS}
    for retriever in records:
        for representation in representations:
            query_records = []
            for number, query in enumerate(validator.representation_queries(representation)):
                text, diagnostic = validator.truncate_query(query, 512)
                entry = {"query_index": number, "query": text, **diagnostic, "ranking": ranking()}
                if retriever == "dense":
                    entry.update({"model_tokens_including_prefix": 8, "model_truncated": False, "model_max_length": 512})
                query_records.append(entry)
            baseline = representation["baseline_id"]
            final_ranking = validator.reciprocal_rank_fusion([query["ranking"] for query in query_records], 20, 60) if baseline == "B3" else ranking()
            records[retriever].append({"case_id": representation["case_id"], "baseline_id": baseline,
                                       "repeat_id": representation["repeat_id"], "retriever": retriever,
                                       "representation_status": "completed", "representation_input_sha256": "a" * 64,
                                       "config_sha256": config_hash, "corpus_sha256": corpus_hash,
                                       "fusion": "five-query RRF" if baseline == "B3" else "single-query",
                                       "ranking": final_ranking, "queries": query_records})
    manifest = {"config": config, "config_sha256": config_hash, "corpus_sha256": corpus_hash,
                "representations_sha256": validator.sha256_json(representations), "corpus_count": 96,
                "representation_count": 288, "retrievers_requested": ["bm25", "dense"],
                "retrievers_completed": ["bm25", "dense"], "dense_runtime": {**config["dense"],
                "similarity": "cosine", "normalized_embeddings": True}}
    return state, records, config, manifest


class MatrixTests(unittest.TestCase):
    def test_matrix_requires_every_pair_and_rejects_duplicates(self):
        expected = {("C001", "K001"), ("C001", "K002")}
        rows = [{"case_id": "C001", "knowledge_id": item_id} for item_id in ("K001", "K002")]
        self.assertEqual(set(validator.unique_index(rows, ("case_id", "knowledge_id"), expected)), expected)
        with self.assertRaisesRegex(ValueError, "missing"):
            validator.unique_index(rows[:1], ("case_id", "knowledge_id"), expected)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validator.unique_index(rows + rows[:1], ("case_id", "knowledge_id"), expected)

    def test_pending_judge_is_honest_but_not_final_gold(self):
        pending = {"status": "needs_review", "relevance": ""}
        self.assertIsNone(validator.annotation_value(pending, allow_pending=True))
        with self.assertRaises(ValueError):
            validator.annotation_value(pending)
        with self.assertRaises(ValueError):
            validator.annotation_value({"status": "needs_review", "relevance": "0"}, allow_pending=True)
        with self.assertRaises(ValueError):
            validator.annotation_value({"status": "labeled", "relevance": True})
        self.assertEqual(validator.annotation_value({"status": "labeled", "relevance": "2"}), 2)

    def test_csv_flags_are_not_coerced_from_numbers(self):
        self.assertTrue(validator.csv_boolean("True"))
        self.assertFalse(validator.csv_boolean("false"))
        for bad in (1, 0, "1", "yes", None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validator.csv_boolean(bad)


class AnnotationRevisionTests(unittest.TestCase):
    def setUp(self):
        from annotate_relevance import ANNOTATION_REVISION
        self.current_revision = ANNOTATION_REVISION

    def test_uniform_current_judge_and_adjudication_revisions_are_accepted(self):
        fixture_rows = [{"annotation_revision": self.current_revision}] * 2
        for role in ("judge_a", "judge_b", "adjudicated"):
            with self.subTest(role=role):
                validator.check_annotation_revision(fixture_rows, self.current_revision, role)

    def test_mixed_superseded_and_missing_revisions_are_rejected(self):
        variants = [[], [{"annotation_revision": "blinded-annotation-v1"}], [{}],
                    [{"annotation_revision": self.current_revision}, {"annotation_revision": "blinded-annotation-v1"}]]
        for fixture_rows in variants:
            with self.subTest(rows=fixture_rows), self.assertRaisesRegex(ValueError, "annotation revisions"):
                validator.check_annotation_revision(fixture_rows, self.current_revision, "judge_a")

    def test_three_column_gold_uses_current_producer_metadata(self):
        fixture_rows = [{"case_id": "fixture_case", "knowledge_id": "fixture_item", "relevance": "0"}]
        validator.check_gold_annotation_revision(fixture_rows, {"annotation_revision": self.current_revision}, self.current_revision)
        for metadata in ({}, {"annotation_revision": "blinded-annotation-v1"}):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "producer metadata"):
                validator.check_gold_annotation_revision(fixture_rows, metadata, self.current_revision)

    def test_gold_revision_column_cannot_conflict_with_producer_metadata(self):
        metadata = {"annotation_revision": self.current_revision}
        rows = [{"annotation_revision": self.current_revision}] * 2
        validator.check_gold_annotation_revision(rows, metadata, self.current_revision)
        for invalid in ([rows[0], {"annotation_revision": "blinded-annotation-v1"}], [rows[0], {}]):
            with self.subTest(rows=invalid), self.assertRaisesRegex(ValueError, "Gold CSV"):
                validator.check_gold_annotation_revision(invalid, metadata, self.current_revision)


class RankingTests(unittest.TestCase):
    def test_zero_score_tie_has_fixed_id_order(self):
        validator.validate_ranking(ranking())
        wrong = ranking()
        wrong[0]["knowledge_id"], wrong[1]["knowledge_id"] = wrong[1]["knowledge_id"], wrong[0]["knowledge_id"]
        with self.assertRaisesRegex(ValueError, "tie breaking"):
            validator.validate_ranking(wrong)

    def test_rankings_reject_partial_duplicate_unknown_and_nan(self):
        variants = [ranking(19), ranking(), ranking(), ranking(), ranking()]
        variants[1][1]["knowledge_id"] = "K001"
        variants[2][0]["knowledge_id"] = "K097"
        variants[3][0]["score"] = float("nan")
        variants[4][0]["rank"] = 0
        for value in variants:
            with self.subTest(value=value[0]), self.assertRaises(ValueError):
                validator.validate_ranking(value)

    def test_fusion_is_checked_against_saved_per_query_lists(self):
        from retrieval import reciprocal_rank_fusion
        expected = reciprocal_rank_fusion([ranking()] * 5, 20, 60)
        validator.rankings_equal(expected, deepcopy(expected))
        wrong = deepcopy(expected)
        wrong[0]["score"] += 0.001
        with self.assertRaisesRegex(ValueError, "recomputed RRF"):
            validator.rankings_equal(wrong, expected)


class RepresentationTests(unittest.TestCase):
    def run_fixture(self, state, records, manifest):
        with patch.object(validator, "read_jsonl", return_value=records), \
                patch.object(validator, "read_json", return_value=manifest), \
                patch.object(validator, "model_input", side_effect=lambda case: case), \
                patch("generate_representations.raw_statistical_facts", return_value="facts"):
            return validator.check_representations(ROOT, state)

    def test_full_matrix_allows_identical_deterministic_repeats(self):
        state, records, manifest = representation_fixture()
        result = self.run_fixture(state, records, manifest)
        self.assertEqual(result["count"], 288)
        self.assertEqual(len(state["representation_index"]), 288)

    def test_completed_counts_do_not_mask_failed_record(self):
        state, records, manifest = representation_fixture()
        records[0]["metadata"]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "Incomplete representation"):
            self.run_fixture(state, records, manifest)

    def test_openai_compatible_alias_matches_adapter_metadata(self):
        state, records, manifest = representation_fixture()
        state["config"]["llm"]["backend"] = "openai_compatible"
        for record in records:
            if record["baseline_id"] != "B4":
                record["metadata"]["backend"] = "openai_compatible_chat_completions"
        self.assertEqual(self.run_fixture(state, records, manifest)["count"], 288)

    def test_unrelated_provider_does_not_match_openai_compatible_alias(self):
        state, records, manifest = representation_fixture()
        state["config"]["llm"]["backend"] = "openai_compatible"
        for record in records:
            if record["baseline_id"] != "B4":
                record["metadata"]["backend"] = "openai_compatible_chat_completions"
        records[0]["metadata"]["backend"] = "codex_exec_chatgpt_login"
        with self.assertRaisesRegex(ValueError, "another provider/model"):
            self.run_fixture(state, records, manifest)

    def test_querygen_has_five_real_queries_and_common_raw_input(self):
        for mutation in ("missing_query", "blank_query", "input_hash"):
            with self.subTest(mutation=mutation):
                state, records, manifest = representation_fixture()
                target = next(record for record in records if record["baseline_id"] == "B3")
                if mutation == "missing_query":
                    target["queries"].pop()
                elif mutation == "blank_query":
                    target["queries"][0] = " "
                else:
                    target["input_sha256"] = "b" * 64
                with self.assertRaises(ValueError):
                    self.run_fixture(state, records, manifest)


class FreezeTests(unittest.TestCase):
    def test_freeze_detects_content_change_without_writing_files(self):
        payload = b"frozen cases"
        manifest = {"label_name": validator.LABEL_KIND, "no_benchmark_changes_after_results": True,
                    "file_sha256": {"data/wearable_cases.jsonl": hashlib.sha256(payload).hexdigest()}}
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "is_file", return_value=True), \
                patch.object(validator, "read_json", return_value=manifest), patch.object(Path, "read_bytes", return_value=payload):
            self.assertTrue(validator.check_freeze(ROOT)["integrity_valid"])
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "is_file", return_value=True), \
                patch.object(validator, "read_json", return_value=manifest), patch.object(Path, "read_bytes", return_value=b"changed"):
            with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                validator.check_freeze(ROOT)

    def test_manifest_cannot_escape_project(self):
        with self.assertRaisesRegex(ValueError, "leaves project"):
            validator.contained_path(ROOT, "../outside.json")
        self.assertEqual(validator.contained_path(ROOT, "data/knowledge_items.jsonl"), ROOT / "data/knowledge_items.jsonl")


class RetrievalTests(unittest.TestCase):
    def run_fixture(self, state, records, config, manifest):
        def read_json(path):
            return config if Path(path).name == "retrieval.json" else manifest

        def read_jsonl(path):
            return records[Path(path).stem]

        with patch.object(validator, "read_json", side_effect=read_json), \
                patch.object(validator, "read_jsonl", side_effect=read_jsonl):
            return validator.check_retrieval(ROOT, state)

    def test_complete_576_matrix_checks_standalone_retrievers_and_rrf(self):
        state, records, config, manifest = retrieval_fixture()
        result = self.run_fixture(state, records, config, manifest)
        self.assertEqual(result["count"], 576)
        self.assertEqual(result["retrievers"], ["bm25", "dense"])

    def test_matrix_and_configuration_fail_closed(self):
        for mutation in ("missing_run", "changed_config", "changed_query", "changed_rrf"):
            with self.subTest(mutation=mutation):
                state, records, config, manifest = retrieval_fixture()
                if mutation == "missing_run":
                    records["dense"].pop()
                elif mutation == "changed_config":
                    records["bm25"][0]["config_sha256"] = "b" * 64
                elif mutation == "changed_query":
                    records["bm25"][0]["queries"][0]["query"] = "different input"
                else:
                    target = next(record for record in records["bm25"] if record["baseline_id"] == "B3")
                    target["ranking"][0]["score"] += 0.001
                with self.assertRaises(ValueError):
                    self.run_fixture(state, records, config, manifest)


class MetricTests(unittest.TestCase):
    def test_metric_csv_preserves_na_and_rejects_wrong_values(self):
        expected = {"retriever": "bm25", "baseline_id": "B1", "label_kind": validator.LABEL_KIND,
                    **{metric: None for metric in validator.METRICS}, "case_count": 24}
        saved = {key: "" if value is None else str(value) for key, value in expected.items()}
        validator.compare_metric_csv([saved], [expected], ("retriever", "baseline_id"))
        wrong = {**saved, "recall_at_10": "0"}
        with self.assertRaisesRegex(ValueError, "differs from recomputed"):
            validator.compare_metric_csv([wrong], [expected], ("retriever", "baseline_id"))


class CompletionTests(unittest.TestCase):
    def test_any_failed_stage_fails_closed_and_other_stages_are_reported(self):
        names = ["load_config", "check_cases", "check_corpus", "check_annotations", "check_representations",
                 "check_retrieval", "check_metrics", "check_analysis", "check_reports", "check_freeze"]
        patches = [patch.object(validator, name, return_value={"fixture_only": True}) for name in names]
        for handle in patches:
            handle.start()
        try:
            self.assertTrue(validator.validate_pilot(ROOT)["valid"])
            with patch.object(validator, "check_retrieval", side_effect=ValueError("one missing retrieval run")):
                result = validator.validate_pilot(ROOT)
                self.assertFalse(result["valid"])
                self.assertEqual(result["status"], "INCOMPLETE_OR_INVALID")
                self.assertEqual(result["stages"]["retrieval"]["error_type"], "ValueError")
                self.assertTrue(result["stages"]["freeze"]["valid"])
                self.assertEqual(len(result["stages"]), 10)
        finally:
            for handle in reversed(patches):
                handle.stop()


if __name__ == "__main__":
    unittest.main()
