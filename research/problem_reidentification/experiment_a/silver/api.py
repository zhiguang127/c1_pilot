"""Separate, persistent, pessimistically reserved Qwen-Max budget and private cache."""
import contextlib
import json
import os
import time
from pathlib import Path

from ..src.common import LOCAL, digest, now, private_path, read, write

MODEL = "qwen-max"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
SILVER = LOCAL / "silver_annotations" / "v1"
PRICE = {"input_per_million_cny": 2.4, "output_per_million_cny": 9.6,
         "cached_input_per_million_cny": .48,
         "source": "https://help.aliyun.com/zh/model-studio/qwen-max",
         "checked_on": "2026-10-18", "region": "Beijing", "invoice_verified": False,
         "documented_alias_equivalence": "qwen-max-2025-01-25",
         "alias_is_immutable": False}


class IncompleteOutput(ValueError):
    pass


class MalformedOutput(ValueError):
    pass


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def estimate(messages, max_tokens):
    # Qwen's proprietary tokenizer/version is not asserted to be locally known.
    # A UTF-8 byte ceiling plus generous chat framing is conservative for byte BPE.
    upper = sum(len(m["content"].encode("utf-8")) + 128 for m in messages) + 256
    if upper > 30720 or upper + max_tokens > 32768:
        raise ValueError("Conservative context ceiling exceeded; never truncate personal input")
    return {"input_token_ceiling": upper, "output_token_ceiling": max_tokens,
            "reserved_cny": (upper * 2.4 + max_tokens * 9.6) / 1_000_000,
            "basis": "UTF8 bytes plus chat framing; conservative estimate, not actual tokenizer count"}


def request_options(messages, max_tokens, schema=None):
    request = {"model": MODEL, "messages": messages, "temperature": 0,
               "max_tokens": max_tokens, "response_format": {"type": "json_object"}, "stream": False}
    estimated_messages=messages
    if schema is not None:
        request.pop('response_format')
        request['tools']=[{'type':'function','function':{'name':'record_silver_audit',
             'description':'Return the complete structured Silver audit. This declarative record function is never executed.',
             'parameters':schema}}]
        request['tool_choice']={'type':'function','function':{'name':'record_silver_audit'}}
        estimated_messages=messages+[{'role':'system','content':packed({'tools':request['tools'],'tool_choice':request['tool_choice']})}]
    return request, estimate(estimated_messages,max_tokens)


