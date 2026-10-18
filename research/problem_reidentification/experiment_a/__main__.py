"""Unified Experiment A CLI. Run from repository root."""
import argparse
import json
from pathlib import Path

from .src.common import LOCAL, P1, ROOT, credential_available, read, write


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("audit")
    q.add_argument("--output", required=True)
    q = sub.add_parser("check-baselines")
    q.add_argument("--output", required=True)
    q = sub.add_parser("reproduce")
    q.add_argument("--project", choices=("medcpt", "trialgpt", "pha-offline", "phia", "pha_ds", "pha_parallel", "pha_orchestrator"), required=True)
    q.add_argument("--output", required=True)
    sub.add_parser("download-medcpt")
    q = sub.add_parser("retrieve")
    q.add_argument("--method", choices=("bm25", "bge_m3", "medcpt", "medcpt_cross"), required=True)
    q.add_argument("--mode", choices=("current", "statistics", "full"), default="statistics")
    q.add_argument("--limit", type=int, default=48)
    q.add_argument("--output", required=True)
    q = sub.add_parser("build-a1")
    q.add_argument("--output", required=True)
    for name in ("packets", "import-gold", "evaluate", "evaluate-retrieval", "failures", "run-a0", "run-a1", "smoke"):
        q = sub.add_parser(name)
        if name not in ("run-a0", "run-a1", "smoke"):
            q.add_argument("--stage", choices=("a0", "a1"), default="a0")
        q.add_argument("--release", default=str(ROOT / "data/releases/a1-v1"))
        q.add_argument("--output", required=True)
        if name in ("run-a0", "run-a1", "smoke"):
            from .src.matching import METHODS
            q.add_argument("--method", choices=METHODS, required=True)
            q.add_argument("--limit", type=int, default=1)
            q.add_argument("--mode", choices=("current", "statistics", "full"), default="full")
            q.add_argument("--max-calls", type=int, default=12)
            q.add_argument("--external-authorized", action="store_true")
            q.add_argument("--batch-authorized", action="store_true")
        elif name == "import-gold":
            for option in ("packets-path", "roster", "a", "b"):
                q.add_argument("--" + option, required=True)
            q.add_argument("--adjudications")
        elif name in ("evaluate", "evaluate-retrieval", "failures"):
            q.add_argument("--predictions", required=name == "evaluate-retrieval")
            q.add_argument("--gold-dir", required=name == "evaluate-retrieval")
            if name == "evaluate":
                q.add_argument("--bootstrap", type=int, default=0)
    q = sub.add_parser("budget")
    q.add_argument("--output", required=True)
    q = sub.add_parser("summarize")
    q.add_argument("--output", required=True)
    return p


