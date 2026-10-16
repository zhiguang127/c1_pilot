"""Artificial human declarations for SOFTWARE VALIDATION ONLY; never study labels."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.problem_reidentification.experiment_a.src import annotation, common


class ArtificialImportTest(unittest.TestCase):
    def setUp(self):
        common.LOCAL.mkdir(exist_ok=True, parents=True)
        self.temp = tempfile.TemporaryDirectory(dir=common.LOCAL)
        self.root = Path(self.temp.name)
        self.case = {"case_id": "SOFTWARE_ONLY_CASE", "subject_id": "SOFTWARE_ONLY_SUBJECT", "candidate_ids": ["SOFTWARE_K"],
                     "context": {"symptoms": None}, "quality_notes": ["SOFTWARE_ONLY"],
                     "days": [{"day": 29, "metrics": {"sleep_minutes": 400}}]}
        self.knowledge = {"SOFTWARE_K": {"id": "SOFTWARE_K", "title": "SOFTWARE_ONLY", "content": "SOFTWARE_ONLY",
            "source_url": "https://example.invalid/software-only", "source": "SOFTWARE_ONLY", "source_locator": "SOFTWARE_ONLY",
            "applicability": {"observable_conditions": ["SOFTWARE_ONLY condition"]}}}
        self.source = patch.object(annotation, "candidates", return_value=([self.case], self.knowledge, "SOFTWARE_ONLY_RELEASE"))
        self.source.start()
        annotation.packets("a1", None, self.root / "packets")
        roster = {"reviewers": [{"reviewer_id": r, "person_id": "SOFTWARE_PERSON_"+r,
            "role": "adjudicator" if r == "C" else "reviewer", "is_human": True,
            "qualified": True, "background": "SOFTWARE_TEST_DECLARATION_ONLY", "independence_attested": True} for r in ("A", "B", "C")]}
        common.write(self.root / "roster.json", roster)

    def tearDown(self):
        self.source.stop()
        self.temp.cleanup()

    def record(self, reviewer, label="insufficient_information", timestamp="2026-01-02T00:00:00+00:00"):
        record = common.rows(self.root / "packets" / ("A" if reviewer == "C" else reviewer) / "annotations.template.jsonl")[0]
        record.update(reviewer_id=reviewer, status="complete", human_attestation=True, completed_at=timestamp)
        ref = record["items"][0]["candidate_ref"]
        record["items"][0].update(topic_relevance="related", applicability=label,
            observations=[] if label == "insufficient_information" else ["d29.sleep_minutes"],
            conditions=[ref+".observable_conditions.0"], missing_information=["SOFTWARE_ONLY missing symptom"],
            rationale="SOFTWARE_FIXTURE_ONLY", condition_judgments=[{"condition_id": ref+".observable_conditions.0",
                "status": "unknown", "observations": [], "rationale": "SOFTWARE_FIXTURE_ONLY"}])
        if reviewer == "C":
            record["reviewed_reviewers"] = ["A", "B"]
        return record

    def save(self, name, record):
        common.write_rows(self.root / name, [record])
        return self.root / name

    def invoke(self, left, right, adjudication=None):
        return annotation.import_gold("a1", None, self.root / "packets", self.root / "roster.json",
            self.save("A.jsonl", left), self.save("B.jsonl", right),
            self.save("C.jsonl", adjudication) if adjudication else None, self.root / "gold")

    def test_independent_software_declarations_resolve_only_applicability(self):
        report = self.invoke(self.record("A"), self.record("B"))
        self.assertEqual(report["resolved_pairs"], 1)
        self.assertEqual(report["status"], "ANNOTATED")
        self.assertFalse(report["priority_labels_imported"])
        common.verify(self.root / "gold")

    def test_draft_template_is_not_gold(self):
        left = self.record("A")
        left["human_attestation"] = False
        with self.assertRaises(ValueError):
            self.invoke(left, self.record("B"))

    def test_stale_adjudication_rejected(self):
        c = self.record("C", timestamp="2026-01-01T00:00:00+00:00")
        with self.assertRaises(ValueError):
            self.invoke(self.record("A"), self.record("B", "not_applicable"), c)

    def test_source_dispute_stays_unresolved(self):
        left, right = self.record("A"), self.record("B")
        left["items"][0]["source_scope_disputed"] = True
        right["items"][0]["source_scope_disputed"] = True
        report = self.invoke(left, right)
        self.assertEqual(report["resolved_pairs"], 0)
        self.assertEqual(report["status"], "PENDING_HUMAN_ANNOTATION")
