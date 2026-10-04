"""Report-boundary tests without model calls or experimental labels."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from assess_hypothesis import synthesis_case


class ResearchSynthesisTests(unittest.TestCase):
    def test_unwraps_nested_representation_records_and_excludes_raw_control(self):
        case = {
            "case_id": "C001",
            "semantic_audit": {"audit_kind": "PROVISIONAL_LLM_AUDIT"},
            "retrieval": [{"baseline_id": "B4"}],
            "gold_relevance": {"K001": 2},
            "baseline_outputs": [{"representation": {"baseline_id": baseline, "text": baseline},
                                  "lexical_token_count": 1, "retention_probes": []}
                                 for baseline in ("B1", "B2", "B3", "B4")],
        }
        result = synthesis_case(case)
        self.assertEqual([row["baseline_id"] for row in result["baseline_outputs"]], ["B1", "B2", "B3"])
        self.assertEqual(result["retrieval"], case["retrieval"])
        self.assertEqual(result["provisional_gold"], case["gold_relevance"])


if __name__ == "__main__":
    unittest.main()