def execute(args):
    command = args.pop("command")
    if command == "audit":
        from .src.data import audit
        result = audit()
        write(args["output"], result)
        return {k: result[k] for k in ("status", "legacy_hashes_verified", "cases", "participants", "a0_pairs")}
    if command == "check-baselines":
        from .src.upstream import inventory
        result = {"official_sources": inventory(), "credential_available": credential_available(),
                  "credential_available_scope": "Process environment only; secure wrapper may load DPAPI later",
                  "dpapi_credential_present": (Path(__import__('os').environ.get('LOCALAPPDATA', '')) / 'C1Pilot/qwen-api-key.dpapi').is_file(),
                  "credential_values_read_or_logged": False, "provider": "DashScope", "model": "qwen3.8-max",
                  "native_azure_or_gemini_credentials": "not_configured_or_probed", "human_gold": "not_available"}
        write(args["output"], result)
        return result
    if command == "download-medcpt":
        from .src.upstream import download_medcpt
        return download_medcpt()
    if command == "reproduce":
        project, output = args["project"], args["output"]
        if project == "medcpt":
            from .src.upstream import medcpt_smoke
            return medcpt_smoke(output)
        if project == "trialgpt":
            from .src.trialgpt import smoke
            return smoke(output)
        from .src.pha import native_smoke, offline_check
        return offline_check(output) if project == "pha-offline" else native_smoke(project, output)
    if command == "retrieve":
        from .src.retrieval import run
        result = run(**args)
        return {k: result[k] for k in ("status", "method", "cases", "duration_seconds")}
    if command == "build-a1":
        from .src.data import build_a1
        result = build_a1(**args)
        return {k: result[k] for k in ("release_id", "unique_pairs", "participants")}
    if command == "packets":
        from .src.annotation import packets
        return packets(**args)
    if command == "import-gold":
        from .src.annotation import import_gold
        return import_gold(**args)
    if command in ("run-a0", "run-a1", "smoke"):
        from .src.matching import run
        if args["limit"] < 1 or args["limit"] > 48:
            raise ValueError("limit must be 1..48")
        if command == "smoke" and args["limit"] > 2:
            raise ValueError("Smoke test uses at most two common cases")
        result = run(stage="a1" if command == "run-a1" else "a0", **args)
        return {k: result[k] for k in ("status", "method", "predictions", "parse_failures", "llm_calls")}
    if command in ("evaluate", "evaluate-retrieval", "failures"):
        from .src.evaluation import evaluate, retrieval_metrics, failure_queue
        function = {"evaluate": evaluate, "evaluate-retrieval": retrieval_metrics, "failures": failure_queue}[command]
        if command == "evaluate-retrieval":
            args["rankings"] = args.pop("predictions")
        return function(**args)
    if command == "budget":
        current = ROOT / "results/credential_continuation.json"
        if current.exists():
            r = read(current)
            forecasts = r["one_case_batch_scaling_forecast"]
            a0 = sum(x["cny_48_cases_ignoring_discounts_if_representative"] for x in forecasts.values())
            additional_e3 = sum(48*(v["prompt_tokens_logical"]*12 + v["completion_tokens_logical"]*36)/1_000_000
                                for v in r["e3_direct_smoke_views"] if v.get("information_view") in ("current", "statistics"))
            result = {"status": "BATCH_PAUSED_UNTIL_EXPLICIT_BUDGET_AUTHORIZATION", "based_on": str(current.relative_to(ROOT)),
                      "one_case_scaling_forecasts": forecasts,
                      "a0_six_methods_estimated_cny_ignoring_discounts": a0,
                      "a0_plus_additional_e3_estimated_cny_ignoring_discounts": a0+additional_e3,
                      "actual_invoice_cost": None, "paid_batch_executed": False,
                      "warning": r["forecast_limitations"], "smoke_costs": r["costs"]}
            write(args["output"], result)
            return result
        result = {"status": "BATCH_PAUSED_UNTIL_COST_AND_BUDGET_REVIEW", "a0_cases": 48, "a0_pairs": 240,
                  "estimated_call_caps_per_case": {"direct": 1, "trialgpt_style": 5, "phia": 12,
                      "pha_parallel": 12, "pha_orchestrator": 12, "pha_ds_trialgpt": 8},
                  "a0_e2_e4_call_cap": 2400, "e3_extra_direct_current_and_statistics_calls": 96,
                  "native_smoke_call_cap": 38, "output_token_cap_per_a0_call": 4096,
                  "a0_e2_e4_output_tokens_upper_bound": 9830400,
                  "input_character_cap_per_call": 250000, "input_token_forecast": None,
                  "verified_rate_per_million_tokens": None, "estimated_money": None,
                  "reason": "No verified provider billing rate or approved batch budget; tool/agent iterations make point estimates unreliable before smoke",
                  "actual_cost": 0 if not credential_available() else None,
                  "a1_paid_inference_planned": False, "cache": "Exact request SHA256, persistent attempt ledger and per-case checkpoints"}
        write(args["output"], result)
        return result
    if command == "summarize":
        from .src.continuation import build
        return build(**args)
    raise ValueError("Unknown command")


def main():
    p = parser()
    try:
        result = execute(vars(p.parse_args()))
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except Exception as exc:
        # No request, response or SDK exception text in public console output.
        p.exit(2, "Experiment A stopped: " + type(exc).__name__ + " (inspect private logs/configuration; no result fabricated)\n")


if __name__ == "__main__":
    main()
