"""Privacy-preserving continuation readout: counts, provenance and cost estimates."""
from pathlib import Path
import re

from .common import LOCAL, ROOT, now, read, rows, sha, write
from .data import audit
from .upstream import inventory

SELECTED = {
    "direct": "a0-direct-v8",
    "trialgpt_style": "a0-trialgpt-v8",
    "phia": "a0-phia-v9",
    "pha_parallel": "a0-parallel-v9",
    "pha_orchestrator": "a0-orchestrator-v10",
    "pha_ds_trialgpt": "a0-combination-v9",
}


def run_metadata(name):
    path = LOCAL / "runs" / name
    if not (path / "manifest.json").exists():
        return {"run": name, "status": "NOT_COMPLETED", "formal_metrics": None}
    manifest = read(path / "manifest.json")
    predictions = rows(path / "predictions.jsonl")
    raw_tools = [tool for raw in (path / "raw").glob("*.json") for tool in read(raw).get("tools", [])]
    specialists = [s for e in raw_tools if e.get("tool") == "audit_specialist_responses" for s in e.get("responses", [])]
    usage = [e.get("usage") or {} for e in read(path / "transport/events.json")] if (path / "transport/events.json").exists() else []
    return {"run": name, "status": manifest["status"], "method": manifest["method"],
            "cases": manifest["limit"], "pairs": len(predictions),
            "case_ids_sha256": __import__('hashlib').sha256("\n".join(sorted({p["case_id"] for p in predictions})).encode()).hexdigest(),
            "parsed_labels": sum(p["parse_status"] == "ok" for p in predictions),
            "reference_validation_failures": sum(p.get("evidence_validation_status") == "invalid" for p in predictions),
            "evidence_semantics_human_reviewed": False,
            "llm_calls_new_this_run": manifest.get("llm_calls"), "cache_hits": manifest.get("cached_calls"),
            "logical_requests": manifest.get("llm_calls", 0) + manifest.get("cached_calls", 0),
            "prompt_tokens_logical": sum(u.get("prompt_tokens", 0) for u in usage),
            "completion_tokens_logical": sum(u.get("completion_tokens", 0) for u in usage),
            "tool_calls": manifest.get("tool_calls"),
            "tools_in_trace": sorted({t["tool"] for t in raw_tools if t.get("is_tool_call", True)}),
            "specialist_diagnostic_errors": [s["agent"] for s in specialists if any(k in s["response"].lower() for k in ("could not extract", "[error", "budget exhausted"))],
            "duration_seconds": manifest.get("duration_seconds"),
            "runtime_note": "Includes cache replay; not comparable latency. Logical requests/tokens describe the actual model transcript, with cache hits separate.",
            "information_view": manifest["mode"], "protocol_release_id": manifest["protocol_release_id"],
            "formal_metrics": None, "manifest_sha256": sha(path / "manifest.json"),
            "predictions_sha256": sha(path / "predictions.jsonl")}


