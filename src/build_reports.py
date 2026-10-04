"""Render research reports from real saved outputs and an explicit assessment."""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from evaluate import METRICS, read_gold, ranking_metrics
from io_utils import ROOT, read_json, read_jsonl, write_json

NAMES={"B1":"Summary","B2":"Insight-style","B3":"QueryGen (5 queries)","B4":"Raw statistical facts"}
METRIC_NAMES=["R@5","R@10","R@20","Strong R@10","nDCG@10","Irrelevant@10"]


def read_csv(path):
    with path.open(encoding="utf-8",newline="") as handle:
        return list(csv.DictReader(handle))


def number(value):
    return "N/A" if value in (None,"") else f"{float(value):.3f}"


def table(headers, rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join(["---"]*len(headers))+" |"]+["| "+" | ".join(str(v).replace("|","/").replace("\n"," ") for v in row)+" |" for row in rows])+"\n"


def qwen_usage_totals(calls_root, experiment):
    requested_models = {experiment["llm"][role + "_model"] for role in
                        ("generator", "judge_a", "judge_b", "adjudicator", "audit")}
    included = []
    skipped_archives = 0
    skipped_backends = 0
    totals = Counter()
    by_stage = defaultdict(Counter)
    by_scope = defaultdict(Counter)
    unknown_usage = []
    for path in sorted(Path(calls_root).rglob("metadata.json")):
        if any("archiv" in part.casefold() for part in path.relative_to(calls_root).parts):
            skipped_archives += 1
            continue
        metadata = read_json(path)
        backend = metadata.get("backend", "")
        model = metadata.get("requested_model", metadata.get("model", ""))
        if backend not in {"openai_compatible", "openai_compatible_chat_completions", "qwen_api", "dashscope"} or model not in requested_models:
            skipped_backends += 1
            continue
        task_id = metadata.get("task_id", str(path.parent.relative_to(calls_root)))
        parts = path.relative_to(calls_root).parts
        if any("rejected_cached_response" in part.casefold() for part in parts):
            scope = "rejected_model_attempt"
        elif ("execution-qwen-v1" in task_id and "blinded-annotation-v2-shortrefs" not in task_id
              and (re.search(r"(?:judge_[ab]|adjudicator)_[CP][0-9]{3}", task_id)
                   or "practice" in task_id.casefold() or "calibration" in task_id.casefold())):
            scope = "superseded_annotation"
        else:
            scope = "current_stage_calls"
        if "representations" in task_id:
            stage = "representations"
        elif "semantic-audit" in task_id:
            stage = "semantic_audit"
        elif "source" in task_id and "audit" in task_id:
            stage = "source_audit"
        elif "adjudicator" in task_id:
            stage = "adjudication"
        elif "_P" in task_id:
            stage = "calibration"
        elif "judge_" in task_id:
            stage = "judges"
        else:
            stage = "other"
        usage = metadata.get("usage") or {}
        values = {"prompt_tokens": usage.get("prompt_tokens", usage.get("input_tokens")),
                  "completion_tokens": usage.get("completion_tokens", usage.get("output_tokens")),
                  "total_tokens": usage.get("total_tokens")}
        if values["total_tokens"] is None and values["prompt_tokens"] is not None and values["completion_tokens"] is not None:
            values["total_tokens"] = values["prompt_tokens"] + values["completion_tokens"]
        if any(type(value) is not int or value < 0 for value in values.values()):
            unknown_usage.append(task_id)
        totals["successful_call_metadata_count"] += 1
        by_stage[stage]["successful_call_metadata_count"] += 1
        by_scope[scope]["successful_call_metadata_count"] += 1
        for name, value in values.items():
            if type(value) is int and value >= 0:
                totals[name] += value
                by_stage[stage][name] += value
                by_scope[scope][name] += value
        included.append({"task_id": task_id, "metadata_path": str(path.relative_to(calls_root)),
                         "stage": stage, "scope": scope, "requested_model": model,
                         "returned_model": metadata.get("provider_model", metadata.get("returned_model", metadata.get("response_model"))),
                         "provider_request_id": metadata.get("provider_request_id"),
                         "http_request_id": metadata.get("http_request_id"),
                         "usage": values})
    return {"execution_revision": experiment["revision"], "backend": "openai_compatible",
            "base_url": experiment["llm"]["base_url"], "totals": dict(totals),
            "by_stage": {stage: dict(values) for stage, values in sorted(by_stage.items())},
            "by_scope": {scope: dict(values) for scope, values in sorted(by_scope.items())},
            "included_calls": included, "unknown_usage_call_ids": unknown_usage,
            "skipped_archive_metadata": skipped_archives, "skipped_non_qwen_metadata": skipped_backends,
            "coverage": "Cumulative recorded Qwen response budget, including superseded annotation and rejected cached-response attempts; archived runs and non-Qwen providers are excluded. Current-stage totals are separated and missing usage or billing cost is not inferred",
            "retry_caveat": "If the API adapter's usage only covers the successful attempt, earlier billed failed/repair attempts are not included"}


