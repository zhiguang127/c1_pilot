"""Mocked API behavior only. The credential in this test is deliberately fake."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import api_llm_client as client

FAKE_KEY = "fake-pilot-test-credential-only"
CONFIG = {"base_url": "https://example.invalid/compatible-mode/v1/", "max_tokens": 8000,
          "temperature": 0, "timeout_seconds": 60, "max_attempts": 3, "max_workers": 2}
SCHEMA = client.object_schema({"value": {"type": "string"}})


def response(value="ok", status=200, content=None, finish="stop", tools=None, error=None):
    body = {"id": "test-request", "model": "qwen-test", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content if content is not None else json.dumps({"value": value})}}]}
    if tools is not None:
        body["choices"][0]["message"]["tool_calls"] = tools
    if error:
        body = {"error": error}
    result = Mock(status_code=status, text=json.dumps(body), headers={"x-request-id": "http-test-request"})
    result.json.return_value = body
    return result


class APIClientTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root_patch = patch.object(client, "ROOT", Path(self.directory.name))
        self.root_patch.start()
        self.environment_patch = patch.dict(os.environ, {client.API_KEY_ENV: FAKE_KEY})
        self.environment_patch.start()
        self.sleep_patch = patch.object(client.time, "sleep")
        self.sleep_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.environment_patch.stop()
        self.root_patch.stop()
        self.directory.cleanup()

    def call(self, task="task", **kwargs):
        return client.call_model("Fresh data prompt", SCHEMA, "qwen-test", task, kwargs.pop("config", CONFIG), **kwargs)

    def assert_no_credential_in_artifacts(self):
        for file in Path(self.directory.name).rglob("*"):
            if file.is_file():
                self.assertNotIn(FAKE_KEY, file.read_text(encoding="utf-8"))

    def test_fresh_tool_free_payload_url_and_cache(self):
        with patch.object(client.requests, "post", return_value=response()) as post:
            result, metadata = self.call()
            self.assertEqual({"value": "ok"}, result)
            url = post.call_args.args[0]
            kwargs = post.call_args.kwargs
            self.assertEqual("https://example.invalid/compatible-mode/v1/chat/completions", url)
            self.assertEqual("Bearer " + FAKE_KEY, kwargs["headers"]["Authorization"])
            self.assertEqual(["system", "user"], [message["role"] for message in kwargs["json"]["messages"]])
            self.assertEqual({"type": "json_object"}, kwargs["json"]["response_format"])
            self.assertNotIn("tools", kwargs["json"])
            self.assertNotIn("seed", kwargs["json"])
            self.assertEqual(0, kwargs["json"]["temperature"])
            self.assertEqual(8000, kwargs["json"]["max_tokens"])
            self.assertTrue(metadata["fresh_context"])
            self.assertEqual("http-test-request", metadata["http_request_id"])
            self.assertEqual(0, metadata["tool_calls"])
            self.assertEqual((result, metadata), self.call())
            self.assertEqual(1, post.call_count)
        self.assert_no_credential_in_artifacts()

    def test_bad_json_schema_and_callback_retry(self):
        invalid = response(content="not JSON")
        bad_schema = response(content='{"value":1}')
        with patch.object(client.requests, "post", side_effect=[invalid, bad_schema, response("valid")]) as post:
            result, metadata = self.call()
            self.assertEqual(3, post.call_count)
            self.assertEqual({"value": "valid"}, result)
            self.assertEqual(2, len(metadata["prior_failures"]))

        def callback(result):
            if result["value"] != "accepted":
                raise ValueError("Unresolved annotation")

        with patch.object(client.requests, "post", side_effect=[response("unresolved"), response("accepted")]) as post:
            result, metadata = self.call("semantic", validate_result=callback)
            self.assertEqual("accepted", result["value"])
            self.assertEqual(2, post.call_count)

    def test_authentication_rate_and_credit_errors_stop_immediately_and_redact(self):
        for status, code in ((401, "InvalidApiKey"), (403, "access_denied"), (429, "RateLimit"), (402, "InsufficientBalance"), (200, "InsufficientQuota")):
            with self.subTest(status=status):
                fake = response(status=status, error={"code": code, "message": "Request refused: " + FAKE_KEY})
                with patch.object(client.requests, "post", return_value=fake) as post:
                    with self.assertRaises(client.LLMTerminalError) as error:
                        self.call("error_" + str(status))
                    self.assertNotIn(FAKE_KEY, str(error.exception))
                    self.assertEqual(1, post.call_count)
                self.assert_no_credential_in_artifacts()

    def test_tool_calls_and_nonstop_output_are_rejected(self):
        for name, invalid in (("tools", response(tools=[{"id": "call", "type": "function"}])),
                              ("truncated", response(finish="length"))):
            with self.subTest(name=name), patch.object(client.requests, "post", side_effect=[invalid, response()]) as post:
                _, metadata = self.call(name)
                self.assertEqual(2, post.call_count)
                self.assertEqual(2, metadata["attempt"])

    def test_runtime_failures_are_bounded_and_redacted(self):
        with patch.object(client.requests, "post", side_effect=client.requests.Timeout("Timeout " + FAKE_KEY)) as post:
            with self.assertRaises(client.LLMError) as error:
                self.call()
            self.assertEqual(3, post.call_count)
            self.assertNotIn(FAKE_KEY, str(error.exception))
        self.assert_no_credential_in_artifacts()

    def test_seed_only_if_configured_and_cache_changed_config_rejected(self):
        config = {**CONFIG, "provider_seed_supported": True, "sampling_seed": 17, "enable_thinking": False}
        with patch.object(client.requests, "post", return_value=response()) as post:
            self.call(config=config)
            self.assertEqual(17, post.call_args.kwargs["json"]["seed"])
            self.assertIs(False, post.call_args.kwargs["json"]["enable_thinking"])
            with self.assertRaises(client.LLMError):
                self.call(config={**config, "max_tokens": 9000})
            self.assertEqual(1, post.call_count)

    def test_environment_only_key_and_missing_key(self):
        with patch.object(client.requests, "post") as post:
            with self.assertRaises(client.LLMError):
                self.call(config={**CONFIG, "api_key": FAKE_KEY})
            with patch.dict(os.environ, {client.API_KEY_ENV: ""}):
                with self.assertRaises(client.LLMTerminalError):
                    self.call()
            post.assert_not_called()

    def test_global_and_configured_worker_bound(self):
        lock = threading.Lock()
        active, maximum = 0, 0
        release = threading.Event()

        def slow_post(*args, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                if active == 2:
                    release.set()
            release.wait(timeout=1)
            with lock:
                active -= 1
            return response()

        with patch.object(client.requests, "post", side_effect=slow_post), ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda index: self.call("parallel_" + str(index)), range(6)))
        self.assertEqual(6, len(results))
        self.assertEqual(2, maximum)


if __name__ == "__main__":
    unittest.main()
