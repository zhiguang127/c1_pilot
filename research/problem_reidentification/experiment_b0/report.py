"""Public aggregate reporting only; never export participant predictions or Gold."""
from collections import Counter
from itertools import combinations
from .core import *
from .run import METHODS
from copy import deepcopy


def normalized_reference_diagnostic(output, case):
    """Post-hoc syntax-only diagnostic; original predictions stay immutable.

    The input object includes stats.phase.metrics.metric.stat. The output
    contract spells the same location stats.phase.metric.stat. Only remove
    that literal layer when the canonical reference resolves in the same input.
    """
    from ..experiment_a.silver.pipeline import resolve
    value = deepcopy(output)
    changes = 0
    for item in value.get("items", []):
        for entry in item.get("evidence", []):
            if not isinstance(entry, dict):
                continue
            ref = entry.get("ref")
            if not isinstance(ref, str):
                continue
            parts = ref.split(".")
            if len(parts) == 5 and parts[0] == "stats" and parts[2] == "metrics":
                fixed = ".".join(parts[:2] + parts[3:])
                try:
                    resolve(case, fixed)
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
                entry["ref"] = fixed
                changes += 1
    return {**evidence_audit(value, case), "format_only_references_mapped": changes}


def order(output):
    return tuple(tuple(sorted(group)) for group in output["ranking"])


def relation(output, a, b):
    groups = {k: i for i, g in enumerate(output["ranking"]) for k in g}
    return (groups[a] > groups[b]) - (groups[a] < groups[b])