def main():
    experiment = read_json(ROOT/"config/experiment.json")
    summaries=read_csv(ROOT/"outputs/metrics/summary.csv")
    per_case=read_csv(ROOT/"outputs/metrics/per_case.csv")
    per_run=read_csv(ROOT/"outputs/metrics/per_run.csv")
    intervals=read_csv(ROOT/"outputs/metrics/cluster_bootstrap.csv")
    knowledge_groups=read_csv(ROOT/"outputs/metrics/knowledge_group_breakdown.csv")
    api_usage=qwen_usage_totals(ROOT/"outputs/llm_calls", experiment)
    write_json(ROOT/"outputs/metrics/qwen_api_usage.json", api_usage)
    agreement=read_json(ROOT/"outputs/metrics/judge_agreement.json")
    matched=read_json(ROOT/"outputs/metrics/matched_pairs.json")
    manifest=read_json(ROOT/"outputs/metrics/evaluation_manifest.json")
    failure=read_json(ROOT/"outputs/case_analysis/analysis_summary.json")
    audit=read_json(ROOT/"outputs/case_analysis/semantic_audit/summary.json")
    reps=read_jsonl(ROOT/"outputs/representations/representations.jsonl")
    cases=read_jsonl(ROOT/"data/wearable_cases.jsonl")
    corpus=read_jsonl(ROOT/"data/knowledge_items.jsonl")
    items={item["id"]:item for item in corpus}
    gold=read_gold(ROOT/"data/relevance_labels_provisional.csv",{c["id"] for c in cases},set(items))
    recall_ceilings = []
    for case_id, labels in sorted(gold.items()):
        positive_count = sum(label >= 1 for label in labels.values())
        strong_count = sum(label == 2 for label in labels.values())
        recall_ceilings.append({"case_id": case_id, "positive_count": positive_count, "strong_count": strong_count,
                                "maximum_recall_at_10": min(10, positive_count)/positive_count if positive_count else None,
                                "maximum_strong_recall_at_10": min(10, strong_count)/strong_count if strong_count else None})
    assessment=read_json(ROOT/"reports/research_assessment.json")
    if assessment["category"] not in "ABCDE" or assessment["hypothesis_status"] not in ["supported","partially supported","unsupported","inconclusive"]:
        raise ValueError("An explicit A/B/C/D/E research assessment is required")
    if manifest["run_count"]!=576 or len(reps)!=288 or not audit["all_cases_completed"]:
        raise ValueError("Do not render completed pilot reports from partial runs")
    overall=[row for row in summaries if row["grouping"]=="overall"]
    results=["# C1 Pilot Results","","Label status: **PROVISIONAL_LLM_GOLD**. All observations are synthetic; no human ground truth, official PHIA or Personal Evidence method was run.","",f"Research category: **{assessment['category']}**. C1 status: **{assessment['hypothesis_status']}**.","",assessment["reasoning"],"","## Execution coverage","","24 cases (1008 day rows), 96 source-grounded items, two 2304-pair fresh-context Qwen judge matrices and 2304 adjudications, 288 representations (three repeats), and 576 retrieval runs across BM25 and dense. Semantic audits cover all 24 cases.","",f"Model calls use the authorized Qwen API endpoint `{experiment['llm']['base_url']}` and fixed alias `{experiment['llm']['generator_model']}`. Fixed parameters: temperature={experiment['llm']['temperature']}, enable_thinking={experiment['llm']['enable_thinking']}, max_tokens={experiment['llm']['max_tokens']}; no provider sampling seed is assumed. Generator, both judges, adjudicator and semantic auditor share the same model alias. Separate contexts and shuffled inputs do not establish independent model families.","","## Overall metrics","","Case-level means after averaging three repeats; N/A denominators excluded, not scored as zero. Higher is better except Irrelevant@10.","",table(["Retriever","Baseline",*METRIC_NAMES],[[r["retriever"],NAMES[r["baseline_id"]],*[number(r[m]) for m in METRICS]] for r in overall]),"","## Judge reliability","",f"Exact agreement: {number(agreement['exact_agreement'])}; linear weighted Cohen kappa: {number(agreement['linear_weighted_cohen_kappa'])}; non-zero disagreement rate: {number(agreement['non_zero_disagreement_rate'])}. Resolved comparison pairs: {agreement.get('resolved_pairs',agreement['pairs'])}; pairs pending either judge: {agreement.get('pending_either',0)}; pending Judge A: {agreement.get('pending_judge_a',0)}; pending Judge B: {agreement.get('pending_judge_b',0)}.","",table(["Judge A / Judge B","0","1","2"],[[i,*row] for i,row in enumerate(agreement["confusion_matrix_rows_a_columns_b"])]),"","Matrix rows are Judge A, columns Judge B. Both judges use fresh contexts of the same Qwen model; shared weights and related prompts can induce correlated errors. Adjudication reviewed agreements as well as disputes.","",f"All-zero cases: {manifest['all_zero_cases']}; cases without grade 2: {manifest['no_strong_cases']}.","","## A/B/C and four case types","",table(["Retriever","Baseline","Grouping","Group",*METRIC_NAMES],[[r["retriever"],r["baseline_id"],r["grouping"],r["group"],*[number(r[m]) for m in METRICS]] for r in summaries if r["grouping"]!="overall"]),"","## Matched pairs","","Gold differences below are provisional labels, not proof of a medically meaningful temporal distinction. Full conditional-item results and all repeat rankings are in `outputs/metrics/matched_pairs.json`.",""]
    pair_rows=[]
    for pair in matched:
        for method in pair["methods"]:
            pair_rows.append(["/".join(pair["pair"]),pair["gold_different_item_count"],method["retriever"],method["baseline_id"],number(method["mean_candidate_jaccard_at_10"]),number(method["left_metrics"]["ndcg_at_10"]),number(method["right_metrics"]["ndcg_at_10"])])
    interval_table = table(
        ["Retriever","A","B","Metric","B-A","95% lower","95% upper"],
        [[r["retriever"],r["baseline_a"],r["baseline_b"],r["metric"],number(r.get("mean_difference")),number(r.get("lower_95")),number(r.get("upper_95"))]
         for r in intervals if r["metric"] in ("ndcg_at_10","strong_recall_at_10")],
    )
    results+=[table(["Pair","Gold differences","Retriever","Baseline","Top10 Jaccard","Left nDCG","Right nDCG"],pair_rows),"","## Knowledge group diagnostics","","These counts use the same global top10 list, with no subgroup reranking or extra indexed fields. Device measurement-quality knowledge is separated from personal monitoring and behavior/context knowledge. Within-group irrelevant fraction is N/A when that group returns no candidate.","",table(["Retriever","Baseline","Knowledge group","Items","R@10","Strong R@10","Top10 share","Within-group irrelevant@10"],[[row["retriever"],row["baseline_id"],row["knowledge_group"],row["corpus_item_count"],number(row["recall_at_10"]),number(row["strong_recall_at_10"]),number(row["top10_group_share"]),number(row["within_group_irrelevant_fraction_at_10"])] for row in knowledge_groups]),"","## Paired uncertainty","","19 construction clusters (five matched pairs plus fourteen single cases), 10000 bootstrap draws. Intervals describe this synthetic pilot; repeats and labels are not independent participants. All comparisons are exploratory because the planned Evidence comparison is intentionally absent.","",interval_table,"","## Qwen API usage","",table(["Stage","Recorded response metadata","Prompt tokens","Completion tokens","Total tokens"],[[stage,values.get("successful_call_metadata_count",0),values.get("prompt_tokens",0),values.get("completion_tokens",0),values.get("total_tokens",0)] for stage,values in api_usage["by_stage"].items()]),"",f"Cumulative recorded Qwen response budget: {api_usage['totals']}. Calls with incomplete provider usage: {len(api_usage['unknown_usage_call_ids'])}. Superseded annotations and rejected cached responses remain in the cumulative budget but do not contribute to experiment labels or metrics. Archived and non-Qwen calls are excluded. "+api_usage["retry_caveat"]+" Request IDs, returned model aliases and per-call details are retained in `outputs/metrics/qwen_api_usage.json`; this is token accounting, not a billing-cost estimate.","",table(["Budget scope","Recorded response metadata","Prompt tokens","Completion tokens","Total tokens"],[[scope,values.get("successful_call_metadata_count",0),values.get("prompt_tokens",0),values.get("completion_tokens",0),values.get("total_tokens",0)] for scope,values in api_usage["by_scope"].items()]),"","## Recall denominators","","When a case has more than ten positive items, Recall@10 cannot reach 1 even with an ideal ranking: its ceiling is 10 divided by the number of positives. Strong Recall@10 has the same ceiling for grade 2 items. Scores remain unchanged; below-one recall alone is not evidence of representation loss. nDCG@10 still compares against the ideal ten ranked gains.","",table(["Case","Relevant items","Strong items","R@10 ceiling","Strong R@10 ceiling"],[[row["case_id"],row["positive_count"],row["strong_count"],number(row["maximum_recall_at_10"]),number(row["maximum_strong_recall_at_10"])] for row in recall_ceilings]),"","## Current decision","",assessment["next_step"],"","The strongest Summary/Insight/QueryGen condition is "+assessment["strongest"]+". See `FAILURE_ANALYSIS.md` for mechanisms and `VALIDITY_NOTES.md` for limits."]
    root=ROOT/"reports"; root.mkdir(exist_ok=True)
    text_winners = []
    for retriever in sorted({row["retriever"] for row in overall}):
        choices = [row for row in overall if row["retriever"] == retriever and row["baseline_id"] in {"B1", "B2", "B3"}]
        best = min(choices, key=lambda row: (-float(row["ndcg_at_10"]), row["baseline_id"]))
        text_winners.append(best)
    results += ["", "## Text baseline comparison", "", "Restricting to Summary, Insight-style and QueryGen, the highest observed mean nDCG@10 condition per retriever is shown below. This is a descriptive winner, not a significance claim. The separate Qwen synthesis also considers the B4 raw-statistics control; B4 is not one of these three text-generation baselines.", "", table(["Retriever", "Best text baseline", "nDCG@10", "R@10"], [[row["retriever"], NAMES[row["baseline_id"]], number(row["ndcg_at_10"]), number(row["recall_at_10"])] for row in text_winners])]
    results += ["", "## Agreement definitions", "", "Non-zero disagreement means disagreement after binarizing labels to relevance > 0; grade 1 versus grade 2 is not counted in that binary rate. The reported rate uses all resolved pairs. Among the union of positive judgments, the same binary disagreement rate is " + number(agreement["nonzero_union_disagreement_rate"]) + ". Exact agreement and weighted kappa retain the three ordinal grades."]
    results = [line.replace("The strongest Summary/Insight/QueryGen condition is ", "The Qwen all-baseline comparison is ") for line in results]
    (root/"PILOT_RESULTS.md").write_text("\n".join(results)+"\n",encoding="utf-8")
    semantic_rows=[]
    for method in audit["methods"]:
        rates=method["case_weighted_fractions"]
        semantic_rows.append([method["baseline_id"],method["cases_with_fact_opportunities"],*[number(rates[k]) for k in ("retained","omitted","contradicted","uncertain")],method["verifiable_unsupported_excerpt_count"],method["verifiable_potential_noise_excerpt_count"]])
    analysis=["# Representation Failure Analysis","","Observed retrieval errors are relative to **PROVISIONAL_LLM_GOLD**. Semantic retention is **PROVISIONAL_LLM_AUDIT**, independently checked against dates, paths and exact output excerpts. These are not medical truth or causal proof.","","## Information retention","",table(["Baseline","Cases","Retained","Omitted","Contradicted","Uncertain","Unsupported excerpts","Potential noise excerpts"],semantic_rows),"","Rates are case-weighted over correlated fact/repeat opportunities; up to eight relevant facts are selected per case. Accurate paraphrases are accepted. A missing exact number is not automatically information loss.","",table(["Compared condition","Missing/contradicted opportunities","Recovered by QueryGen","Recovery fraction"],[[r["compared_baseline"],r.get("prior_missing_or_contradicted",0),r.get("querygen_recovered",0),number(r["recovery_fraction_of_missing_or_contradicted"])] for r in audit["querygen_fact_recovery"]]),"","Semantic noise flags were generated without retrieval output. Check the saved false positives before attributing noise to them; longer outputs or five queries alone do not establish a causal effect.","","## Five key failure cases",""]
    for case_id in failure["top_five_failure_candidates"]:
        case_report=read_json(ROOT/f"outputs/case_analysis/{case_id}.json")
        summary=next(r for r in failure["per_case"] if r["case_id"]==case_id)
        counts=Counter(k for r in case_report["retrieval"] if r["baseline_id"] in ("B1","B2","B3") for k in r["strong_false_negatives_at_10"])
        positive=counts.most_common(4)
        analysis.extend([f"### {case_id}","",f"Design type: {summary['case_type']}; stratum {summary['stratum']}. Mean Summary/Insight strong miss fraction across retrievers: {number(summary['average_summary_insight_strong_miss_fraction'])}.","",table(["Retriever","Baseline",*METRIC_NAMES],[[r["retriever"],r["baseline_id"],*[number(r[m]) for m in METRICS]] for r in per_case if r["case_id"]==case_id]),"","Frequently missed grade-2 items across B1/B2/B3: "+("; ".join(k+" ("+items[k]["title"]+"): "+str(n)+" runs" for k,n in positive) or "none")+".",""])
        audit_case=case_report["semantic_audit"]
        omitted=[]
        for fact in audit_case["audit"]["facts"]:
            statuses=Counter(check["status"] for check in fact["representation_checks"])
            if statuses["omitted"] or statuses["contradicted"]:
                omitted.append(fact["fact_statement"]+" ["+", ".join(fact["knowledge_ids"])+"]")
        analysis.extend(["Audit facts with at least one omission or contradiction: "+("; ".join(omitted[:3]) or "none; retrieval failure may reflect ranking, corpus or label limits despite retained facts")+".","",f"Complete raw data, every baseline output, top20, full gold, false positives and negatives: `outputs/case_analysis/{case_id}.json`.",""])
    analysis.extend(["## Matched-pair discrimination","",table(["Pair","Different labels","Identifiable under provisional gold"],[["/".join(p["pair"]),p["gold_different_item_count"],p["retrieval_identifiable"]] for p in matched]),"","Candidate lists changing is not itself correct discrimination. Conditional item ranks and the raw observation axis must agree; inspect item-level records, particularly grade 0/1 uncertainty and unsupported conjunctions.","","## Design-sensitive cases without a QueryGen penalty","","Cases where QueryGen did not improve nDCG by at least 0.05 over the better of Summary/Insight in either retriever: "+str(failure["sensitive_design_cases_without_observed_penalty_vs_querygen"])+". This is a retrieval diagnostic, not proof that all information was retained or that the case is intrinsically insensitive.","",assessment.get("failure_interpretation",""),"","## Research category","",f"{assessment['category']}: {assessment['hypothesis_status']}. "+assessment["reasoning"]])
    analysis += ["", "## Audit verification limits", "", f"There were {audit['evidence_or_excerpt_validation_note_count']} date/path/excerpt verification notes. Invalid daily-observation paths and unverifiable retained/contradicted excerpts downgrade the affected checks to uncertain; these are auditor limitations, not evidence that a baseline omitted the fact. Model status, corrected status and original response remain available for review. No post-outcome quotation repair or semantic relabelling was used to improve the hypothesis result."]
    (root/"FAILURE_ANALYSIS.md").write_text("\n".join(analysis)+"\n",encoding="utf-8")
    truncation=Counter((r["baseline_id"],bool(r["metadata"].get("truncated"))) for r in reps)
    corpus_sources=Counter(i["source"] for i in corpus)
    validity=["# Validity Notes","","## Five material threats","","1. Provisional annotation: two LLM judges plus one LLM adjudicator are not independent human or clinical ground truth. Generator, both judges, adjudicator and semantic auditor use separate fresh contexts of the same Qwen model alias and therefore share weights. Their errors can be correlated. Agreement is reliability, not correctness; gold-driven retention audits inherit label errors.","","2. Corpus/source identification: 96 atomic items derive from clustered authority sources and include many context-dependent educational items. Unsupported RHR/HRV conjunctions are absent. Some matched differences can concern generic or device-context relevance rather than the intended axis. Never infer that a matched score difference proves the planned distinction.","","3. Synthetic small sample: 24 cases, 19 construction units and three repeated generations do not represent a natural wearable population. Numerical estimates, idealized timing and deterministic noise limit external validity. No real intervention or clinical effect is measured.","","4. Resource and truncation confounds: B3 uses five retrieval operations; B1/B2/B4 use one. B1-B3 final text is capped at 256 cl100k tokens; hard post-generation truncation can remove information. B4 is a much longer deterministic reference and is subject to identical 512 lexical-token and 512 dense-subword truncation. Qwen API parameters temperature=0, enable_thinking=false and max_tokens=16384 are fixed for all roles. Provider sampling seed support is not assumed. The fixed model alias does not pin immutable provider weights; repeat generation can still differ despite temperature 0.","","5. Retrieval and audit dependence: English regex BM25 and pinned BGE-M3 each impose format preferences. Low top-k recall does not prove information loss. Semantic audits use one LLM, are incompletely blinded to writing style, and cover selected positive-label facts. No proposed Personal Evidence representation is evaluated; additional information might still add noise.","","## Recorded controls","","All baseline inputs use the same raw/derived-statistics whitelist. No corpus, labels, categories or designer notes were visible during generation. Judges saw source-supported items and raw data only, with randomized opaque references. Corpus corrections occurred before annotation and retrieval; post-result changes are prohibited. API calls do not expose tools and reject tool-use responses. Missing values are not zero. All five matched constraints and statistics were independently recomputed.","",f"Execution revision: `{experiment['revision']}`. Authorized Qwen API endpoint: `{experiment['llm']['base_url']}`. Provider request IDs, returned model names and actual usage are preserved; no aborted archived Codex output contributes to this run.","","Final representation truncation counts: "+str({b:truncation[(b,True)] for b in NAMES})+" out of 72 records per baseline (B4 has no generation budget).","","Corpus source counts: "+str(dict(corpus_sources))+". Corpus verification means fetched sources, anchors, schema checks and independent fresh context LLM source review; no human expert review.","","Cumulative recorded Qwen response budget: "+str(api_usage["totals"])+". "+api_usage["coverage"]+". "+api_usage["retry_caveat"],"","## Scope of conclusion","",assessment["reasoning"],"","A negative result is allowed. No benchmark, prompt, corpus condition, threshold or hypothesis interpretation was changed to rescue C1 after retrieval results. Improvements to code address runtime/correctness defects; any new experimental comparison must be a separately declared run."]
    validity.insert(2, "Labels: **PROVISIONAL_LLM_GOLD**. Semantic audits: **PROVISIONAL_LLM_AUDIT**. Research synthesis: **PROVISIONAL_LLM_RESEARCH_SYNTHESIS**.")
    validity += ["", "## Runtime history", "", "See `EXECUTION_HISTORY.md` and the hash-recorded amendments in `data/input_freeze.json` for the public endpoint correction, short-reference annotation restart, and discarded generation batch. The frozen protocol's historical workspace/opaque-hash wording is not a description of the final transport. Empty representation slots are rejected and may be retried within two attempts, unlike design-v1's empty-candidates rule; no such empty response was observed in retained generation records. Four-case generation batching and large provider-native contexts also limit independence and cost comparability."]
    validity += ["", "B4 matched-pair candidate identity is a result of this fixed representation/retriever setup, not proof that every factual representation is intrinsically unable to discriminate. Its long ledger is truncated at retrieval input; paired baseline histories are equal, so the early query portion can conceal later window differences. B4's dense mean nDCG is only slightly above Insight-style; inspect the saved paired intervals rather than calling this a reliable format advantage."]
    (root/"VALIDITY_NOTES.md").write_text("\n".join(validity)+"\n",encoding="utf-8")
    write_json(ROOT/"outputs/metrics/final_summary.json",{"assessment":assessment,"overall_metrics":overall,"judge_agreement":agreement,"case_count":24,"knowledge_count":96,"provisional_label_count":2304,"retrieval_runs":576,"top_five_failure_cases":failure["top_five_failure_candidates"],"matched_pair_gold_differences":{ '/'.join(p['pair']):p['gold_different_item_count'] for p in matched},"knowledge_group_diagnostics":knowledge_groups,"qwen_api_usage":api_usage,"recall_denominator_ceilings":recall_ceilings,"model_parameters":{"backend":experiment["llm"]["backend"],"base_url":experiment["llm"]["base_url"],"model_alias":experiment["llm"]["generator_model"],"temperature":experiment["llm"]["temperature"],"enable_thinking":experiment["llm"]["enable_thinking"],"max_tokens":experiment["llm"]["max_tokens"],"shared_model_weights":True}})
    print("Rendered PILOT_RESULTS.md, FAILURE_ANALYSIS.md, VALIDITY_NOTES.md from completed outputs",flush=True)


if __name__=="__main__": main()
