"""Save reviewable per-case failures and cautious, non-semantic retention probes."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
from statistics import mean

from evaluate import (LABEL_KIND, METRICS, average_defined, case_level_results,
                      load_retrieval_results, matched_pair_analysis, ranking_metrics, read_gold)
from retrieval import read_jsonl, tokenize, write_json


METRIC_ALIASES = {
    "sleep_duration_minutes": ["sleep", "night", "duration"],
    "steps": ["steps", "walking", "step"],
    "activity_duration_minutes": ["activity", "exercise", "movement"],
    "low_movement_minutes": ["low movement", "inactivity", "sedentary", "sitting"],
    "resting_heart_rate_bpm": ["resting heart rate", "resting pulse", "rhr"],
    "hrv_rmssd_ms": ["hrv", "heart rate variability", "rmssd"],
}
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?")
FACT_PROBE_REVISION = "raw-fact-probes-v2"


def numeric_series(case: dict, period: str, metric: str) -> list[float | None]:
    return [record["metrics"].get(metric) for record in case["observations"][period + "_daily"]]


def defined_mean(values: list[float | None]) -> float | None:
    return average_defined(values)


def raw_facts(case: dict) -> list[dict]:
    """Arithmetic audit facts from observations, without intended-case or knowledge hints."""
    facts = []
    window = case["observations"]["window_daily"]
    baseline = case["observations"]["baseline_daily"]
    for metric, aliases in METRIC_ALIASES.items():
        before = numeric_series(case, "baseline", metric)
        current = numeric_series(case, "window", metric)
        before_mean, current_mean = defined_mean(before), defined_mean(current)
        if current_mean is None:
            continue
        first_mean, last_mean = defined_mean(current[:7]), defined_mean(current[7:])
        facts.append({"fact_id": f"{metric}:baseline_comparison", "family": "baseline_comparison",
                      "metric": metric, "aliases": aliases, "baseline_mean": before_mean,
                      "window_mean": current_mean,
                      "mean_difference": current_mean - before_mean if before_mean is not None else None,
                      "probe_values": [value for value in [before_mean, current_mean] if value is not None]})
        facts.append({"fact_id": f"{metric}:ordered_halves", "family": "ordered_halves", "metric": metric,
                      "aliases": aliases, "first_7_mean": first_mean, "last_7_mean": last_mean,
                      "dated_values": [{"date": row["date"], "value": value} for row, value in zip(window, current)],
                      "probe_values": [value for value in [first_mean, last_mean] if value is not None]})
        weekday = [row["metrics"].get(metric) for row in window if date.fromisoformat(row["date"]).weekday() < 5]
        weekend = [row["metrics"].get(metric) for row in window if date.fromisoformat(row["date"]).weekday() >= 5]
        facts.append({"fact_id": f"{metric}:day_groups", "family": "day_groups", "metric": metric,
                      "aliases": aliases, "weekday_mean": defined_mean(weekday), "weekend_mean": defined_mean(weekend),
                      "probe_values": [value for value in [defined_mean(weekday), defined_mean(weekend)] if value is not None]})
        missing_dates = [row["date"] for row in window if row["metrics"].get(metric) is None]
        if missing_dates:
            facts.append({"fact_id": f"{metric}:missing", "family": "missing", "metric": metric,
                          "aliases": aliases, "missing_dates": missing_dates, "probe_values": [len(missing_dates)]})
    for timestamp_metric in ("sleep_start_at", "sleep_end_at"):
        minutes = []
        for row in window:
            value = row["metrics"].get(timestamp_metric)
            if value:
                parsed = datetime.fromisoformat(value)
                minutes.append((parsed.hour * 60 + parsed.minute - 720) % 1440)
        if minutes:
            facts.append({"fact_id": timestamp_metric + ":timing", "family": "sleep_timing",
                          "metric": timestamp_metric, "aliases": ["sleep", "bedtime", "wake", "timing", "schedule"],
                          "minutes_from_local_noon_min": min(minutes), "minutes_from_local_noon_max": max(minutes),
                          "range_minutes": max(minutes) - min(minutes), "probe_values": [max(minutes) - min(minutes)]})
    low_movement = []
    for row in window:
        intervals = row.get("low_movement_intervals", [])
        durations = [(datetime.fromisoformat(interval["end_at"]) - datetime.fromisoformat(interval["start_at"])).total_seconds() / 60
                     for interval in intervals]
        if durations:
            low_movement.append({"date": row["date"], "total_minutes": sum(durations),
                                 "longest_interval_minutes": max(durations), "interval_count": len(durations)})
    if low_movement:
        longest = mean(row["longest_interval_minutes"] for row in low_movement)
        facts.append({"fact_id": "low_movement:interval_structure", "family": "interval_structure",
                      "metric": "low_movement_minutes", "aliases": METRIC_ALIASES["low_movement_minutes"],
                      "mean_longest_interval_minutes": longest, "daily_interval_structure": low_movement,
                      "probe_values": [longest]})
    late_activity, other_activity = [], []
    activity_dates = []
    aligned_sleep = []
    by_date = {row["date"]: row for row in window}
    for row in window:
        next_date = (date.fromisoformat(row["date"]) + timedelta(days=1)).isoformat()
        sleep_row = by_date.get(next_date)
        sleep = sleep_row["metrics"].get("sleep_duration_minutes") if sleep_row else None
        intervals = row.get("activity_intervals", [])
        evening = any(datetime.fromisoformat(interval["start_at"]).hour >= 18 for interval in intervals)
        if sleep is not None:
            (late_activity if evening else other_activity).append(sleep)
            aligned_sleep.append({"activity_date": row["date"], "sleep_wake_date": next_date,
                                  "activity_starts_at_or_after_18_local": evening,
                                  "following_sleep_duration_minutes": sleep})
        if evening:
            activity_dates.append(row["date"])
    if activity_dates:
        facts.append({"fact_id": "activity_sleep:lag_one_alignment", "family": "multivariable_alignment",
                      "metric": "sleep_duration_minutes", "aliases": ["activity", "evening", "sleep", "exercise"],
                      "evening_activity_dates": activity_dates, "following_sleep_mean_with_evening_activity": defined_mean(late_activity),
                      "following_sleep_mean_without_evening_activity": defined_mean(other_activity),
                      "aligned_daily_records": aligned_sleep,
                      "alignment_note": "Activity onday t aligns with sleep attributed to its waking date t+1; 18:00 is a fixed descriptive grouping, not a medical threshold or causal claim",
                      "probe_values": [value for value in [defined_mean(late_activity), defined_mean(other_activity)] if value is not None]})
    rhr_before = [row["metrics"].get("resting_heart_rate_bpm") for row in baseline]
    hrv_before = [row["metrics"].get("hrv_rmssd_ms") for row in baseline]
    valid_rhr, valid_hrv = [value for value in rhr_before if value is not None], [value for value in hrv_before if value is not None]
    if valid_rhr and valid_hrv:
        higher_dates = [row["date"] for row in window if row["metrics"].get("resting_heart_rate_bpm") is not None
                        and row["metrics"]["resting_heart_rate_bpm"] > max(valid_rhr)]
        lower_dates = [row["date"] for row in window if row["metrics"].get("hrv_rmssd_ms") is not None
                       and row["metrics"]["hrv_rmssd_ms"] < min(valid_hrv)]
        facts.append({"fact_id": "rhr_hrv:date_overlap", "family": "multivariable_alignment",
                      "metric": "resting_heart_rate_bpm", "aliases": ["heart rate", "hrv", "variability", "rhr"],
                      "rhr_dates_above_observed_baseline_max": higher_dates,
                      "hrv_dates_below_observed_baseline_min": lower_dates,
                      "overlapping_dates": sorted(set(higher_dates) & set(lower_dates)),
                      "threshold_note": "Observed baseline extrema, not medical thresholds", "probe_values": []})
    return facts


def probe_retention(fact: dict, text: str) -> dict:
    """Token/number candidates are review aids, never semantic preservation verdicts."""
    folded = text.casefold()
    alias_hits = [alias for alias in fact["aliases"] if alias in folded]
    numbers = [float(match.replace(",", "")) for match in NUMBER_PATTERN.findall(text)]
    values = fact.get("probe_values", [])
    value_hits = []
    for value in values:
        alternatives = [value]
        if "minutes" in fact["metric"]:
            alternatives.append(value / 60)
        matched = any(abs(number - target) <= max(abs(target) * 0.025, 0.05) for number in numbers for target in alternatives)
        value_hits.append(matched)
    family = fact["family"]
    cues = {"baseline_comparison": ["baseline", "previous", "prior", "before", "usual", "increase", "decrease", "rose", "fell", "changed", "stable"],
            "ordered_halves": ["first", "last", "then", "later", "second", "returned", "recover", "four", "consecutive"],
            "day_groups": ["weekday", "weekend", "workday", "weekdays", "weekends"],
            "missing": ["missing", "coverage", "unavailable", "null", "not zero"],
            "sleep_timing": ["timing", "regular", "bedtime", "wake", "schedule"],
            "interval_structure": ["bout", "block", "continuous", "uninterrupted", "break", "interval", "long", "fragment"],
            "multivariable_alignment": ["same", "together", "overlap", "aligned", "coincid", "evening", "following", "separate", "different", "nonoverlap"]}
    cue_hits = [cue for cue in cues.get(family, []) if cue in folded]
    candidate = bool(alias_hits and (cue_hits or (value_hits and all(value_hits))))
    return {"fact_id": fact["fact_id"], "lexical_retention_candidate": candidate,
            "alias_hits": alias_hits, "relation_cue_hits": cue_hits, "numeric_value_hits": value_hits,
            "interpretation": "requires semantic review; absence does not prove compression loss and presence does not prove correctness"}


def linked_items(fact: dict, items: dict[str, dict], gold: dict[str, int]) -> list[dict]:
    links = []
    for item_id, label in gold.items():
        if label == 0:
            continue
        item = items[item_id]
        text = (item["title"] + " " + item["content"] + " " + json.dumps(item.get("applicability", {}))).casefold()
        aliases = [alias for alias in fact["aliases"] if alias in text]
        if aliases:
            links.append({"knowledge_id": item_id, "relevance": label, "shared_aliases": aliases,
                          "link_kind": "lexical applicability candidate, not an adjudicated fact-to-item dependency"})
    return links


def recovery_noise_analysis(results: list[dict], gold: dict[str, int]) -> list[dict]:
    by_run = {(record["retriever"], str(record["repeat_id"]), record["baseline_id"]): record for record in results}
    positives = {item_id for item_id, label in gold.items() if label >= 1}
    strong = {item_id for item_id, label in gold.items() if label == 2}
    findings = []
    for retriever, repeat in sorted({key[:2] for key in by_run}):
        querygen = by_run.get((retriever, repeat, "B3"))
        if querygen is None:
            continue
        querygen_ids = {item["knowledge_id"] for item in querygen["ranking"][:10]}
        for baseline in ("B1", "B2"):
            compared = by_run.get((retriever, repeat, baseline))
            if compared is None:
                continue
            compared_ids = {item["knowledge_id"] for item in compared["ranking"][:10]}
            recovered = querygen_ids - compared_ids
            lost = compared_ids - querygen_ids
            findings.append({"retriever": retriever, "repeat_id": repeat, "compared_baseline": baseline,
                             "summary_insight_false_negatives_recovered_by_querygen": sorted(recovered & positives),
                             "strong_false_negatives_recovered_by_querygen": sorted(recovered & strong),
                             "relevant_items_lost_by_querygen": sorted(lost & positives),
                             "strong_items_lost_by_querygen": sorted(lost & strong),
                             "querygen_additional_irrelevant_items": sorted(recovered - positives),
                             "summary_insight_additional_irrelevant_items": sorted(lost - positives)})
    return findings


def run(cases_path: Path, corpus_path: Path, labels_path: Path, representations_path: Path,
        retrieval_dir: Path, output_dir: Path, semantic_audit_dir: Path | None = None) -> dict:
    cases = {case["id"]: case for case in read_jsonl(cases_path)}
    items = {item["id"]: item for item in read_jsonl(corpus_path)}
    gold = read_gold(labels_path, set(cases), set(items))
    representations = read_jsonl(representations_path)
    results = load_retrieval_results(retrieval_dir)
    _, case_metrics = case_level_results(cases, results, gold)
    matched = matched_pair_analysis(results, gold, case_metrics)
    rep_by_case, runs_by_case = defaultdict(list), defaultdict(list)
    for representation in representations:
        rep_by_case[representation["case_id"]].append(representation)
    for result in results:
        runs_by_case[result["case_id"]].append(result)
    output_dir.mkdir(parents=True, exist_ok=True)
    semantic_audit_dir = semantic_audit_dir or output_dir / "semantic_audit"
    semantic_audit_cases = []
    summaries = []
    probe_totals = defaultdict(lambda: {"facts_probed": 0, "lexical_candidates": 0})
    for case_id, case in sorted(cases.items()):
        facts = raw_facts(case)
        for fact in facts:
            fact["provisionally_relevant_item_links"] = linked_items(fact, items, gold[case_id])
        rep_analysis = []
        for representation in rep_by_case[case_id]:
            text = "\n".join(representation.get("queries", [])) if representation["baseline_id"] == "B3" else representation.get("text", "")
            probes = [probe_retention(fact, text) for fact in facts]
            baseline = representation["baseline_id"]
            probe_totals[baseline]["facts_probed"] += len(probes)
            probe_totals[baseline]["lexical_candidates"] += sum(probe["lexical_retention_candidate"] for probe in probes)
            rep_analysis.append({"representation": representation, "lexical_token_count": len(tokenize(text)), "retention_probes": probes})
        retrieval = []
        for result in runs_by_case[case_id]:
            metrics = ranking_metrics(result["ranking"], gold[case_id])
            enriched = [{**candidate, "gold_relevance": gold[case_id][candidate["knowledge_id"]],
                         "title": items[candidate["knowledge_id"]]["title"],
                         "source_url": items[candidate["knowledge_id"]]["source_url"]} for candidate in result["ranking"]]
            retrieval.append({"retriever": result["retriever"], "baseline_id": result["baseline_id"],
                              "repeat_id": result["repeat_id"], "retrieved_top_k": enriched,
                              "metrics": {metric: metrics[metric] for metric in METRICS},
                              "false_negatives_at_10": metrics["false_negatives_at_10"],
                              "strong_false_negatives_at_10": metrics["strong_false_negatives_at_10"],
                              "false_positives_at_10": metrics["false_positives_at_10"]})
        record = {"case_id": case_id, "label_kind": LABEL_KIND, "raw_data": case,
                  "gold_relevance": gold[case_id], "raw_fact_table": facts,
                  "baseline_outputs": rep_analysis, "retrieval": retrieval,
                  "querygen_recovery_and_noise": recovery_noise_analysis(runs_by_case[case_id], gold[case_id]),
                  "audit_limit": "The automatic lexical probes cannot establish semantic information loss or hallucination; inspect text and raw evidence"}
        semantic_path = semantic_audit_dir / f"{case_id}.json"
        if semantic_path.exists():
            semantic_record = json.loads(semantic_path.read_text(encoding="utf-8-sig"))
            if semantic_record.get("case_id") != case_id or semantic_record.get("audit_kind") != "PROVISIONAL_LLM_AUDIT":
                raise ValueError(f"Invalid semantic audit checkpoint for {case_id}")
            record["semantic_audit"] = semantic_record
            semantic_audit_cases.append(case_id)
        write_json(output_dir / f"{case_id}.json", record)
        local = [row for row in case_metrics if row["case_id"] == case_id]
        method_comparisons = []
        for retriever in sorted({row["retriever"] for row in local}):
            by_baseline = {row["baseline_id"]: row for row in local if row["retriever"] == retriever}
            if {"B1", "B2", "B3"} <= by_baseline.keys():
                querygen = by_baseline["B3"]["ndcg_at_10"]
                summaries_best = average_defined([max(value for value in [by_baseline["B1"]["ndcg_at_10"], by_baseline["B2"]["ndcg_at_10"]] if value is not None)]) if any(by_baseline[key]["ndcg_at_10"] is not None for key in ("B1", "B2")) else None
                querygen_gain = querygen - summaries_best if querygen is not None and summaries_best is not None else None
                method_comparisons.append({"retriever": retriever, "querygen_minus_best_summary_insight_ndcg": querygen_gain,
                                           "querygen_recovers_practically_visible_gain": querygen_gain is not None and querygen_gain >= 0.05,
                                           "metrics": {baseline: {metric: row[metric] for metric in METRICS}
                                                       for baseline, row in by_baseline.items()}})
        average_summary_strong_miss = average_defined([1 - row["strong_recall_at_10"] for row in local if row["baseline_id"] in {"B1", "B2"} and row["strong_recall_at_10"] is not None])
        summaries.append({"case_id": case_id, "stratum": case["designer_notes"]["stratum"],
                          "case_type": case["case_type"], "average_summary_insight_strong_miss_fraction": average_summary_strong_miss,
                          "methods": method_comparisons,
                          "no_observed_summary_insight_penalty_vs_querygen": bool(method_comparisons) and all(
                              comparison["querygen_minus_best_summary_insight_ndcg"] is not None and
                              comparison["querygen_minus_best_summary_insight_ndcg"] < 0.05 for comparison in method_comparisons)})
    ranked_failures = sorted(summaries, key=lambda row: (-(row["average_summary_insight_strong_miss_fraction"] or 0), row["case_id"]))
    aggregate = {"label_kind": LABEL_KIND, "fact_probe_revision": FACT_PROBE_REVISION,
                 "top_five_failure_candidates": [row["case_id"] for row in ranked_failures[:5]],
                 "failure_selection_rule": "Largest mean Summary/Insight strong false-negative fraction across retrievers, ties by case ID",
                 "per_case": summaries, "matched_pairs": matched, "lexical_retention_probe_totals": dict(probe_totals),
                 "sensitive_design_cases_without_observed_penalty_vs_querygen": [row["case_id"] for row in summaries if row["stratum"] == "B" and row["no_observed_summary_insight_penalty_vs_querygen"]],
                 "limitations": ["No automatic semantic or medical truth adjudication", "Lexical fact probes are review aids only",
                                 "More output tokens and more irrelevant candidates do not establish a causal noise mechanism",
                                 "QueryGen has five retrieval calls; its advantage cannot be attributed solely to representation format",
                                 "Identical matched-pair gold cannot validate retrieval sensitivity to the target construction axis"]}
    aggregate["semantic_audit_available_for_cases"] = semantic_audit_cases
    semantic_summary_path = semantic_audit_dir / "summary.json"
    if semantic_summary_path.exists():
        aggregate["semantic_audit_summary"] = json.loads(semantic_summary_path.read_text(encoding="utf-8-sig"))
    write_json(output_dir / "analysis_summary.json", aggregate)
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--representations", type=Path, required=True)
    parser.add_argument("--retrieval-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--semantic-audit-dir", type=Path)
    args = parser.parse_args()
    result = run(args.cases, args.corpus, args.labels, args.representations, args.retrieval_dir, args.output_dir, args.semantic_audit_dir)
    print(json.dumps({"case_count": len(result["per_case"]), "top_five_failure_candidates": result["top_five_failure_candidates"]}))


if __name__ == "__main__":
    main()
