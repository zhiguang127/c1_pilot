import unittest
from unittest.mock import patch
from research.problem_reidentification.experiment_c0.pilot import (
    make_cards, top_pairs, public_audit, check_blinding, check_freeze, check_runs,
    AuditBlocked, EXPECTED_CANDIDATES, prepare_local,
)


def sample(case_id, subject):
    ids = ["K001", "K002", "K003", "K004", "K005"]
    return {"case_id": case_id, "candidate_ids": ids,
            "packet": {"records": {"daily": [1, 2, 3], "subject": subject},
                       "candidates": [{"id": k} for k in ids]}}


def output(rank=None):
    ranking = rank if rank is not None else [["K001"], ["K002", "K003"], ["K004", "K005"]]
    return {"ranking": ranking,
            "items": [{"id": k, "applicability": "insufficient_information",
                       "explanation": "sample", "evidence": []}
                      for k in ["K001", "K002", "K003", "K004", "K005"]],
            "pairwise_reasons": [{"higher": "K001", "lower": "K002", "reason": "sample reasoning"}]}


class C0Tests(unittest.TestCase):
    def test_paired_top_tier_ties_are_not_forced(self):
        self.assertEqual(top_pairs(output()), [("K001", "K002"), ("K001", "K003")])
        self.assertEqual(top_pairs(output([["K001", "K002", "K003", "K004", "K005"]])), [])

    def test_blind_and_deterministic(self):
        cases = [sample("c2", "private"), sample("c1", "another")]
        runs = [{"case_id": "c1", "method": "B1_direct", "status": "EXECUTED", "output": output()},
                {"case_id": "c2", "method": "B1_direct", "status": "EXECUTED", "output": output()}]
        a = make_cards(cases, runs, seed=7, methods=("B1_direct", "B4_critic"))
        b = make_cards(cases, runs, seed=7, methods=("B1_direct", "B4_critic"))
        self.assertEqual(a, b)
        case_cards, explanation_cards, crosswalk, missing = a
        self.assertEqual(len(case_cards), 2)
        self.assertEqual(len(explanation_cards), 4)
        self.assertEqual(len(missing), 2)
        self.assertIn("B1_direct", str(crosswalk))
        self.assertNotIn("B1_direct", str(explanation_cards))
        self.assertNotIn("c1", str(explanation_cards))
        self.assertEqual(explanation_cards[0]["goal_policy"], "UNSPECIFIED_IN_B0")
        self.assertNotIn("output", explanation_cards[0])

    def test_stage1_shuffling_does_not_mutate_input(self):
        from copy import deepcopy
        c = sample("original", "secret")
        old = deepcopy(c)
        stage1, stage2, _, _ = make_cards([c], [], methods=())
        self.assertEqual(c, old)
        self.assertNotIn("ranking", stage1[0])
        self.assertEqual(sorted(x["id"] for x in stage1[0]["data_and_sources"]["candidates"]),
                         old["candidate_ids"])
        self.assertEqual(stage2, [])

    def test_invalid_and_missing_are_preserved(self):
        runs = [{"case_id": "c1", "method": "B1_direct", "status": "INVALID_OUTPUT"}]
        _, cards, _, missing = make_cards([sample("c1", "s")], runs, methods=("B1_direct", "B4_critic"))
        self.assertEqual(cards, [])
        self.assertEqual([x["status"] for x in missing], ["INVALID_OUTPUT", "MISSING_RECORD"])

    def test_tie_output_kept_with_null_pair(self):
        cases = [sample("c1", "s")]
        runs = [{"case_id": "c1", "method": "B1_direct", "status": "EXECUTED",
                 "output": output([["K001", "K002", "K003", "K004", "K005"]])}]
        _, cards, _, _ = make_cards(cases, runs, methods=("B1_direct",))
        self.assertEqual(len(cards), 1)
        self.assertIsNone(cards[0]["higher"])
        self.assertIsNone(cards[0]["lower"])

    def test_bad_accepted_partition_rejected(self):
        runs = [{"case_id": "c1", "method": "B1_direct", "status": "EXECUTED",
                 "output": output([["K001"], ["K002"]])}]
        with self.assertRaises(ValueError):
            make_cards([sample("c1", "s")], runs, methods=("B1_direct",))

    def test_duplicate_run_rejected(self):
        runs = [{"case_id": "c1", "method": "B1_direct", "status": "FAILED"}] * 2
        with self.assertRaises(ValueError):
            make_cards([sample("c1", "s")], runs, methods=("B1_direct",))

    def test_duplicate_items_cannot_hide_behind_mapping(self):
        value = output()
        value["items"].append(value["items"][0])
        with self.assertRaises(ValueError):
            make_cards([sample("c1", "s")], [{"case_id": "c1", "method": "B1_direct",
                       "status": "EXECUTED", "output": value}], methods=("B1_direct",))

    def test_stage1_removes_source_identity_without_changing_evidence(self):
        case = sample("case-secret", "private-subject")
        case["packet"]["records"] = {"case_id": "case-secret", "subject_id": "private-subject",
                                         "daily_rows": [[1, None], [2, 7]]}
        cards, explanations, key, _ = make_cards([case], [], methods=())
        self.assertEqual(cards[0]["data_and_sources"]["records"],
                         {"daily_rows": [[1, None], [2, 7]]})
        check_blinding(cards, explanations, ["case-secret", "private-subject"])
        self.assertEqual(key[0]["case_id"], "case-secret")

    def test_blinding_rejects_method_in_explanation_without_rewriting_it(self):
        cards = [{"explanation": "CRITIC supports this"}]
        with self.assertRaises(ValueError):
            check_blinding([], cards, [])
        self.assertEqual(cards[0]["explanation"], "CRITIC supports this")

    def test_blinding_rejects_private_identity_and_stage1_model_metadata(self):
        with self.assertRaises(ValueError):
            check_blinding([], [{"text": "secret-subject"}], ["secret-subject"])
        with self.assertRaises(ValueError):
            check_blinding([{"ranking": []}], [], [])

    def test_real_card_seed_is_private_and_changes_ids(self):
        case = sample("c1", "s")
        first = make_cards([case], [], seed="private-seed-a", methods=())[0]
        second = make_cards([case], [], seed="private-seed-b", methods=())[0]
        self.assertNotEqual(first[0]["card_id"], second[0]["card_id"])

    def test_missing_run_blocks_but_recorded_failures_remain(self):
        case = {"case_id": "c1", "subject_id": "s", "candidate_ids": sample("c1", "s")["candidate_ids"]}
        frozen = {"cases": [{**case, "input_sha256": "frozen-hash"}]}
        run = {"case_id": "c1", "subject_id": "s", "method": "B1_direct", "status": "FAILED",
               "input_sha256": "frozen-hash"}
        with patch("research.problem_reidentification.experiment_c0.pilot.METHODS", ("B1_direct", "B4_critic")):
            with self.assertRaises(AuditBlocked) as caught:
                check_runs([case], [run], frozen)
            self.assertEqual(caught.exception.status, "BLOCKED_MISSING_PRIVATE_DATA")
            second = {**run, "method": "B4_critic", "status": "INVALID_OUTPUT"}
            counts = check_runs([case], [run, second], frozen)
            self.assertEqual(counts["B1_direct"], {"FAILED": 1})
            self.assertEqual(counts["B4_critic"], {"INVALID_OUTPUT": 1})

    def test_changed_run_input_hash_blocks(self):
        case = {"case_id": "c1", "subject_id": "s", "candidate_ids": []}
        frozen = {"cases": [{**case, "input_sha256": "original"}]}
        run = {**case, "method": "B1_direct", "status": "FAILED", "input_sha256": "changed"}
        with self.assertRaises(AuditBlocked) as caught:
            check_runs([case], [run], frozen)
        self.assertEqual(caught.exception.status, "BLOCKED_FREEZE_MISMATCH")

    def test_frozen_payload_mismatch_blocks(self):
        from research.problem_reidentification.experiment_b0.core import digest
        cases = [{"case_id": "fixture-case-" + str(i), "subject_id": "fixture-subject-" + str(i),
                  "block": 0, "candidate_ids": EXPECTED_CANDIDATES, "days": [None] * 42} for i in range(16)]
        packets = {c["case_id"]: {"fixture": 1} for c in cases}
        frozen = {"files": {}, "upstream_pins_sha256": "pin", "p1_release_id": "fixture-release",
                  "cases": [{k: c[k] for k in ("case_id", "subject_id", "block", "candidate_ids")} |
                            {"input_sha256": digest(packets[c["case_id"]])} for c in cases]}
        frozen["id"] = digest(frozen)
        with patch("research.problem_reidentification.experiment_c0.pilot.file_sha", return_value="pin"):
            check_freeze(frozen, cases, "fixture-release", packets)
            packets[cases[0]["case_id"]] = {"fixture": 2}
            with self.assertRaises(AuditBlocked) as caught:
                check_freeze(frozen, cases, "fixture-release", packets)
            self.assertEqual(caught.exception.status, "BLOCKED_FREEZE_MISMATCH")

    def test_private_output_cannot_escape_local_or_overwrite(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("research.problem_reidentification.experiment_c0.pilot.ROOT", root):
                with self.assertRaises(ValueError):
                    prepare_local(root / "public")
                (root / "local/version1").mkdir(parents=True)
                with self.assertRaises(FileExistsError):
                    prepare_local(root / "local/version1")

    def test_public_aggregation_fails_closed_on_no_gold(self):
        doc = {"status": "COMPLETE_EXPLORATORY_EXECUTION", "planned_records": 200,
               "record_count": 200, "human_gold": False, "decision_accuracy": None,
               "panels": {"main": {}}, "candidate_order_intervention": {}}
        for m in ("B1_direct", "B2_re2_style", "B3_self_refine", "B4_critic", "BM_critic", "S4_relative"):
            doc["panels"]["main"][m] = {"planned_windows": 16, "completed_records": 16,
                "status_counts": {"EXECUTED": 12, "FAILED": 4}, "valid_output_windows": 12,
                "all_candidates_tied_windows": 0}
            doc["candidate_order_intervention"][m] = {"same_priority_order": 0,
                "valid_paired_windows": 4, "same_pair_relations": 22, "pair_denominator": 40}
        report = public_audit(doc)
        self.assertEqual(report["total_valid_method_windows"], 72)
        self.assertIsNone(report["verified_chain_failures"])
        doc["human_gold"] = True
        with self.assertRaises(ValueError):
            public_audit(doc)


if __name__ == "__main__":
    unittest.main()
