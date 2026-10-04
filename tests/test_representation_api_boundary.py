"""Offline regressions for batch validation before API cache writes."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import api_llm_client as api
import generate_representations as representations

FAKE_KEY = "fake-boundary-test-credential-only"
CONFIG = {"revision": "offline-boundary-test", "representation_output_tokens": 256,
          "seed": 20261003, "llm": {"backend": "openai_compatible", "generator_model": "test-qwen",
          "base_url": "https://example.invalid/compatible-mode/v1", "max_tokens": 1000,
          "temperature": 0, "max_workers": 1, "max_attempts": 3, "timeout_seconds": 1,
          "enable_thinking": False}}
BATCH = [{"case_id": "C001", "case_ref": "sample_a", "input": {"measured_values": [1, 2]},
          "input_sha256": "hash_a", "input_tokens": 12},
         {"case_id": "C002", "case_ref": "sample_b", "input": {"measured_values": [3, 4]},
          "input_sha256": "hash_b", "input_tokens": 12}]


def answer(baseline="B1"):
    return {"representations": [{"case_ref": row["case_ref"], **(
        {"queries": ["sleep baseline", "sleep timing", "activity baseline", "wear coverage", "heart rate recording"]}
        if baseline == "B3" else {"text": "Measured longitudinal changes."})} for row in BATCH]}


def response(result, finish="stop"):
    body = {"model": "test-qwen", "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": json.dumps(result)}}]}
    mocked = Mock(status_code=200, headers={}, text=json.dumps(body))
    mocked.json.return_value = body
    return mocked


class RepresentationAPIBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(api, "ROOT", self.root)
        self.root_patch.start()
        self.environment_patch = patch.dict(os.environ, {api.API_KEY_ENV: FAKE_KEY})
        self.environment_patch.start()
        self.sleep_patch = patch.object(api.time, "sleep")
        self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.environment_patch.stop()
        self.root_patch.stop()
        self.directory.cleanup()

    def cache_directory(self, baseline="B1"):
        return self.root / "outputs/llm_calls/representations/offline-boundary-test/strong-baselines-v1" / baseline / "repeat_1/batch_001"

    def run_batch(self, baseline="B1"):
        return representations._run_batch(baseline, 1, 1, deepcopy(BATCH), deepcopy(CONFIG))

    def test_exact_references_reject_missing_duplicate_unknown_and_extra_rows(self):
        complete = answer()
        invalid = [deepcopy(complete) for _ in range(4)]
        invalid[0]["representations"].pop()
        invalid[1]["representations"][1]["case_ref"] = "sample_a"
        invalid[2]["representations"][1]["case_ref"] = "unknown_sample"
        invalid[3]["representations"].append(deepcopy(complete["representations"][0]))
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(api.LLMError):
                representations._validate_batch_response(result, BATCH, "B1")

    def test_whitespace_summary_and_query_slots_rejected(self):
        for baseline in ("B1", "B2", "B3"):
            invalid = answer(baseline)
            if baseline == "B3":
                invalid["representations"][0]["queries"][2] = " \n\t"
            else:
                invalid["representations"][0]["text"] = " \n\t"
            with self.subTest(baseline=baseline), self.assertRaises(api.LLMError):
                representations._validate_batch_response(invalid, BATCH, baseline)

    def test_invalid_reference_output_is_not_cached_before_retry(self):
        invalid = answer()
        invalid["representations"][1]["case_ref"] = "sample_a"
        calls = 0

        def post(*args, **kwargs):
            nonlocal calls
            calls += 1
            self.assertFalse((self.cache_directory() / "result.json").exists())
            return response(invalid if calls == 1 else answer())

        with patch.object(api.requests, "post", side_effect=post):
            records = self.run_batch()
        self.assertEqual(2, calls)
        self.assertEqual({"C001", "C002"}, {record["case_id"] for record in records})
        self.assertTrue(all(record["metadata"]["attempt"] == 2 for record in records))
        cached = json.loads((self.cache_directory() / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(answer(), cached)

    def test_all_empty_outputs_fail_bounded_without_a_success_cache(self):
        invalid = answer("B3")
        invalid["representations"][1]["queries"][0] = ""
        with patch.object(api.requests, "post", return_value=response(invalid)) as post:
            with self.assertRaises(api.LLMError):
                self.run_batch("B3")
        self.assertEqual(3, post.call_count)
        self.assertFalse((self.cache_directory("B3") / "result.json").exists())
        self.assertFalse((self.cache_directory("B3") / "metadata.json").exists())
        failures = json.loads((self.cache_directory("B3") / "failures.json").read_text(encoding="utf-8"))
        self.assertEqual(3, len(failures))

    def test_complete_b3_batch_is_validated_on_cache_reuse(self):
        with patch.object(api.requests, "post", return_value=response(answer("B3"))) as post:
            records = self.run_batch("B3")
            cached_records = self.run_batch("B3")
        self.assertEqual(1, post.call_count)
        self.assertEqual(records, cached_records)
        self.assertTrue(all(len(record["queries"]) == 5 for record in records))

    def test_provider_truncation_is_rejected_even_with_parseable_json(self):
        with patch.object(api.requests, "post", return_value=response(answer(), finish="length")) as post:
            with self.assertRaises(api.LLMError):
                self.run_batch()
        self.assertEqual(3, post.call_count)
        self.assertFalse((self.cache_directory() / "result.json").exists())

    def test_cached_result_cannot_bypass_new_semantic_validation(self):
        schema = api.object_schema({"value": {"type": "string"}})
        with patch.object(api.requests, "post", return_value=response({"value": "unresolved"})) as post:
            api.call_model("fresh test", schema, "test-qwen", "semantic-cache", CONFIG["llm"])

            def reject(result):
                raise api.LLMError("unresolved semantic result")

            with self.assertRaisesRegex(api.LLMError, "Cached API output failed validation"):
                api.call_model("fresh test", schema, "test-qwen", "semantic-cache", CONFIG["llm"], validate_result=reject)
        self.assertEqual(1, post.call_count)


if __name__ == "__main__":
    unittest.main()
