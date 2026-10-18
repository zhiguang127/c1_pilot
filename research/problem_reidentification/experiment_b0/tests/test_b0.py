"""Behavioral invariants of the experiment, never research outcome fixtures."""
import copy
import unittest
from ..core import selected, payload, tools, validate, evidence_audit, definitions, LOCAL, digest


class B0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.knowledge, _ = selected()

    def test_sampling_is_earliest_all_participants(self):
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(len({c["subject_id"] for c in self.cases}), 16)
        self.assertEqual({c["block"] for c in self.cases}, {0})
        self.assertTrue(all(len(c["candidate_ids"]) == 5 for c in self.cases))

    def test_tool_cannot_hide_days_and_does_not_include_gold(self):
        c = self.cases[0]
        events = []
        a = tools(c, self.knowledge, "only day 1", events)
        b = tools(c, self.knowledge, "all days", events)
        self.assertEqual(a, b)
        self.assertEqual(events[0]["full_record_count"], 42)
        self.assertEqual(events[0]["result_sha256"], digest(payload(c, self.knowledge)))
        self.assertNotIn("QWEN_MAX_SILVER", a["page"])
        self.assertNotIn("predicted_applicability", a["page"])

    def test_candidate_reversal_changes_no_evidence(self):
        c = self.cases[0]
        a, b = payload(c, self.knowledge), payload(c, self.knowledge, reverse=True)
        self.assertEqual(a["records"], b["records"])
        self.assertEqual(a["candidates"], b["candidates"][::-1])

    def test_partial_order_is_a_partition(self):
        c = self.cases[0]
        v = {"ranking": [c["candidate_ids"]], "items": [
            {"id": k, "applicability": "insufficient_information", "explanation": "unknown", "evidence": []}
            for k in c["candidate_ids"]]}
        self.assertEqual(validate(v, c), [])
        v["ranking"].append([c["candidate_ids"][0]])
        self.assertIn("ranking_must_partition_all_candidates", validate(v, c))

    def test_missingness_purpose_is_separate_from_physiology(self):
        c = copy.deepcopy(self.cases[0])
        c["days"][0]["metrics"]["resting_heart_rate_bpm"] = 0
        ref = {"ref": "d1.resting_heart_rate_bpm", "value": 0, "purpose": "missingness"}
        value = {"items": [{"evidence": [ref]}]}
        self.assertEqual(evidence_audit(value, c)["valid_citations"], 1)
        ref["purpose"] = "physiology"
        self.assertEqual(evidence_audit(value, c)["unusable_physiology"], 1)
        ref["ref"] = "d43.resting_heart_rate_bpm"
        self.assertEqual(evidence_audit(value, c)["invalid_reference"], 1)

    def test_exact_official_definitions_are_present(self):
        env = definitions(LOCAL / "upstream/critic/src/qa/critic.py", ["critic_iter"], {})
        self.assertEqual(env["critic_iter"].__code__.co_name, "critic_iter")

    def test_all_frozen_source_anchors_locate(self):
        for c in self.cases:
            p = payload(c, self.knowledge)
            self.assertEqual(len(p["candidates"]), 5)
            self.assertTrue(all(k["source_paragraphs"] for k in p["candidates"]))


if __name__ == "__main__":
    unittest.main()
