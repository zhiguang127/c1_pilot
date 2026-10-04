"""Meaningful invariants for graded metrics, matching and query aggregation."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluate import cluster_bootstrap, construction_clusters, ranking_metrics
from retrieval import BM25Retriever, rank_scores, reciprocal_rank_fusion, representation_queries, truncate_query
from audit_representations import anonymize, validate_audit
from failure_analysis import raw_facts


def ranking(*ids):
    return [{"knowledge_id": item_id, "rank": index, "score": 0.0} for index, item_id in enumerate(ids, start=1)]


class EvaluationTests(unittest.TestCase):
    def test_graded_ndcg_not_binary(self):
        metrics = ranking_metrics(ranking("K2", "K1", "K3"), {"K1": 2, "K2": 1, "K3": 0})
        expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
        self.assertAlmostEqual(metrics["ndcg_at_10"], expected)
        self.assertEqual(metrics["recall_at_10"], 1)
        self.assertEqual(metrics["strong_recall_at_10"], 1)
        self.assertEqual(metrics["false_positives_at_10"], ["K3"])

    def test_all_zero_gold_is_not_perfect_or_zero_ndcg(self):
        metrics = ranking_metrics(ranking("K1"), {"K1": 0})
        self.assertIsNone(metrics["ndcg_at_10"])
        self.assertIsNone(metrics["recall_at_10"])
        self.assertIsNone(metrics["strong_recall_at_10"])
        self.assertEqual(metrics["irrelevant_fraction_at_10"], 1)

    def test_empty_query_is_visible_failure(self):
        metrics = ranking_metrics([], {"K1": 2})
        self.assertEqual(metrics["recall_at_10"], 0)
        self.assertEqual(metrics["ndcg_at_10"], 0)
        self.assertIsNone(metrics["irrelevant_fraction_at_10"])
        self.assertEqual(metrics["empty_result"], 1)

    def test_label_absence_is_error(self):
        with self.assertRaises(ValueError):
            ranking_metrics(ranking("K_unknown"), {"K1": 0})
        with self.assertRaises(ValueError):
            ranking_metrics(ranking("K1", "K1"), {"K1": 1})
        with self.assertRaises(ValueError):
            ranking_metrics([{"knowledge_id": "K1", "rank": 2}], {"K1": 1})

    def test_rrf_not_concatenated_word_bag(self):
        fused = reciprocal_rank_fusion([ranking("K2", "K1"), ranking("K1", "K3")], 3)
        self.assertEqual(fused[0]["knowledge_id"], "K1")
        self.assertAlmostEqual(fused[0]["score"], 1 / 62 + 1 / 61)

    def test_querygen_exactly_five_and_failed_record_empty(self):
        with self.assertRaises(ValueError):
            representation_queries({"case_id": "C1", "baseline_id": "B3", "queries": ["sleep"]})
        self.assertEqual(representation_queries({"case_id": "C1", "baseline_id": "B3", "status": "failed"}), [])

    def test_ties_deterministic_and_empty_bm25_not_all_zeros(self):
        self.assertEqual(rank_scores(["K2", "K1"], [0, 0], 2)[0]["knowledge_id"], "K1")
        corpus = [{"id": "K2", "title": "Sleep", "content": "daily sleep"},
                  {"id": "K1", "title": "Activity", "content": "walking steps"}]
        retriever = BM25Retriever(corpus)
        self.assertEqual(retriever.retrieve("", 20), [])
        self.assertEqual(retriever.retrieve("unknownterm", 20)[0]["knowledge_id"], "K1")

    def test_shared_query_truncation_preserves_original_punctuation(self):
        query, meta = truncate_query("Sleep: 7 hours. Steps: 5000 daily.", 3)
        self.assertEqual(query, "Sleep: 7 hours")
        self.assertTrue(meta["truncated"])

    def test_clusters_not_labels_or_repeats(self):
        clusters = construction_clusters({f"C{index:03}" for index in range(1, 25)})
        self.assertEqual(len(clusters), 19)
        self.assertIn(["C003", "C005"], clusters)
        interval = cluster_bootstrap({"C003": 0.2, "C005": -0.2}, [["C003", "C005"]], 100, 1729)
        self.assertEqual(interval["mean_difference"], 0)
        self.assertEqual(interval["lower_95"], 0)
        self.assertEqual(interval["upper_95"], 0)
        self.assertEqual(interval["case_count"], 2)
        self.assertEqual(interval["cluster_count"], 1)

    def test_audit_blinding_keeps_method_mapping_out_of_prompt_records(self):
        records = [{"case_id": "C003", "baseline_id": "B1", "repeat_id": 0, "text": "Sleep fell later."},
                   {"case_id": "C003", "baseline_id": "B3", "repeat_id": 0, "queries": ["sleep"] * 5}]
        anonymous, mapping = anonymize(records, "C003", 1729)
        self.assertTrue(all(set(record) == {"representation_ref", "representation_text"} for record in anonymous))
        self.assertEqual({record["baseline_id"] for record in mapping.values()}, {"B1", "B3"})

    def test_audit_invented_date_cannot_count_as_retained(self):
        case = {"observations": {"baseline_daily": [], "window_daily": [{"date": "2026-04-01", "metrics": {"steps": 100}}]}}
        mapping = {"R01": {"baseline_id": "B1", "repeat_id": 0, "text": "Steps were 100."}}
        audit = {"facts": [{"fact_id": "F1", "knowledge_ids": ["K1"],
                            "raw_data_support": [{"period": "window", "dates": ["2026-04-99"], "field_paths": ["metrics.steps"]}],
                            "representation_checks": [{"representation_ref": "R01", "status": "retained", "representation_excerpt": "Steps were 100."}]}],
                 "unsupported_interpretations": [], "potential_retrieval_noise": []}
        checked, notes = validate_audit(audit, case, {"K1"}, mapping)
        self.assertEqual(checked["facts"][0]["representation_checks"][0]["status"], "uncertain")
        self.assertTrue(notes)

    def test_audit_unsupported_quote_cannot_count_as_retained(self):
        case = {"observations": {"baseline_daily": [], "window_daily": [{"date": "2026-04-01", "metrics": {"steps": 100}}]}}
        mapping = {"R01": {"baseline_id": "B1", "repeat_id": 0, "text": "Steps were 100."}}
        audit = {"facts": [{"fact_id": "F1", "knowledge_ids": ["K1"],
                            "raw_data_support": [{"period": "window", "dates": ["2026-04-01"], "field_paths": ["metrics.steps"]}],
                            "representation_checks": [{"representation_ref": "R01", "status": "retained", "representation_excerpt": "Steps were 1000."}]}],
                 "unsupported_interpretations": [], "potential_retrieval_noise": []}
        checked, _ = validate_audit(audit, case, {"K1"}, mapping)
        self.assertEqual(checked["facts"][0]["representation_checks"][0]["status"], "uncertain")

    def test_activity_sleep_probe_uses_next_wake_date(self):
        window = [{"date": "2026-04-01", "metrics": {"sleep_duration_minutes": 480},
                   "activity_intervals": [{"start_at": "2026-04-01T20:00:00+08:00", "end_at": "2026-04-01T21:00:00+08:00"}]},
                  {"date": "2026-04-02", "metrics": {"sleep_duration_minutes": 330}, "activity_intervals": []},
                  {"date": "2026-04-03", "metrics": {"sleep_duration_minutes": 450}, "activity_intervals": []}]
        facts = raw_facts({"observations": {"baseline_daily": [], "window_daily": window}})
        relation = next(fact for fact in facts if fact["fact_id"] == "activity_sleep:lag_one_alignment")
        self.assertEqual(relation["following_sleep_mean_with_evening_activity"], 330)
        self.assertEqual(relation["following_sleep_mean_without_evening_activity"], 450)
        self.assertEqual(relation["aligned_daily_records"][0]["sleep_wake_date"], "2026-04-02")


if __name__ == "__main__":
    unittest.main()
