"""Run pinned baseline adapters. All decisions and feedback come from real calls."""
import argparse
import copy
import io
import itertools
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from .core import *
from . import prompts as P

METHODS = ["B1_direct", "B2_re2_style", "B3_self_refine", "B4_critic", "B5_rarr_explanation_only",
           "S3a_grounding", "S3b_claim", "S4_relative", "BM_self_refine", "BM_critic"]
UP = LOCAL / "upstream"


class Session:
    def __init__(self, tag):
        self.client = Client()
        self.tag = tag
        self.events = []
        self.tool_events = []

    def call(self, prompt, limit=2048, json_mode=False, stop=None, schema="full"):
        text, meta = self.client.call(prompt, tag=self.tag, limit=limit, json_mode=json_mode, stop=stop, schema=schema)
        self.events.append(meta)
        return text


def self_refine(session, packet, initial, matched=False):
    # Execute the official Prompt.make_query, with a task-specific feedback rubric.
    env = definitions(UP / "self_refine/src/utils.py", ["Prompt"], {})
    prompt = env["Prompt"]("Input: ", "Output: ", "\n", "\n\n")
    feedback = session.call(prompt.make_query(P.FEEDBACK, packed({"data": packet, "initial": initial})),
                            limit=3072 if matched else 1024, json_mode=True, schema="feedback")
    value = session.call(prompt.make_query(P.ITERATE, packed({"data": packet, "initial": initial, "feedback": decode(feedback)})),
                         limit=3072 if matched else 2048, json_mode=True)
    return decode(value), {"feedback": decode(feedback), "official_definition": "src/utils.py:Prompt.make_query"}


def critic(session, packet, initial, case, knowledge, constraint="", matched=False):
    logs = []
    args = SimpleNamespace(data="health_b0", critic_type="critic", model=MODEL,
                           max_interaction=3 if matched else 2, max_tokens=2048,
                           temperature=0, use_tool=True, evidence_length=1000000)
    step = 0
    def llm(**kwargs):
        nonlocal step
        step += 1
        schema = "query" if step == 1 else "full" if step == args.max_interaction else "feedback"
        result = session.call(kwargs["prompt"], limit=kwargs["max_tokens"], json_mode=True, schema=schema)
        value = decode(result)
        # Typed task interface maps the actual model's query/feedback/revision
        # into the author's existing text protocol without semantic fabrication.
        result = "> Search Query: " + value["query"] if schema == "query" else "most possible answer: " + result if schema == "full" else result
        return {"choices": [{"text": result}]}
    def query(q, topk=1):
        return tools(case, knowledge, q, session.tool_events)
    env = {"load_prompt": lambda *a: P.CRITIC + constraint + P.CONTRACT + "\nData: " + packed(packet) + "\n",
           "llm": llm, "google": query, "arg": args, "print": lambda *a, **kw: logs.append(" ".join(map(str, a)))}
    definitions(UP / "critic/src/qa/critic.py", ["critic_iter"], env)
    result = env["critic_iter"]({"question": "Prioritize these five optional health-education candidates."}, packed(initial), args)
    if not result:
        raise ValueError("Official CRITIC loop ended without final JSON; trajectory retained")
    return decode(result), {"official_definition": "src/qa/critic.py:critic_iter", "logs": logs,
                            "upstream_bug_shim": "Global arg aliases args for original tool-loop typo; function body unchanged"}


def rarr(session, packet, initial, case, knowledge):
    # Real author query generation, gate and editor; frozen evidence replaces web.
    def complete(**kwargs):
        # Five-item structured task output needs more than the original single-
        # sentence editor's 512-token cap. This is a declared task adaptation.
        cap = 2048 if kwargs["max_tokens"] == 512 else kwargs["max_tokens"]
        original_cap = kwargs["max_tokens"]
        schema = "items" if original_cap == 512 else "gate" if "logit_bias" in kwargs else "query"
        raw = session.call(kwargs["prompt"], limit=cap, json_mode=True, schema=schema)
        v = decode(raw)
        txt = "My edit follows the supplied evidence.\nMy fix: " + raw if schema == "items" else v["reason"] + "\nTherefore: The evidence " + ("agrees" if v["agrees"] else "disagrees") if schema == "gate" else "I googled: " + v["query"]
        return SimpleNamespace(choices=[SimpleNamespace(text=txt)])
    backend = SimpleNamespace(Completion=SimpleNamespace(create=complete), error=SimpleNamespace(OpenAIError=RuntimeError))
    env0 = {"List": List, "Dict": Dict, "Any": Any, "Tuple": Tuple, "openai": backend, "time": time}
    qgen = definitions(UP / "rarr/utils/question_generation.py", ["parse_api_response", "run_rarr_question_generation"], dict(env0))
    gate = definitions(UP / "rarr/utils/agreement_gate.py", ["parse_api_response", "run_agreement_gate"], dict(env0))
    editor = definitions(UP / "rarr/utils/editor.py", ["parse_api_response", "run_rarr_editor"], dict(env0))
    # Ranking/applicability are not exposed to the editor, so no accidental reranker.
    claim = packed({"items": [{"id": x["id"], "explanation": x["explanation"], "evidence": x["evidence"]} for x in initial["items"]]})
    queries = qgen["run_rarr_question_generation"](claim, MODEL, P.RARR_QUERY, 0, 1, num_retries=1)
    if len(queries) != 1:
        raise ValueError("RARR one-query budget contract failed; no extra calls")
    evidence = tools(case, knowledge, queries[0], session.tool_events)["page"]
    g = gate["run_agreement_gate"](claim, queries[0], evidence, MODEL, P.RARR_GATE, num_retries=1)
    edited = editor["run_rarr_editor"](claim, queries[0], evidence, MODEL, P.RARR_EDIT, num_retries=1)["text"] if g["is_open"] else claim
    replacement = decode(edited)["items"]
    if len(replacement) != len(initial["items"]) or {x["id"] for x in replacement} != set(case["candidate_ids"]):
        raise ValueError("RARR edited explanation set changed")
    output = copy.deepcopy(initial)
    mapping = {x["id"]: x for x in replacement}
    for x in output["items"]:
        for field in ("explanation", "evidence"):
            x[field] = mapping[x["id"]][field]
    # One complete evidence packet: coverage selection is degenerate. Author
    # select_evidences still runs; no replacement relevance model or hallucination.
    select = definitions(UP / "rarr/utils/evidence_selection.py", ["question_coverage_objective_fn", "select_evidences"],
                         {"Dict": Dict, "List": List, "Any": Any, "itertools": itertools,
                          "compute_score_matrix": lambda qs, es: [[1. for _ in es] for _ in qs]})
    attribution = select["select_evidences"]({"questions": queries, "revisions": [{"evidences": [{"text": evidence}]}]}, max_selected=1)
    return output, {"questions": queries, "gate": g, "edited_claim": edited,
                    "attribution_sha256": digest(attribution), "attribution_scope": "One exhaustive frozen packet; selection has no ranking choice; original CrossEncoder not used"}