def cost_summary():
    ledgers = list((LOCAL / "official-smoke").glob("*/ledger.json")) + list((LOCAL / "runs").glob("*/transport/ledger.json"))
    attempts = sum(read(p)["attempts"] for p in ledgers)
    bodies = [read(p)["response"] for p in (LOCAL / "cache/model-responses").glob("*.json")]
    prompt = sum((b.get("usage") or {}).get("prompt_tokens", 0) for b in bodies)
    output = sum((b.get("usage") or {}).get("completion_tokens", 0) for b in bodies)
    cached_input = sum(((b.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens", 0) for b in bodies)
    # These are list-price products, not invoice amounts. The pre-guard PHIA
    # Responses invocation cannot be retroactively measured and stays separate.
    return {"metered_request_attempts": attempts, "unique_cached_successful_requests": len(bodies),
            "prompt_tokens_metered_successes": prompt, "completion_tokens_metered_successes": output,
            "provider_cached_input_tokens": cached_input,
            "estimated_cny_ignoring_cache_discounts": (prompt*12 + output*36)/1_000_000,
            "estimated_cny_applying_reported_input_cache_discount": ((prompt-cached_input)*12 + cached_input*1.5 + output*36)/1_000_000,
            "price_source": "https://help.aliyun.com/zh/model-studio/qwen3-8-max",
            "price_checked_on": "2026-10-16", "price_basis": "Published Beijing rates: CNY 12 input / 36 output / 1.5 cached input per million tokens",
            "actual_invoice_cost": None,
            "unmetered_legacy_phia_smoke": {"exact_requests": None, "observed_model_steps_lower_bound": 3,
                                           "tokens": None, "actual_cost": None,
                                           "note": "First PHIA smoke used OneTwo Responses outside the old chat-only instrumentation; excluded from zero-cost claims"},
            "scope": "All recorded local official and A0 smoke attempts, including failed/replaced runs; excludes software fixtures",
            "paid_48_case_batch_executed": False}


def build(output):
    selected = {m: run_metadata(n) for m, n in SELECTED.items()}
    completed = [r for r in selected.values() if r.get("status") != "NOT_COMPLETED"]
    same_cases = len({r["case_ids_sha256"] for r in completed}) <= 1
    if not same_cases:
        raise ValueError("Selected methods do not use the same frozen case set")
    smoke_mapping = read(ROOT / "configs/active_baselines.json")
    smokes = {}
    for method, name in smoke_mapping.items():
        path = ROOT / name
        if path.exists():
            r = read(path)
            smokes[method] = {"report": name, **{k:r.get(k) for k in
                ("status", "llm_calls", "cached_calls", "tool_calls", "prompt_tokens", "completion_tokens",
                 "component_errors", "incomplete_model_responses", "source_edits", "model", "base_model")}}
        else:
            smokes[method] = {"report": name, "status": "NOT_COMPLETED"}
    input_audit = audit()
    e3 = [run_metadata(n) for n in ("e3-direct-current-v8", "e3-direct-statistics-v8", "a0-direct-v8")]
    tests = {}
    for label, name in (("experiment_a", "tests-credential-final.log"), ("p1", "tests-p1-credential-final.log"), ("legacy_c1", "tests-legacy-credential-final.log")):
        p = LOCAL / name
        text = p.read_text(encoding="utf-8-sig") if p.exists() else ""
        match = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
        tests[label] = {"tests": int(match[1]) if match else None, "passed": bool(match and re.search(r"^OK\s*$", text, re.M)),
                        "log_sha256": sha(p) if p.exists() else None}
    # A descriptive scaling estimate from one prespecified case is not a batch
    # authorization, nor a stable efficiency estimate over 16 participants.
    forecasts = {}
    for method, r in selected.items():
        if r.get("status") != "NOT_COMPLETED":
            forecasts[method] = {"calls_48_cases_if_first_case_representative": r["logical_requests"]*48,
                "cny_48_cases_ignoring_discounts_if_representative":
                    48*(r["prompt_tokens_logical"]*12 + r["completion_tokens_logical"]*36)/1_000_000}
    result = {"recorded_at": now(), "status": "PENDING_HUMAN_ANNOTATION", "credential_configured": True,
              "credential_storage": "User-bound DPAPI outside repository; never stored in plaintext project files",
              "input_integrity": {k:input_audit[k] for k in ("legacy_hashes_verified", "p1_release_id", "cases", "participants", "a0_pairs")},
              "official_sources": inventory(), "official_smokes": smokes,
              "selected_methods_share_exact_case_set": same_cases,
              "a0_selected_smoke_runs": selected, "e3_direct_smoke_views": e3,
              "formal_accuracy_or_retrieval_metrics": None, "human_gold_pairs": 0,
              "costs": cost_summary(), "one_case_batch_scaling_forecast": forecasts,
              "forecast_limitations": "Only one prespecified P1 window; architecture tool/retry counts vary. Billing discounts and actual invoice unknown. No paid batch authorization inferred.",
              "tests": tests, "conclusion": "Real execution and prediction feasibility only; stable applicability success/failure and repair benefits remain unmeasured"}
    write(output, result)
    return {"status": result["status"], "selected_methods_completed": sum(r.get("status") != "NOT_COMPLETED" for r in selected.values()),
            "costs": result["costs"], "tests": tests}
