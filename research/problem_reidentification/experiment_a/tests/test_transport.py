"""Synthetic SDK test doubles verify accounting; never counted as baseline inference."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.problem_reidentification.experiment_a.src.common import LOCAL, read, write
from research.problem_reidentification.experiment_a.src.transport import BASE_URL, MODEL, BudgetExceeded, GovernedCalls

try:
    from openai import OpenAI
    from openai.resources.chat.completions import Completions
    from openai.types.chat import ChatCompletion
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@unittest.skipUnless(HAS_OPENAI, "Transport integration needs the isolated pha or trialgpt environment")
class TransportTest(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(exist_ok=True, parents=True)
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.directory = Path(self.temp.name)
        self.dispatched = []

    def tearDown(self):
        self.temp.cleanup()

    def fake_sdk(self, resource, **kwargs):
        self.dispatched.append(kwargs)
        return ChatCompletion.model_validate({"id": "SOFTWARE_FIXTURE_NO_NETWORK", "created": 0,
            "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"fixture":true}'}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}})

    def test_cache_budget_and_redaction(self):
        test_key = "SOFTWARE_FIXTURE_NOT_A_REAL_CREDENTIAL"
        client = OpenAI(api_key=test_key, base_url=BASE_URL)
        owner = self
        def create(resource, **kwargs):
            return owner.fake_sdk(resource, **kwargs)
        with patch.object(Completions, "create", new=create):
            with GovernedCalls(self.directory, max_calls=1, max_output_tokens=128) as calls:
                opts = {"model": MODEL, "messages": [{"role": "user", "content": "SOFTWARE_FIXTURE"}]}
                client.chat.completions.create(**opts)
                client.chat.completions.create(**opts)
                with self.assertRaises(BudgetExceeded):
                    client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "DIFFERENT_SOFTWARE_FIXTURE"}])
            self.assertEqual(calls.summary()["llm_calls"], 1)
            self.assertEqual(calls.summary()["cached_calls"], 1)
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(client.max_retries, 0)
        self.assertEqual(self.dispatched[0]["max_tokens"], 128)
        for path in self.directory.rglob("*.json"):
            self.assertNotIn(test_key, path.read_text(encoding="utf-8"))

    def test_endpoint_and_input_caps(self):
        client = OpenAI(api_key="SOFTWARE_FIXTURE", base_url="https://example.invalid/v1")
        with GovernedCalls(self.directory, max_calls=1, max_input_chars=20):
            with self.assertRaises(ValueError):
                client.chat.completions.create(model=MODEL, messages=[])
            client = OpenAI(api_key="SOFTWARE_FIXTURE", base_url=BASE_URL)
            with self.assertRaises(BudgetExceeded):
                client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "long software-only fixture"}])
        self.assertFalse((self.directory / "ledger.json").exists())

    def test_real_sdk_http_boundary_blocks_unmetered_responses(self):
        import httpx
        dispatched = []
        def handler(request):
            dispatched.append(str(request.url))
            return httpx.Response(200, json={"id": "SOFTWARE_ONLY", "created": 0, "object": "chat.completion", "model": MODEL,
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "SOFTWARE_ONLY"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        sdk = OpenAI(api_key="SOFTWARE_ONLY", base_url=BASE_URL,
                     http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with GovernedCalls(self.directory, max_calls=1) as calls:
            if hasattr(sdk, "responses"):
                with self.assertRaisesRegex(ValueError, "Ungoverned"):
                    sdk.responses.create(model=MODEL, input="SOFTWARE_ONLY")
            result = sdk.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": "SOFTWARE_ONLY"}])
            self.assertEqual(result.choices[0].message.content, "SOFTWARE_ONLY")
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(calls.summary()["llm_calls"], 1)

    def test_exact_cache_reused_across_run_versions(self):
        client = OpenAI(api_key="SOFTWARE_FIXTURE", base_url=BASE_URL)
        owner = self
        def create(resource, **kwargs):
            return owner.fake_sdk(resource, **kwargs)
        shared = self.directory / "shared"
        with patch.object(Completions, "create", new=create):
            with GovernedCalls(self.directory / "version1", max_calls=1, shared_cache=shared):
                client.chat.completions.create(model=MODEL, messages=[])
            with GovernedCalls(self.directory / "version2", max_calls=0, shared_cache=shared) as resumed:
                client.chat.completions.create(model=MODEL, messages=[])
        self.assertEqual(len(self.dispatched), 1)
        self.assertEqual(resumed.summary()["cached_calls"], 1)
        self.assertEqual(resumed.summary()["llm_calls"], 0)

    def test_cache_tampering_is_rejected(self):
        client = OpenAI(api_key="SOFTWARE_FIXTURE", base_url=BASE_URL)
        owner = self
        def create(resource, **kwargs):
            return owner.fake_sdk(resource, **kwargs)
        with patch.object(Completions, "create", new=create):
            with GovernedCalls(self.directory, max_calls=1):
                client.chat.completions.create(model=MODEL, messages=[])
            path = next((self.directory / "calls").glob("*.json"))
            record = read(path)
            record["response"]["model"] = "CHANGED_FIXTURE"
            write(path, record, overwrite=True)
            with GovernedCalls(self.directory, max_calls=1):
                with self.assertRaises(ValueError):
                    client.chat.completions.create(model=MODEL, messages=[])
        self.assertEqual(len(self.dispatched), 1)


if __name__ == "__main__":
    unittest.main()
