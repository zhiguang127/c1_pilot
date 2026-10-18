"""Bounded transport and exact-request caches for real official-code execution."""
import contextlib
import json
import os
import threading
import time
from urllib.parse import urlparse

from .common import LOCAL, REPO, digest, now, private_path, read, write

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.8-max"


class BudgetExceeded(RuntimeError):
    pass


class GovernedCalls:
    """Transport-only instrumentation: no simulated LLM results or tool actions.

    A persistent per-run ledger counts attempted new requests before dispatch.
    Failed requests also consume the budget. Cached responses are content hashed.
    Request/response bodies remain private. Never store HTTP auth headers.
    """
    def __init__(self, directory, *, max_calls=12, max_output_tokens=2048, max_input_chars=250000, shared_cache=None):
        self.directory = private_path(directory)
        self.cache_directory = private_path(shared_cache) if shared_cache else self.directory / "calls"
        self.max_calls, self.max_output_tokens = max_calls, max_output_tokens
        self.max_input_chars = max_input_chars
        self.events = []
        self.lock = threading.RLock()
        self.request_locks = {}
        self.ledger = self.directory / "ledger.json"
        self.attempts = read(self.ledger)["attempts"] if self.ledger.exists() else 0

    def install(self):
        from openai import OpenAI
        from openai.resources.chat.completions import Completions
        old = Completions.create
        old_request = OpenAI.request
        owner = self
        def guarded_request(sdk_client, cast_to, options, *args, **kwargs):
            # Defense in depth: new SDK routes (Responses, parse, embeddings)
            # must not silently bypass cache, budget, token or endpoint checks.
            if str(options.url) != "/chat/completions" or not getattr(owner.dispatch, "active", False):
                raise ValueError("Ungoverned SDK network route refused")
            return old_request(sdk_client, cast_to, options, *args, **kwargs)
        def create(resource, *args, **kwargs):
            # No credential or unrestricted endpoint can enter an experiment trace.
            actual_url = str(resource._client.base_url).rstrip("/")
            if actual_url != BASE_URL:
                raise ValueError("Only the authorized DashScope endpoint is permitted")
            if args or kwargs.get("stream"):
                raise ValueError("Audited nonstreaming keyword-only requests required")
            kwargs["model"] = MODEL
            kwargs["max_tokens"] = min(kwargs.pop("max_completion_tokens", kwargs.get("max_tokens", owner.max_output_tokens)), owner.max_output_tokens)
            kwargs["temperature"] = 0
            kwargs["extra_body"] = {**kwargs.get("extra_body", {}), "enable_thinking": False}
            serialized = json.dumps(kwargs, ensure_ascii=False, default=str)
            if len(serialized) > owner.max_input_chars:
                raise BudgetExceeded("Input context cap exceeded; input was NOT truncated")
            key = digest(kwargs)
            target = owner.cache_directory / (key + ".json")
            from openai.types.chat import ChatCompletion
            with owner.lock:
                request_lock = owner.request_locks.setdefault(key, threading.RLock())
            with request_lock:
                if target.exists():
                    cached = read(target)
                    if cached["request_sha256"] != key or cached["response_sha256"] != digest(cached["response"]):
                        raise ValueError("Cached response integrity mismatch")
                    event = {"cache_hit": True, "request_sha256": key, "duration_seconds": 0,
                             "usage": cached["response"].get("usage"), "model": cached["response"].get("model")}
                    with owner.lock:
                        owner.events.append(event)
                        write(owner.directory / "events.json", owner.events, overwrite=True)
                    return ChatCompletion.model_validate(cached["response"])
                with owner.lock:
                    if owner.attempts >= owner.max_calls:
                        raise BudgetExceeded("Persistent API call budget exhausted")
                    owner.attempts += 1
                    attempt = owner.attempts
                    write(owner.ledger, {"attempts": owner.attempts, "max_calls": owner.max_calls}, overwrite=True)
                started = time.monotonic()
                write(owner.directory / "requests" / (key + f"-attempt-{attempt}.json"), kwargs)
                try:
                    resource._client.max_retries = 0
                    resource._client.timeout = 120
                    owner.dispatch.active = True
                    try:
                        response = old(resource, **kwargs)
                    finally:
                        owner.dispatch.active = False
                    body = response.model_dump(mode="json")
                    event = {"cache_hit": False, "request_sha256": key, "at": now(),
                             "duration_seconds": time.monotonic()-started, "usage": body.get("usage"),
                             "model": body.get("model"), "request_id": body.get("id"),
                             "finish_reason": body["choices"][0].get("finish_reason"),
                             "max_output_tokens": kwargs["max_tokens"], "input_characters": len(serialized)}
                    write(target, {"request_sha256": key, "response_sha256": digest(body), "response": body, "event": event})
                    with owner.lock:
                        owner.events.append(event)
                        write(owner.directory / "events.json", owner.events, overwrite=True)
                    return response
                except Exception as exc:
                    # Error class only: provider/SDK messages can contain private request content.
                    with owner.lock:
                        safe_reason = str(exc).replace(str(resource._client.api_key), "[REDACTED]")
                        owner.events.append({"request_sha256": key, "error_type": type(exc).__name__, "at": now(),
                                             "http_status": getattr(exc, "status_code", None),
                                             "provider_code": getattr(exc, "code", None), "reason": safe_reason,
                                             "duration_seconds": time.monotonic()-started})
                        write(owner.directory / "events.json", owner.events, overwrite=True)
                    raise
        Completions.create = create
        self._class, self._old = Completions, old
        self.dispatch = threading.local()
        self._sdk, self._old_request = OpenAI, old_request
        OpenAI.request = guarded_request
        return self

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self._class.create = self._old
        self._sdk.request = self._old_request

    def summary(self):
        usage = [e.get("usage") or {} for e in self.events if not e.get("cache_hit")]
        return {"llm_calls": sum(not e.get("cache_hit", False) for e in self.events),
                "cached_calls": sum(e.get("cache_hit", False) for e in self.events),
                "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
                "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
                "api_cost": None, "cost_note": "Provider billing/rate unavailable; not inferred from token count",
                "returned_models": sorted({e["model"] for e in self.events if e.get("model")}),
                "max_calls": self.max_calls, "max_output_tokens": self.max_output_tokens,
                "failed_calls": sum("error_type" in e for e in self.events), "at": now()}


def client():
    from openai import OpenAI
    key = os.environ.get("C1_PILOT_API_KEY")
    if not key:
        raise ValueError("Use environment or the local secure credential wrapper")
    return OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=120)


def complete(messages, *, json_mode=True):
    options = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = client().chat.completions.create(model=MODEL, messages=messages, temperature=0, **options)
    return response.choices[0].message.content, response.choices[0].finish_reason
