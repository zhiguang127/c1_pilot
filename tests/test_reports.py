"""Report token accounting separates experimental scope from recorded budget."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_reports


class ReportAccountingTests(unittest.TestCase):
    def test_actual_qwen_metadata_totals_exclude_archives_and_codex(self):
        root = Path("calls")
        files = [root / "active/metadata.json", root / "archive/metadata.json",
                 root / "codex/metadata.json", root / "unknown/metadata.json"]
        records = {str(files[0]): {"backend": "openai_compatible_chat_completions", "model": "qwen3.8-max",
                                   "provider_model": "returned-qwen", "task_id": "representations/execution-qwen-v1/B1",
                                   "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
                   str(files[1]): {"backend": "openai_compatible_chat_completions", "model": "qwen3.8-max", "usage": {"prompt_tokens": 900}},
                   str(files[2]): {"backend": "codex_exec", "model": "gpt-6.1-sol", "usage": {"input_tokens": 500}},
                   str(files[3]): {"backend": "openai_compatible_chat_completions", "model": "qwen3.8-max",
                                   "task_id": "execution-qwen-v1/judge_a_C001", "usage": {}}}
        experiment = {"revision": "execution-qwen-v1", "llm": {"base_url": "https://example.org/v1",
                      **{role + "_model": "qwen3.8-max" for role in ("generator", "judge_a", "judge_b", "adjudicator", "audit")}}}
        with patch.object(Path, "rglob", return_value=files), patch.object(build_reports, "read_json", side_effect=lambda path: records[str(path)]):
            result = build_reports.qwen_usage_totals(root, experiment)
        self.assertEqual(result["totals"]["prompt_tokens"], 100)
        self.assertEqual(result["totals"]["completion_tokens"], 20)
        self.assertEqual(result["totals"]["total_tokens"], 120)
        self.assertEqual(result["totals"]["successful_call_metadata_count"], 2)
        self.assertEqual(result["skipped_archive_metadata"], 1)
        self.assertEqual(result["skipped_non_qwen_metadata"], 1)
        self.assertEqual(result["unknown_usage_call_ids"], ["execution-qwen-v1/judge_a_C001"])
        self.assertEqual(result["included_calls"][0]["returned_model"], "returned-qwen")

    def test_budget_preserves_superseded_and_rejected_response_usage(self):
        root = Path("calls")
        tasks = {
            "current": "execution-qwen-v1/blinded-annotation-v2-shortrefs/judge_a_C001",
            "old_judge": "execution-qwen-v1/judge_b_C001",
            "old_practice": "execution-qwen-v1/judge_a_P001",
            "old_adjudicator": "execution-qwen-v1/adjudicator_C001",
            "practice": "execution-qwen-v1/calibration/practice_case",
            "rejected_cached_response": "execution-qwen-v1/judge_a_C002",
            "representations": "representations/execution-qwen-v1/B1_C001_r1",
            "source": "source-review/execution-qwen-v1/source_001",
        }
        files = [root / name / "metadata.json" for name in tasks]
        records = {
            str(path): {
                "backend": "openai_compatible_chat_completions",
                "model": "qwen3.8-max",
                "task_id": tasks[path.parent.name],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            }
            for path in files
        }
        experiment = {
            "revision": "execution-qwen-v1",
            "llm": {"base_url": "https://example.org/v1", **{
                role + "_model": "qwen3.8-max"
                for role in ("generator", "judge_a", "judge_b", "adjudicator", "audit")
            }},
        }
        with patch.object(Path, "rglob", return_value=files), patch.object(
            build_reports, "read_json", side_effect=lambda path: records[str(path)]
        ):
            result = build_reports.qwen_usage_totals(root, experiment)

        self.assertEqual(result["totals"], {
            "successful_call_metadata_count": 8,
            "prompt_tokens": 80, "completion_tokens": 16, "total_tokens": 96,
        })
        expected_counts = {
            "current_stage_calls": 3,
            "superseded_annotation": 4,
            "rejected_model_attempt": 1,
        }
        for scope, count in expected_counts.items():
            self.assertEqual(result["by_scope"][scope], {
                "successful_call_metadata_count": count,
                "prompt_tokens": count * 10,
                "completion_tokens": count * 2,
                "total_tokens": count * 12,
            })
        scopes = {call["task_id"]: call["scope"] for call in result["included_calls"]}
        self.assertEqual(scopes[tasks["current"]], "current_stage_calls")
        self.assertEqual(scopes[tasks["rejected_cached_response"]], "rejected_model_attempt")
        self.assertEqual(scopes[tasks["source"]], "current_stage_calls")
        self.assertIn("Cumulative recorded", result["coverage"])


if __name__ == "__main__":
    unittest.main()
