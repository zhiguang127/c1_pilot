"""Actual OneTwo/SDK integration with a local HTTP fixture; no research prediction."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.problem_reidentification.experiment_a.src.common import LOCAL

try:
    import httpx
    from openai import OpenAI
    from onetwo.backends import openai_api
    from onetwo.core import content as content_lib
    HAS_PHA_DEPS = True
except ImportError:
    HAS_PHA_DEPS = False


@unittest.skipUnless(HAS_PHA_DEPS, "Requires the isolated PHA environment")
class OneTwoBoundaryTest(unittest.TestCase):
    def test_real_p1_frames_execute_with_empty_optional_tables(self):
        import contextlib
        import io
        from research.problem_reidentification.experiment_a.src.data import candidates
        from research.problem_reidentification.experiment_a.src.pha import modules, personal_frames
        modules()
        from pha.tools.python_sandbox import PythonSandbox, PhdaPythonRequest
        cases, _, _ = candidates()
        frames = personal_frames(cases[0])
        self.assertEqual(len(frames["activities"]), 0)
        self.assertEqual(len(frames["population"]), 0)
        sb = PythonSandbox({"summary_df": frames["summary"], "activities_df": frames["activities"],
                            "profile_df": frames["profile"], "population_df": frames["population"]})
        with contextlib.redirect_stdout(io.StringIO()):
            result = sb.execute(PhdaPythonRequest(request='def analysis(summary_df, activities_df, profile_df, population_df):\n    return len(summary_df)'))
        self.assertEqual(result.execution_result.status.value, "success")
        self.assertIn("42", result.execution_result.output)

    def test_onetwo_provider_bridge_is_metered_and_cached(self):
        from research.problem_reidentification.experiment_a.src.pha import modules, governed_onetwo
        from research.problem_reidentification.experiment_a.src.transport import GovernedCalls, MODEL, BASE_URL
        modules()
        LOCAL.mkdir(exist_ok=True, parents=True)
        with tempfile.TemporaryDirectory(dir=LOCAL) as temp:
            requests = []
            def handler(request):
                requests.append(str(request.url))
                return httpx.Response(200, json={"id": "SOFTWARE_ONLY", "created": 0, "object": "chat.completion", "model": MODEL,
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "SOFTWARE_ONLY"}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}})
            backend = openai_api.OpenAIAPI(api_key="SOFTWARE_ONLY", model_name=MODEL)
            backend._client = OpenAI(api_key="SOFTWARE_ONLY", base_url=BASE_URL,
                                     http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            messages = [content_lib.Message(content="SOFTWARE_ONLY", role=content_lib.PredefinedRole.USER)]
            with GovernedCalls(Path(temp), max_calls=1), governed_onetwo():
                self.assertEqual(backend._responses_create(messages=messages).output_text, "SOFTWARE_ONLY")
                self.assertEqual(backend._responses_create(messages=messages).output_text, "SOFTWARE_ONLY")
            self.assertEqual(len(requests), 1)
            self.assertTrue(requests[0].endswith("/chat/completions"))

    def test_controlled_entry_initializes_official_module_path(self):
        from research.problem_reidentification.experiment_a.src.pha import controlled_response
        # No LLM output or human declaration generated here. Only entry-context
        # initialization is exercised; the deliberate exception precedes a model.
        with patch('research.problem_reidentification.experiment_a.src.pha.personal_frames', return_value={}), \
             patch('research.problem_reidentification.experiment_a.src.pha.architecture', side_effect=RuntimeError("SOFTWARE_SENTINEL")):
            with self.assertRaisesRegex(RuntimeError, "SOFTWARE_SENTINEL"):
                controlled_response("phia", {"days": [], "context": {}}, [], "SOFTWARE_ONLY", [])