@contextlib.contextmanager
def locked(path):
    """OS lock prevents concurrent processes from each spending the same balance."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0"); f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)


class SilverClient:
    def __init__(self, root=SILVER):
        self.root = private_path(root)
        if not self.root.is_relative_to((LOCAL / "silver_annotations").resolve()):
            raise ValueError("Silver artifacts must stay in their own private directory")

    def initialize(self, *, cap_cny=5., max_calls=48, batch_authorized=False):
        if cap_cny <= 0 or max_calls < 1:
            raise ValueError("Positive monetary and request caps required")
        with locked(self.root / "budget.lock"):
            p = self.root / "budget.json"
            if p.exists():
                b = read(p)
                if (b["cap_cny"], b["max_calls"], b["batch_authorized"]) != (cap_cny, max_calls, batch_authorized):
                    raise ValueError("Existing budget is immutable; explicit authorization revision required")
                return b
            b = {"label_provenance": "QWEN_MAX_SILVER", "model": MODEL, "price": PRICE,
                 "cap_cny": cap_cny, "max_calls": max_calls, "batch_authorized": batch_authorized,
                 "scope": "Source audit, one-case double smoke, blinded 30-prediction audit; held-out batch requires explicit authorization",
                 "attempts": [], "created_at": now()}
            write(p, b)
            return b

    def authorize_batch(self, *, cap_cny, max_calls, authorization_note):
        if not authorization_note.strip():
            raise ValueError("Record actual user budget authorization")
        with locked(self.root / "budget.lock"):
            b = read(self.root / "budget.json")
            write(self.root / "authorizations" / (str(len(list((self.root / 'authorizations').glob('*.json')))) + ".json"),
                  {"previous_budget": b, "at": now(), "authorization_note": authorization_note})
            if cap_cny < b["cap_cny"] or max_calls < len(b["attempts"]):
                raise ValueError("Invalid revised budget")
            b.update(cap_cny=cap_cny, max_calls=max_calls, batch_authorized=True,
                     authorization_note=authorization_note)
            write(self.root / "budget.json", b, overwrite=True)

    def call(self, messages, *, tag, max_tokens=4096, schema=None, retry_invalid_once=False):
        try:
            return self._call(messages,tag=tag,max_tokens=max_tokens,schema=schema)
        except (json.JSONDecodeError,IncompleteOutput,MalformedOutput):
            if not retry_invalid_once:
                raise
            request,_=request_options(messages,max_tokens,schema)
            key=digest(request);cache=self.root/'cache'/(key+'.json')
            with locked(self.root/'budget.lock'):
                retries_path=self.root/'format_retries.json'
                retries=read(retries_path) if retries_path.exists() else {}
                if key in retries or not cache.exists():
                    raise
                response=read(cache)
                # Keep the Windows path below MAX_PATH; full hashes remain in
                # the immutable archived record and retry registry.
                archive=self.root/'malformed_cache'/(key[:16]+'-'+response['response_sha256'][:16]+'.json')
                archive.parent.mkdir(parents=True,exist_ok=True)
                assert cache.resolve().is_relative_to(self.root) and archive.resolve().is_relative_to(self.root)
                cache.rename(archive)
                retries[key]={'at':now(),'reason':'Malformed/truncated declarative output only; exact same request, no previous labels supplied',
                              'archived_response_sha256':response['response_sha256'],'tag':tag}
                write(retries_path,retries,overwrite=True)
            result,meta=self._call(messages,tag=tag+':format-retry',max_tokens=max_tokens,schema=schema)
            return result,{**meta,'explicit_format_retry_from_sha256':response['response_sha256']}

    def _call(self, messages, *, tag, max_tokens=4096, schema=None):
        from openai import OpenAI
        request,limits = request_options(messages,max_tokens,schema)
        key = digest(request)
        cache = self.root / "cache" / (key + ".json")
        if cache.exists():
            c = read(cache)
            if c["request_sha256"] != key or digest(c["response"]) != c["response_sha256"]:
                raise ValueError("Silver cache integrity mismatch")
            return self.decode(c["response"]), {"cache_hit": True, "request_sha256": key, **c["metadata"]}
        if not os.environ.get("C1_PILOT_API_KEY"):
            raise ValueError("Secure wrapper credential required")
        with locked(self.root / "budget.lock"):
            b = read(self.root / "budget.json")
            used = sum(a.get("charged_estimate_cny", a["reserved_cny"]) for a in b["attempts"])
            if len(b["attempts"]) >= b["max_calls"] or used + limits["reserved_cny"] > b["cap_cny"]:
                raise ValueError("Persistent Silver monetary/request ceiling reached")
            index = len(b["attempts"])
            b["attempts"].append({"tag": tag, "request_sha256": key, "at": now(), **limits,
                                  "status": "RESERVED_OR_UNCERTAIN", "model_requested": MODEL})
            write(self.root / "budget.json", b, overwrite=True)
        write(self.root / "requests" / f"{index:04d}-{key}.json", request)
        start = time.monotonic()
        try:
            # No baseline governor, fallback model, thinking parameter or hidden retry.
            sdk = OpenAI(api_key=os.environ["C1_PILOT_API_KEY"], base_url=BASE_URL, max_retries=0, timeout=180)
            response = sdk.chat.completions.create(**request)
            body = response.model_dump(mode="json")
            usage = body.get("usage") or {}
            n_in, n_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            price = None if n_in is None or n_out is None else (n_in*2.4+n_out*9.6)/1_000_000
            discounted = None if price is None else ((n_in-cached)*2.4+cached*.48+n_out*9.6)/1_000_000
            meta = {"returned_model": body.get("model"), "system_fingerprint": body.get("system_fingerprint"),
                    "response_id": body.get("id"), "server_created": body.get("created"), "usage": usage,
                    "finish_reason": body["choices"][0]["finish_reason"], "duration_seconds": time.monotonic()-start,
                    "estimated_cny_no_discount": price, "estimated_cny_reported_cache": discounted,
                    "api_sdk_version": __import__('importlib.metadata', fromlist=['version']).version('openai'),
                    "actual_invoice_cny": None}
            write(cache, {"request_sha256": key, "response_sha256": digest(body), "response": body, "metadata": meta})
            with locked(self.root / "budget.lock"):
                b = read(self.root / "budget.json")
                b["attempts"][index].update(status="RESPONSE_RECEIVED", metadata=meta)
                if price is not None:
                    b["attempts"][index]["charged_estimate_cny"] = max(price, discounted or 0)
                write(self.root / "budget.json", b, overwrite=True)
            return self.decode(body), {"cache_hit": False, "request_sha256": key, **meta}
        except Exception as exc:
            with locked(self.root / "budget.lock"):
                b = read(self.root / "budget.json")
                b["attempts"][index].update(error_type=type(exc).__name__, http_status=getattr(exc, 'status_code', None))
                write(self.root / "budget.json", b, overwrite=True)
            raise

    @staticmethod
    def decode(body):
        choice=body['choices'][0]
        if choice['finish_reason']=='tool_calls':
            calls=choice['message'].get('tool_calls') or []
            if len(calls)!=1 or calls[0]['function']['name']!='record_silver_audit':
                raise MalformedOutput('Unexpected declarative audit function')
            return json.loads(calls[0]['function']['arguments'])
        if choice["finish_reason"] != "stop":
            raise IncompleteOutput("Incomplete Silver output retained privately, never treated as a label")
        return json.loads(body["choices"][0]["message"]["content"])
