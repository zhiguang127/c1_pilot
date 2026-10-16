"""Fabricated software fixtures ONLY. Never research cases or human labels."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from research.problem_reidentification.p1 import annotations as ann
from research.problem_reidentification.p1 import dataset as ds
from research.problem_reidentification.p1.packets import generate_packets, verify_packets
from research.problem_reidentification.p1.download_pmdata import download


def fixture_case():
    return {"case_id": "TEST-ONLY-CASE", "subject_id": "TEST-ONLY-SUBJECT", "candidate_ids": ["K006", "K017", "K041"],
            "context": {"population": "TEST ADULT", "symptoms": None}, "quality_notes": ["TEST FIXTURE ONLY"],
            "days": [{"day": i + 1, "weekday": (i % 7) + 1, "phase": "baseline" if i < 28 else "current",
                      "metrics": {k: (400 if k == "sleep_minutes" else None) for k in ds.METRICS},
                      "quality_flags": []} for i in range(42)]}


def fixture_knowledge():
    return {kid: {"knowledge_id": kid, "title": "TEST ONLY", "content": "TEST ONLY", "source": "TEST ONLY",
                  "source_url": "https://example.org/test-only", "source_locator": "TEST ONLY", "source_accessed_on": "2026-10-16",
                  "source_review": "TEST ONLY", "support_anchors": ["TEST ONLY"],
                  "applicability": {"population": ["TEST ADULT"], "observable_conditions": ["TEST ONLY"]}}
            for kid in fixture_case()["candidate_ids"]}


def fixture_record(mapping=None, reviewer="A", mode="tie", release_id="TEST"):
    mapping = mapping or {"C1": "K006", "C2": "K017", "C3": "K041"}
    refs = sorted(mapping)
    ev = {"observations": ["d29.sleep_minutes"], "conditions": [refs[0] + ".observable_conditions.0"],
          "rationale": "FABRICATED TEST LABEL ONLY", "missing_information": []}
    record = {"release_id": release_id, "reviewer_id": reviewer, "case_ref": "CASE-001", "status": "complete",
              "human_attestation": True, "completed_at": "2026-10-16T12:00:00-04:00",
              "items": [{**deepcopy(ev), "candidate_ref": r, "applicability": "applicable",
                         "conditions": [r + ".observable_conditions.0"]} for r in refs], "comparisons": [],
              "decision": {**deepcopy(ev), "reason_codes": ["reasonable_tie"], "priority": "none",
                           "top_outcome": "tied_best", "best_set": refs}}
    for i, left in enumerate(refs):
        for right in refs[i + 1:]:
            record["comparisons"].append({**deepcopy(ev), "left": left, "right": right,
                "conditions": [left + ".observable_conditions.0", right + ".observable_conditions.0"],
                "relation": "tie"})
    if mode == "unique":
        for p in record["comparisons"]: p["relation"] = "left_preferred"
        record["decision"].update(priority="clear", top_outcome="unique_best", best_set=[refs[0]])
    if mode == "incomparable":
        for p in record["comparisons"]: p["relation"] = "incomparable"
        record["decision"].update(top_outcome="undetermined", best_set=[])
    if mode == "insufficient":
        for p in record["comparisons"]:
            p.update(relation="insufficient_information", missing_information=["goals"])
        record["decision"].update(priority="insufficient_information", top_outcome="insufficient_information", best_set=[], missing_information=["goals"])
    if reviewer == "C": record["reviewed_reviewers"] = ["A", "B"]
    return record


def fixture_release(path):
    path.mkdir()
    ds.write_jsonl(path / "cases.jsonl", [fixture_case()])
    ds.write_jsonl(path / "knowledge.jsonl", fixture_knowledge().values())
    ds.write_json(path / "sampling_plan.json", {"randomization_seed": "TEST ONLY"})
    ds.write_json(path / "import_audit.json", {"status": "PREPARED_NOT_ANNOTATED", "participant_count": 1})
    (path / "P1_ANNOTATION_GUIDE.md").write_text("TEST ONLY GUIDE", encoding="utf-8")
    hashes = {p.name: ds.sha(p) for p in path.iterdir()}
    ds.write_json(path / "freeze.json", {"files": hashes, "release_id": ds.digest(hashes)})


def fixture_roster():
    return {"reviewers": [{"reviewer_id": r, "person_id": "TEST-ONLY-" + r,
                           "role": "adjudicator" if r == "C" else "reviewer", "is_human": True,
                           "qualified": True, "background": "FABRICATED TEST ONLY", "independence_attested": True}
                          for r in ("A", "B", "C")]}


class ImportTest(unittest.TestCase):
    def test_pmdata_nested_daily_metric_preserves_zero_and_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rhr.json"
            ds.write_json(path, [{"dateTime": "2019-11-01 00:00:00", "value": {"value": 0}},
                                 {"dateTime": "2019-11-02 00:00:00", "value": None}])
            result = ds.daily_metric(path, resting=True)
            self.assertEqual(0, result[date(2019, 11, 1)])
            self.assertIsNone(result[date(2019, 11, 2)])
    def test_duplicate_daily_metric_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.json"
            row = {"dateTime": "2019-11-01 00:00:00", "value": "10"}
            ds.write_json(path, [row, row])
            with self.assertRaisesRegex(ValueError, "Duplicate"): ds.daily_metric(path)
    def test_invalid_numeric_values_are_not_silently_coerced(self):
        for x in (True, "NaN", "inf", -1, 1441):
            with self.subTest(x=x), self.assertRaises(ValueError): ds.number(x, 1440)
    def test_main_sleep_repeated_projection_and_conflict(self):
        row = {"mainSleep": True, "logId": 1, "dateOfSleep": "2019-11-02",
               "startTime": "2019-11-01 23:00:00", "endTime": "2019-11-02T07:00:00.000",
               "minutesAsleep": 400, "timeInBed": 480, "unselected_field": "v1"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sleep.json"
            second = {**row, "unselected_field": "v2"}
            ds.write_json(path, [row, second, {**row, "mainSleep": False}])
            result = ds.sleep_metric(path)[date(2019, 11, 2)]
            self.assertEqual(400, result["sleep_minutes"])
            self.assertEqual(-1, result["sleep_start_day_offset"])
            self.assertIn("repeated_identical_selected_sleep_fields", result["sleep_quality_flags"])
            ds.write_json(path, [row, {**row, "minutesAsleep": 410}])
            result = ds.sleep_metric(path)[date(2019, 11, 2)]
            self.assertNotIn("sleep_minutes", result)
            self.assertEqual(["ambiguous_main_sleep_all_sleep_fields_withheld"], result["sleep_quality_flags"])
    def test_fixed_windows_and_pseudonymization_no_pattern_selection(self):
        plan = ds.read_json(ds.ROOT / "sampling_plan.json")
        start = date.fromisoformat(plan["study_start"])
        daily = {start + timedelta(days=i): {"sleep_minutes": 400 if i % 2 else 600} for i in range(126)}
        cases, exclusions, mapping = ds.construct_cases({"p01": daily}, plan, b"a" * 32)
        self.assertEqual(3, len(cases)); self.assertEqual([], exclusions)
        self.assertEqual(3, len({x["start_date"] for x in mapping}))
        self.assertEqual(1, len({c["subject_id"] for c in cases}))
        self.assertTrue(all(len(c["days"]) == 42 and c["days"][28]["phase"] == "current" for c in cases))
        public = json.dumps(cases)
        self.assertNotIn("p01", public); self.assertNotIn("2019-11-01", public)
        other, _, _ = ds.construct_cases({"p01": daily}, plan, b"b" * 32)
        self.assertNotEqual(cases[0]["case_id"], other[0]["case_id"])
        # A technically empty window is excluded rather than filled.
        cases, exclusions, _ = ds.construct_cases({"p01": {}}, plan, b"a" * 32)
        self.assertEqual([], cases); self.assertEqual(3, len(exclusions))
    def test_real_import_refuses_missing_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds.write_json(Path(tmp) / "source_manifest.json", {"real_records": False})
            with self.assertRaisesRegex(ValueError, "provenance"):
                ds.prepare(tmp, Path(tmp) / "release")
    def test_zero_rhr_and_sleep_status_are_visible_quality_flags(self):
        plan = ds.read_json(ds.ROOT / "sampling_plan.json")
        start = date.fromisoformat(plan["study_start"])
        daily = {start + timedelta(days=i): {"resting_heart_rate_bpm": 0, "sleep_info_code": 2} for i in range(42)}
        cases, _, _ = ds.construct_cases({"p01": daily}, plan, b"a" * 32)
        self.assertEqual(0, cases[0]["days"][0]["metrics"]["resting_heart_rate_bpm"])
        self.assertIn("zero_rhr_source_value_not_valid_for_health_interpretation", cases[0]["days"][0]["quality_flags"])
        self.assertIn("nonzero_sleep_info_code_raw_device_quality_unknown", cases[0]["days"][0]["quality_flags"])
    def test_completed_download_preserves_manifest_and_checks_cached_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "test-only.json"; path.write_text("[]", encoding="utf-8")
            manifest = root / "source_manifest.json"
            ds.write_json(manifest, {"files": [{"path": path.name, "status": "downloaded", "sha256": ds.sha(path)}]})
            before = manifest.read_bytes(); download(root); self.assertEqual(before, manifest.read_bytes())
            path.write_text("[0]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"): download(root)


class AnnotationTest(unittest.TestCase):
    def validate(self, record):
        return ann.validate_record(record, fixture_case(), {"C1": "K006", "C2": "K017", "C3": "K041"}, fixture_knowledge(), "TEST", record["reviewer_id"])
    def test_tie_unique_incomparable_and_information_insufficient_valid(self):
        for mode in ("tie", "unique", "incomparable", "insufficient"):
            with self.subTest(mode=mode): self.validate(fixture_record(mode=mode))
    def test_partial_order_can_still_have_unique_best(self):
        record = fixture_record(mode="unique")
        record["comparisons"][2]["relation"] = "incomparable"
        record["decision"]["priority"] = "partial"
        self.validate(record)
    def test_missing_applicability_prevents_claim_of_unique_best(self):
        record = fixture_record(mode="unique")
        record["items"][2].update(applicability="insufficient_information", missing_information=["goals"])
        record["comparisons"] = record["comparisons"][:1]
        with self.assertRaisesRegex(ValueError, "Best-set"): self.validate(record)
        record["decision"].update(top_outcome="insufficient_information", best_set=[], missing_information=["goals"])
        self.validate(record)
    def test_single_applicable_candidate_is_not_unique_p1_winner(self):
        record = fixture_record()
        for item in record["items"][1:]: item["applicability"] = "not_applicable"
        record["comparisons"] = []
        record["decision"].update(priority="not_comparable", top_outcome="not_comparable", best_set=[])
        self.validate(record)
        record["decision"].update(top_outcome="unique_best", best_set=["C1"])
        with self.assertRaisesRegex(ValueError, "Fewer"): self.validate(record)
    def test_reject_missing_pair_duplicate_item_cycle_and_tie_contradiction(self):
        record = fixture_record(); record["comparisons"].pop()
        with self.assertRaisesRegex(ValueError, "Every pair"): self.validate(record)
        record = fixture_record(); record["items"][1] = deepcopy(record["items"][0])
        with self.assertRaisesRegex(ValueError, "Each candidate"): self.validate(record)
        record = fixture_record(mode="unique"); record["comparisons"][1]["relation"] = "right_preferred"
        with self.assertRaisesRegex(ValueError, "Cyclic"): self.validate(record)
        record = fixture_record(); record["comparisons"][1]["relation"] = "left_preferred"
        with self.assertRaisesRegex(ValueError, "tied"): self.validate(record)
    def test_reject_unsupported_evidence_drafts_and_model_labels(self):
        record = fixture_record(); record["items"][0]["observations"] = ["d29.resting_heart_rate_bpm"]
        with self.assertRaisesRegex(ValueError, "observation"): self.validate(record)
        record = fixture_record(); record["status"] = "draft"
        with self.assertRaisesRegex(ValueError, "Draft"): self.validate(record)
        record = fixture_record(); record["human_attestation"] = False
        with self.assertRaisesRegex(ValueError, "non-human"): self.validate(record)
        record = fixture_record(); record["items"][0]["conditions"] = ["C2.observable_conditions.0"]
        with self.assertRaisesRegex(ValueError, "condition"): self.validate(record)
    def test_canonical_comparison_aligns_different_randomized_references(self):
        mapping = {"C3": "K006", "C2": "K017", "C1": "K041"}
        record = fixture_record(mapping, mode="unique")
        result = ann.normalize(record, "TEST", mapping)
        self.assertEqual("right_preferred", result["pairs"]["K006|K041"])
        self.assertEqual(["K041"], result["best_set"])
    def test_human_roster_requires_three_different_people_and_expertise(self):
        roster = fixture_roster(); ann.validate_roster(roster)
        roster["reviewers"][2]["person_id"] = roster["reviewers"][0]["person_id"]
        with self.assertRaisesRegex(ValueError, "different"): ann.validate_roster(roster)
    def test_known_kappa_and_degenerate_kappa(self):
        self.assertEqual(0, ann.agreement(["a", "a", "b", "b"], ["a", "b", "a", "b"])["cohens_kappa"])
        self.assertIsNone(ann.agreement(["a"], ["a"])["cohens_kappa"])
        self.assertIsNone(ann.agreement([], [])["exact_agreement"])


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.release = self.root / "release"; fixture_release(self.release)
        self.packets = self.root / "packets"; generate_packets(self.release, self.packets)
        self.assignment = verify_packets(self.release, self.packets)
        self.roster = self.root / "roster.json"; ds.write_json(self.roster, fixture_roster())
    def tearDown(self): self.tmp.cleanup()
    def file(self, reviewer, mode):
        mapping = self.assignment["reviewers"]["A" if reviewer == "C" else reviewer]["CASE-001"]["candidates"]
        record = fixture_record(mapping, reviewer=reviewer, mode=mode, release_id=self.assignment["release_id"])
        path = self.root / (reviewer + ".jsonl"); ds.write_jsonl(path, [record]); return path
    def test_no_human_annotations_means_no_research_metrics(self):
        result = ann.analyze(self.release)
        self.assertEqual("PREPARED_NOT_ANNOTATED", result["status"])
        for field in ("agreement", "applicability", "priority", "top_outcome", "clearly_prioritized_case_proportion"):
            self.assertIsNone(result[field])
    def test_blind_cards_do_not_expose_canonical_ids_or_subject(self):
        for r in ("A", "B"):
            card = (self.packets / r / "CASE-001.html").read_text(encoding="utf-8")
            for secret in ("TEST-ONLY-CASE", "TEST-ONLY-SUBJECT", "K006", "K017", "K041"):
                self.assertNotIn(secret, card)
            self.assertNotIn("assignments", card)
    def test_frozen_release_and_packet_changes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exists"): generate_packets(self.release, self.packets)
        card = self.packets / "A/CASE-001.html"; card.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"): verify_packets(self.release, self.packets)
        (self.release / "cases.jsonl").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"): ds.verify_release(self.release)
    def test_disagreement_needs_third_party_and_preserves_original_agreement(self):
        a, b = self.file("A", "tie"), self.file("B", "incomparable")
        result = ann.analyze(self.release, self.packets, self.roster, a, b)
        self.assertEqual("AWAITING_ADJUDICATION", result["status"])
        self.assertIsNone(result["top_outcome"])
        queue = self.root / "queue"
        ann.adjudication_queue(self.release, self.packets, self.roster, a, b, queue)
        self.assertEqual(1, len(ds.read_json(queue / "queue.json")))
        c = self.file("C", "insufficient")
        final = ann.analyze(self.release, self.packets, self.roster, a, b, c)
        self.assertEqual("ANNOTATED", final["status"])
        self.assertEqual(result["agreement"], final["agreement"])
        self.assertEqual(1, final["top_outcome"]["counts"]["insufficient_information"])
    def test_partial_annotations_do_not_become_final_distribution(self):
        a = self.file("A", "tie")
        result = ann.analyze(self.release, self.packets, self.roster, a=a)
        self.assertEqual("PARTIALLY_ANNOTATED", result["status"])
        self.assertEqual(0, result["paired_case_count"])
        self.assertIsNone(result["top_outcome"])
    def test_duplicate_case_and_unneeded_adjudication_rejected(self):
        a, b = self.file("A", "tie"), self.file("B", "tie")
        c = self.file("C", "tie")
        with self.assertRaisesRegex(ValueError, "genuine"): ann.analyze(self.release, self.packets, self.roster, a, b, c)
        a.write_text(a.read_text(encoding="utf-8") * 2, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"): ann.analyze(self.release, self.packets, self.roster, a, b)


if __name__ == "__main__": unittest.main()