def checkpoint(path, fn):
    if path.exists():
        return read(path)
    value = fn()
    write(path, value)
    return value


def run_case(case, knowledge, variant="main"):
    packet = payload(case, knowledge, reverse=(variant == "candidate_reverse"))
    out = LOCAL / "runs" / variant / case["case_id"]
    for method in METHODS:
        dest = out / (method + ".json")
        if dest.exists():
            continue
        s = Session(variant + ":" + case["case_id"] + ":" + method)
        details = {}
        try:
            if method == "B1_direct":
                fixed = decode(s.call(P.DIRECT + P.CONTRACT + packed(packet), limit=512, json_mode=True, schema="rank"))
                explanation = decode(s.call(P.POSTHOC + packed({"data": packet, "fixed": fixed}), json_mode=True, schema="items"))
                value = {**fixed, "items": explanation["items"], "pairwise_reasons": explanation.get("pairwise_reasons", [])}
                details["posthoc_raw"] = explanation
                details["initial_ranking"] = fixed
            elif method == "B2_re2_style":
                reason = decode(s.call(P.REASON + packed(packet), limit=1024, json_mode=True, schema="reason"))
                value = decode(s.call(P.RECOMMEND + packed({"data": packet, "preceding_reasoning": reason}), json_mode=True))
                details["preceding_reasoning"] = reason
            else:
                init_record = read(out / "B1_direct.json")
                if init_record["status"] != "EXECUTED":
                    raise ValueError("Frozen shared B1 initialization unavailable")
                initial = init_record["output"]
                details["initial_output_sha256"] = digest(initial)
                if method in ("B3_self_refine", "BM_self_refine"):
                    value, extra = self_refine(s, packet, initial, method.startswith("BM"))
                elif method == "B5_rarr_explanation_only":
                    value, extra = rarr(s, packet, initial, case, knowledge)
                else:
                    constraints = {"S3a_grounding": P.GROUND, "S3b_claim": P.GROUND + P.CLAIM,
                                   "S4_relative": P.GROUND + P.CLAIM + P.RELATIVE}
                    value, extra = critic(s, packet, initial, case, knowledge, constraints.get(method, ""),
                                          matched=method != "B4_critic")
                details.update(extra)
            errors = validate(value, case)
            record = {"status": "EXECUTED" if not errors else "INVALID_OUTPUT", "output": value,
                      "validation_errors": errors, "evidence_audit": evidence_audit(value, case) if not errors else None}
        except Exception as exc:
            record = {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)}
        record.update(method=method, case_id=case["case_id"], subject_id=case["subject_id"],
                      input_sha256=digest(packet), events=s.events, tool_events=s.tool_events, details=details, at=now())
        write(dest, record)
        print(variant, case["case_id"], method, record["status"], len(s.events), flush=True)


def freeze():
    cases, knowledge, release = selected()
    # Validate every input before any comparison call.
    for case in cases:
        payload(case, knowledge)
    files = [p for p in ROOT.glob("*.py")] + [ROOT / "configs/protocol.json"]
    p = ROOT / "configs/freeze.json"
    value = {"files": {x.relative_to(ROOT).as_posix(): sha(x) for x in files}, "p1_release_id": release,
             "cases": [{"case_id": c["case_id"], "subject_id": c["subject_id"], "block": c["block"],
                        "candidate_ids": c["candidate_ids"], "input_sha256": digest(payload(c, knowledge))} for c in cases],
             "upstream_pins_sha256": sha(ROOT / "results/upstream_pins.json"), "human_gold": False,
             "selection": "All 16 participants, minimum block per participant; no prediction or Silver access", "at": now()}
    value["id"] = digest(value)
    write(p, value)
    return value


def verify():
    f = read(ROOT / "configs/freeze.json")
    for name, expected in f["files"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("Protocol code changed after freeze: " + name)
    from ..experiment_a.src.data import audit
    from ..experiment_a.src.common import verify as verify_a
    a = audit()
    verify_a(ROOT.parent / "experiment_a/data/releases/a1-v1")
    return a


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "run", "verify"])
    args = parser.parse_args()
    if args.action == "freeze":
        print(freeze()["id"])
    elif args.action == "verify":
        print(packed(verify()))
    else:
        verify()
        cases, knowledge, _ = selected()
        # Independent model requests can overlap; there are no separate agents.
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda c: run_case(c, knowledge), cases))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda c: run_case(c, knowledge, "candidate_reverse"), cases[:4]))


if __name__ == "__main__":
    main()
