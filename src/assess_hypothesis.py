"""Qwen research synthesis from completed metrics, never a relevance judge."""
import csv
import json

from io_utils import ROOT, read_json, write_json
from llm_client import call_model, object_schema


def rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def synthesis_case(case):
    return {
        "case_id": case["case_id"],
        "semantic_audit": case["semantic_audit"],
        "retrieval": case["retrieval"],
        "provisional_gold": case["gold_relevance"],
        "baseline_outputs": [record["representation"] for record in case["baseline_outputs"]
                             if record["representation"]["baseline_id"] != "B4"],
    }


def main():
    experiment = read_json(ROOT / "config/experiment.json")
    evaluation = read_json(ROOT / "outputs/metrics/evaluation_manifest.json")
    semantic = read_json(ROOT / "outputs/case_analysis/semantic_audit/summary.json")
    if evaluation["run_count"] != 576 or not semantic["all_cases_completed"]:
        raise ValueError("Research synthesis requires completed evaluation and all 24 semantic audits")
    payload = {
        "protocol": (ROOT / "docs/EXECUTION_PROTOCOL.md").read_text(encoding="utf-8"),
        "evaluation_manifest": evaluation,
        "metrics": rows(ROOT / "outputs/metrics/summary.csv"),
        "knowledge_group_metrics": rows(ROOT / "outputs/metrics/knowledge_group_breakdown.csv"),
        "paired_uncertainty": rows(ROOT / "outputs/metrics/cluster_bootstrap.csv"),
        "judge_agreement": read_json(ROOT / "outputs/metrics/judge_agreement.json"),
        "agreement_definition": "Non-zero disagreement binarizes relevance > 0; grade 1 versus 2 is not a binary disagreement. The main binary rate uses all resolved pairs; the union-positive rate uses only pairs positive for either judge. Exact agreement and linear weighted kappa use all three ordinal grades.",
        "judge_subgroups": read_json(ROOT / "outputs/metrics/judge_agreement_subgroups.json"),
        "practice_calibration": read_json(ROOT / "annotations/calibration/summary.json"),
        "matched_pairs": read_json(ROOT / "outputs/metrics/matched_pairs.json"),
        "failure_analysis": read_json(ROOT / "outputs/case_analysis/analysis_summary.json"),
        "semantic_audit": semantic,
        "source_limits": (ROOT / "reports/CORPUS_AUDIT.md").read_text(encoding="utf-8"),
    }
    selected=[]
    for case_id in payload["failure_analysis"]["top_five_failure_candidates"]:
        case=read_json(ROOT / f"outputs/case_analysis/{case_id}.json")
        selected.append(synthesis_case(case))
    payload["five_selected_failure_cases"]=selected
    schema = object_schema({
        "category": {"type": "string", "enum": list("ABCDE")},
        "hypothesis_status": {"type": "string", "enum": ["supported", "partially supported", "unsupported", "inconclusive"]},
        "reasoning": {"type": "string", "minLength": 1},
        "strongest": {"type": "string", "minLength": 1},
        "next_step": {"type": "string", "minLength": 1},
        "failure_interpretation": {"type": "string", "minLength": 1},
    })
    prompt = """Synthesize the completed C1 pilot research result. Use only these actual outputs; do not use tools or invent facts, thresholds, advantages or missing results. Write concise English suitable for a research report.
The question is whether a distinct retrieval-oriented Personal Evidence representation has a meaningful potential information-retention advantage beyond strong longitudinal Summary, Insight-style and five-query QueryGen. No Personal Evidence method has been implemented or tested, so do not claim its performance or treatment benefit. Corpus distinctions unsupported by authorities must not be manufactured. Labels are PROVISIONAL_LLM_GOLD; audits are PROVISIONAL_LLM_AUDIT; all cases synthetic; judges/auditor share Qwen weights.
Choose exactly one category using the user's unchanged meanings:
A: Generic summary/insight is basically sufficient; C1 is weak.
B: Insight has stable information loss but QueryGen already solves it; a new Evidence representation lacks demonstrated incremental value.
C: Strong Summary, Insight and QueryGen all show consistent retrieval failures linked to genuinely missing retrieval-relevant information; retrieval-oriented representation deserves further research.
D: Evidence-related directions may add retrieval noise; the current hypothesis is unsupported or needs redefinition.
E: Pilot evidence is insufficient to decide.
Do not select C merely because recall is less than one or all methods miss items: ranking, corpus coverage, missing context, source clustering and provisional label error are alternatives. Retained facts with missed items are not information loss. Conversely, do not call summary sufficient just because its relative mean is highest. Inspect both retrievers, repeats, matched-pair conditional item behavior, semantic omissions and noise, source-backed applicability, and uncertainty. Different candidate sets are not automatically correct discrimination, and identical gold for a matched pair limits identification. Do not redefine C1 or recommend modifying the benchmark to rescue it.
Name the strongest Summary/Insight/QueryGen condition using actual metrics. When metrics or retrievers disagree, say so rather than inventing a single composite endpoint. Explain the five automatically selected failure candidates and concrete conditional-versus-ranking limitations. Explicitly decide whether it is worth designing Personal Evidence next or whether more reliable identification is required first. Cite exact observed numbers sparingly and correctly; no human-ground-truth claim.
DATA_JSON:
""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assessment, metadata = call_model(prompt, schema, experiment["llm"]["audit_model"],
                                      experiment["revision"] + "/research_synthesis_v1", experiment["llm"])
    assessment["assessment_kind"] = "PROVISIONAL_LLM_RESEARCH_SYNTHESIS"
    assessment["model_metadata"] = metadata
    write_json(ROOT / "reports/research_assessment.json", assessment)
    print(json.dumps({"category": assessment["category"], "hypothesis_status": assessment["hypothesis_status"],
                      "strongest": assessment["strongest"]}), flush=True)


if __name__ == "__main__":
    main()
