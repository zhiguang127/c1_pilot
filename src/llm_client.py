"""Qwen API-only model boundary; Codex execution is deliberately unsupported."""
from api_llm_client import LLMError, call_model as api_call_model
from io_utils import ROOT, read_json


def call_model(prompt, schema, model, task_id, config=None, validate_result=None):
    config = config or read_json(ROOT / "config/experiment.json")["llm"]
    if config.get("backend") != "openai_compatible":
        raise LLMError("Only the authorized OpenAI-compatible API backend is supported")
    return api_call_model(prompt, schema, model, task_id, config, validate_result)


def object_schema(properties):
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}
