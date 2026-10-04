"""Input blinding, output budget and deterministic-facts checks; no model calls."""

from pathlib import Path
from copy import deepcopy
import contextlib
import io
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import tiktoken

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from case_statistics import model_input
from generate_cases import generate_cases
from generate_representations import _batch_is_finished, enforce_budget, generate_representations, make_prompt, raw_statistical_facts, response_schema
from io_utils import read_jsonl, write_json, write_jsonl
from llm_client import LLMError
from retrieval import representation_queries


class RepresentationProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = generate_cases()
        cls.encoder = tiktoken.get_encoding("cl100k_base")

    def test_summary_and_insight_token_budget(self):
        for baseline in ("B1", "B2"):
            text, queries, metadata = enforce_budget("Measured sleep and activity. " * 400, [], baseline, 256)
            self.assertLessEqual(len(self.encoder.encode(text)), 256)
            self.assertTrue(metadata["truncated"])
            self.assertEqual([], queries)
            self.assertGreater(metadata["pre_enforcement_tokens"], metadata["output_tokens"])

    def test_five_query_slots_share_one_budget(self):
        text, queries, metadata = enforce_budget("", ["a brief query"] + ["Longitudinal wearable change. " * 90] * 4, "B3", 256)
        self.assertEqual(5, len(queries))
        self.assertEqual("a brief query", queries[0])
        self.assertTrue(all(query for query in queries))
        self.assertLessEqual(len(self.encoder.encode(text)), 256)
        self.assertTrue(metadata["truncated"])
        with self.assertRaises(ValueError):
            enforce_budget("", ["one"], "B3", 256)

    def test_prompt_blinding_and_shared_data(self):
        view = model_input(self.cases[20])
        batch = [{"case_ref": "sample_opaque", "input": view}]
        for baseline in ("B1", "B2", "B3"):
            prompt = make_prompt(baseline, batch)
            self.assertNotIn("C021", prompt)
            self.assertNotIn("designer_notes", prompt)
            self.assertNotIn("case_type", prompt)
            self.assertNotIn("matched_group", prompt)
            self.assertIn('"observations"', prompt)
            self.assertIn('"derived_statistics"', prompt)
        inputs = [make_prompt(baseline, batch).split("INPUT_RECORDS_JSON:\n")[1] for baseline in ("B1", "B2", "B3")]
        self.assertEqual(inputs[0], inputs[1])
        self.assertEqual(inputs[1], inputs[2])

    def test_deterministic_facts_preserve_missingness_and_temporal_structure(self):
        c008 = raw_statistical_facts(model_input(self.cases[7]))
        self.assertIn("null", c008)
        self.assertIn("insufficient_coverage", c008)
        c016 = raw_statistical_facts(model_input(self.cases[15]))
        c018 = raw_statistical_facts(model_input(self.cases[17]))
        self.assertNotEqual(c016, c018)
        self.assertIn("150,160,170", c016)
        self.assertIn("15,15,15", c018)
        self.assertIn("t+1", raw_statistical_facts(model_input(self.cases[20])))
        for forbidden in ("sleep_debt", "circadian_disruption", "recommended_action", "knowledge_ids"):
            self.assertNotIn(forbidden, c016)
        self.assertEqual(c016, raw_statistical_facts(model_input(self.cases[15])))

    def test_response_schema_requires_exactly_five_queries(self):
        from jsonschema import Draft7Validator
        validator = Draft7Validator(response_schema("B3"))
        validator.validate({"representations": [{"case_ref": "sample", "queries": ["a", "b", "c", "d", "e"]}]})
        self.assertTrue(list(validator.iter_errors({"representations": [{"case_ref": "sample", "queries": ["a"]}]})))

    def test_failed_metadata_status_produces_empty_retrieval_input(self):
        for baseline in ("B1", "B2", "B3", "B4"):
            record = {"case_id": "C001", "baseline_id": baseline, "text": "",
                      "queries": [""] * 5 if baseline == "B3" else [], "metadata": {"status": "failed"}}
            self.assertEqual([], representation_queries(record))
        valid = {"case_id": "C001", "baseline_id": "B3", "queries": ["one", "two", "three", "four", "five"],
                 "metadata": {"status": "completed"}}
        self.assertEqual(valid["queries"], representation_queries(valid))

    def test_only_explicit_terminal_statuses_skip_a_batch(self):
        batch = [{"case_id": "C001"}]
        for status in ("failed", "running", "pending", None):
            records = {("C001", "B1", 1): {"metadata": {"status": status}}}
            self.assertFalse(_batch_is_finished(records, batch, "B1", 1))
        for status in ("completed", "empty_output"):
            records = {("C001", "B1", 1): {"metadata": {"status": status}}}
            self.assertTrue(_batch_is_finished(records, batch, "B1", 1))
        self.assertFalse(_batch_is_finished({}, batch, "B1", 1))

    def test_resume_retries_failed_batch_without_changing_successful_outputs(self):
        config = {"revision": "resume-test", "seed": 20261003, "repeats": 1,
                  "representation_batch_size": 4, "representation_output_tokens": 256,
                  "llm": {"generator_model": "test-model", "max_workers": 3}}
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            directory = Path(temporary)
            config_path, input_path, output_path = directory / "config.json", directory / "cases.jsonl", directory / "representations.jsonl"
            write_json(config_path, config)
            write_jsonl(input_path, self.cases)

            def successful_batch(baseline, repeat, batch_number, batch, supplied_config):
                return [{"case_id": entry["case_id"], "baseline_id": baseline, "repeat_id": repeat,
                         "text": "one\ntwo\nthree\nfour\nfive", "queries": ["one", "two", "three", "four", "five"],
                         "input_sha256": entry["input_sha256"], "output_tokens": 9,
                         "metadata": {"status": "completed", "configuration_revision": supplied_config["revision"],
                                      "test_batch": batch_number}}
                        for entry in batch]

            def first_attempt(*args):
                if args[2] == 2:
                    raise LLMError("test unavailable backend")
                return successful_batch(*args)

            with contextlib.redirect_stdout(io.StringIO()), patch("generate_representations._run_batch", side_effect=first_attempt) as called:
                with self.assertRaises(LLMError):
                    generate_representations(config_path, input_path, output_path, ["B3"], [1])
                self.assertEqual(6, called.call_count)
            first_records = read_jsonl(output_path)
            first_successes = {record["case_id"]: deepcopy(record) for record in first_records if record["metadata"]["status"] == "completed"}
            self.assertEqual(20, len(first_successes))
            self.assertEqual(4, sum(record["metadata"]["status"] == "failed" for record in first_records))
            with contextlib.redirect_stdout(io.StringIO()), patch("generate_representations._run_batch", side_effect=successful_batch) as called:
                completed = generate_representations(config_path, input_path, output_path, ["B3"], [1])
                self.assertEqual(1, called.call_count)
                self.assertEqual(2, called.call_args.args[2])
            self.assertEqual(24, len(completed))
            self.assertTrue(all(record["metadata"]["status"] == "completed" for record in completed))
            for record in completed:
                if record["case_id"] in first_successes:
                    self.assertEqual(first_successes[record["case_id"]], record)
            with contextlib.redirect_stdout(io.StringIO()), patch("generate_representations._run_batch") as called:
                generate_representations(config_path, input_path, output_path, ["B3"], [1])
                called.assert_not_called()


if __name__ == "__main__":
    unittest.main()