def summarize():
    runs = LOCAL / "runs"
    records = [read(p) for p in runs.rglob("*.json")]
    case_map = {c["case_id"]: c for c in selected()[0]}
    panels = {}
    for variant in ("main", "candidate_reverse"):
        rows = [read(p) for p in (runs / variant).rglob("*.json")]
        by_key = {(r["case_id"], r["method"]): r for r in rows}
        methods = {}
        for method in METHODS:
            rr = [r for r in rows if r["method"] == method]
            valid = [r for r in rr if r["status"] == "EXECUTED"]
            comparisons = [(r, by_key.get((r["case_id"], "B1_direct"))) for r in valid]
            comparisons = [(r, b) for r, b in comparisons if b and b["status"] == "EXECUTED"]
            events = [e for r in rr for e in r["events"]]
            audit = Counter()
            normalized = Counter()
            for r in valid:
                audit.update(r["evidence_audit"])
                normalized.update(normalized_reference_diagnostic(r["output"], case_map[r["case_id"]]))
            methods[method] = {
                "planned_windows": 16 if variant == "main" else 4, "completed_records": len(rr),
                "status_counts": dict(Counter(r["status"] for r in rr)),
                "failure_reasons": dict(Counter(r.get("error", "") for r in rr if r["status"] == "FAILED")),
                "not_run_shared_initialization": sum(r.get("error") == "Frozen shared B1 initialization unavailable" for r in rr),
                "validation_failures": dict(Counter(e for r in rr for e in r.get("validation_errors", []))),
                "valid_output_windows": len(valid), "candidate_items_in_valid_outputs": len(valid) * 5,
                "ranking_changed_from_B1": sum(order(r["output"]) != order(b["output"]) for r, b in comparisons),
                "ranking_comparison_denominator": len(comparisons),
                "explanation_changed_windows": sum(
                    {x["id"]: (x["explanation"], x["evidence"]) for x in r["output"]["items"]} !=
                    {x["id"]: (x["explanation"], x["evidence"]) for x in b["output"]["items"]} for r, b in comparisons),
                "applicability_changed_items": sum(
                    x["applicability"] != next(y["applicability"] for y in b["output"]["items"] if y["id"] == x["id"])
                    for r, b in comparisons for x in r["output"]["items"]),
                "rarr_open_gates": sum(r.get("details", {}).get("gate", {}).get("is_open", False) for r in rr),
                "strict_pairs_changed_from_B1": sum(relation(r["output"], a, k) != relation(b["output"], a, k)
                    for r, b in comparisons for a, k in combinations(sorted(x["id"] for x in r["output"]["items"]), 2)),
                "pair_denominator": len(comparisons) * 10,
                "all_candidates_tied_windows": sum(len(r["output"]["ranking"]) == 1 for r in valid),
                "self_reported_priority_identifiable": sum(r["output"].get("priority_identifiable") is True for r in valid),
                "mechanical_evidence_only": dict(audit), "model_calls_including_cache": len(events),
                "posthoc_reference_format_diagnostic": dict(normalized),
                "logical_input_tokens": sum(e["usage"]["prompt_tokens"] for e in events),
                "logical_output_tokens": sum(e["usage"]["completion_tokens"] for e in events),
                "logical_cost_no_discount": sum(e["cost_no_discount"] for e in events),
                "tool_interactions": sum(len(r["tool_events"]) for r in rr),
            }
        panels[variant] = methods
    invariance = {}
    pairs = {}
    main = {(read(p)["case_id"], read(p)["method"]): read(p) for p in (runs / "main").rglob("*.json")}
    for method in METHODS:
        vv = [read(p) for p in (runs / "candidate_reverse").glob("*/" + method + ".json")]
        comparable = [(r, main.get((r["case_id"], method))) for r in vv]
        comparable = [(r, b) for r, b in comparable if b and r["status"] == b["status"] == "EXECUTED"]
        invariance[method] = {"planned": 4, "valid_paired_windows": len(comparable),
                              "same_priority_order": sum(order(r["output"]) == order(b["output"]) for r, b in comparable),
                              "same_pair_relations": sum(relation(r["output"], a, k) == relation(b["output"], a, k)
                                  for r, b in comparable for a, k in combinations(sorted(x["id"] for x in r["output"]["items"]), 2)),
                              "pair_denominator": len(comparable) * 10}
    for left, right in [("B4_critic", "S4_relative"), ("BM_critic", "S4_relative"),
                        ("BM_self_refine", "S4_relative"), ("S3a_grounding", "S3b_claim"), ("S3b_claim", "S4_relative")]:
        rr = [(main.get((c["case_id"], left)), main.get((c["case_id"], right))) for c in selected()[0]]
        rr = [(a, b) for a, b in rr if a and b and a["status"] == b["status"] == "EXECUTED"]
        pairs[left + "__" + right] = {"valid_paired_windows": len(rr),
            "different_orders": sum(order(a["output"]) != order(b["output"]) for a, b in rr),
            "mechanical_invalid_citation_totals": {side: sum(sum(x["evidence_audit"][k] for k in ("invalid_reference", "invalid_value", "unusable_physiology")) for x in [r[i] for r in rr]) for i, side in enumerate([left, right])},
            "posthoc_normalized_invalid_citation_totals": {side: sum(sum(
                normalized_reference_diagnostic(r[i]["output"], case_map[r[i]["case_id"]])[k]
                for k in ("invalid_reference", "invalid_value", "unusable_physiology")) for r in rr) for i, side in enumerate([left, right])},
            "decision_improvement": None}
    budget = read(LOCAL / "budget.json")
    # Audit fairness using executed records, not merely configured permissions.
    fairness = {"shared_initial_checks": 0, "complete_tool_result_checks": 0, "valid": True}
    case_lookup = {c["case_id"]: c for c in selected()[0]}
    knowledge = selected()[1]
    for variant in ("main", "candidate_reverse"):
        panel = [read(p) for p in (runs / variant).rglob("*.json")]
        initials = {r["case_id"]: r for r in panel if r["method"] == "B1_direct"}
        for r in panel:
            initial_hash = r.get("details", {}).get("initial_output_sha256")
            if initial_hash:
                assert initial_hash == digest(initials[r["case_id"]]["output"])
                fairness["shared_initial_checks"] += 1
            for event in r["tool_events"]:
                assert event["full_record_count"] == 42
                assert event["result_sha256"] == digest(payload(case_lookup[r["case_id"]], knowledge))
                fairness["complete_tool_result_checks"] += 1
    attempts = budget["attempts"]
    known = [a["metadata"] for a in attempts if "metadata" in a]
    private_files = {p.relative_to(LOCAL).as_posix(): sha(p) for p in LOCAL.rglob("*.json") if any(s in p.parts for s in ("runs", "cache", "requests", "protocol_history"))}
    write(LOCAL / "execution_manifest.json", {"files": private_files, "at": now()}, True)
    result = {"status": "COMPLETE_EXPLORATORY_EXECUTION" if len(records) == 200 else "RUNNING_OR_INCOMPLETE",
              "planned_records": 200, "record_count": len(records), "panels": panels, "paired_comparisons": pairs,
              "executed_fairness_checks": fairness,
              "candidate_order_intervention": invariance, "human_gold": False, "decision_accuracy": None,
              "clinical_correctness": None, "novel_constraint_contribution_established": False,
              "reference_diagnostic_version": "POSTHOC_FORMAT_ONLY_V1_NOT_PREDICTION_REPAIR",
              "price": PRICE, "actual_requests_all_versions": len(attempts),
              "returned_models": sorted({m["model"] for m in known}),
              "responses_metered": len(known), "unknown_or_interrupted_requests": len(attempts) - len(known),
              "input_tokens": sum(x["usage"]["prompt_tokens"] for x in known),
              "output_tokens": sum(x["usage"]["completion_tokens"] for x in known),
              "estimated_cost_no_discount": sum(x["cost_no_discount"] for x in known),
              "estimated_cost_reported_cache": sum(x["cost_reported_cache"] for x in known),
              "reserved_ceiling_for_unresolved_calls": sum(x["reserve"] for x in attempts if "metadata" not in x),
              "cap_cny": budget["cap_cny"], "private_manifest_sha256": sha(LOCAL / "execution_manifest.json"),
              "freeze_id": read(ROOT / "configs/freeze.json")["id"], "at": now()}
    write(ROOT / "results/comparison.json", result, True)
    return result


if __name__ == "__main__":
    result = summarize()
    print(packed({k: result[k] for k in ["status", "record_count", "actual_requests_all_versions", "estimated_cost_no_discount"]}))
