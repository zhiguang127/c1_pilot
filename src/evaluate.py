"""Case-level evaluation against PROVISIONAL_LLM_GOLD; repetitions are not cases."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from itertools import combinations
import json
import math
from pathlib import Path
import random
from statistics import mean

from retrieval import read_jsonl, sha256_json, write_json


LABEL_KIND = "PROVISIONAL_LLM_GOLD"
MATCHED_PAIRS = [("C003", "C005"), ("C009", "C011"), ("C016", "C018"),
                 ("C021", "C023"), ("C022", "C024")]
METRICS = ["recall_at_5", "recall_at_10", "recall_at_20", "strong_recall_at_10",
           "ndcg_at_10", "irrelevant_fraction_at_10"]


def average_defined(values: list[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    return mean(defined) if defined else None


def read_gold(path: Path, case_ids: set[str], knowledge_ids: set[str]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {case_id: {} for case_id in case_ids}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            case_id, knowledge_id = row["case_id"], row["knowledge_id"]
            if case_id not in case_ids or knowledge_id not in knowledge_ids:
                raise ValueError(f"Unknown gold pair {case_id}/{knowledge_id}")
            if knowledge_id in result[case_id]:
                raise ValueError(f"Duplicate gold pair {case_id}/{knowledge_id}")
            if row["relevance"] not in {"0", "1", "2"}:
                raise ValueError(f"Unresolved relevance for {case_id}/{knowledge_id}")
            if row.get("label_kind", LABEL_KIND) != LABEL_KIND:
                raise ValueError("Pilot labels must be identified as PROVISIONAL_LLM_GOLD")
            result[case_id][knowledge_id] = int(row["relevance"])
    missing = [(case_id, item_id) for case_id in sorted(case_ids)
               for item_id in sorted(knowledge_ids - result[case_id].keys())]
    if missing:
        raise ValueError(f"Incomplete label matrix: {len(missing)} missing pairs, first={missing[0]}")
    return result


def ranking_metrics(ranking: list[dict], gold: dict[str, int]) -> dict:
    ids = [item["knowledge_id"] for item in ranking]
    if any(item.get("rank") != position for position, item in enumerate(ranking, start=1)):
        raise ValueError("Candidate ranks must be consecutive and agree with list order")
    if len(ids) != len(set(ids)):
        raise ValueError("A candidate list contains duplicate knowledge IDs")
    if any(item_id not in gold for item_id in ids):
        raise ValueError("Retrieved candidate has no gold relevance label")
    positive_ids = {item_id for item_id, label in gold.items() if label >= 1}
    strong_ids = {item_id for item_id, label in gold.items() if label == 2}
    result = {f"recall_at_{k}": len(set(ids[:k]) & positive_ids) / len(positive_ids)
              if positive_ids else None for k in (5, 10, 20)}
    result["strong_recall_at_10"] = len(set(ids[:10]) & strong_ids) / len(strong_ids) if strong_ids else None
    gains = [2 ** gold[item_id] - 1 for item_id in ids[:10]]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal_gains = sorted((2 ** label - 1 for label in gold.values()), reverse=True)[:10]
    idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal_gains))
    result["ndcg_at_10"] = dcg / idcg if idcg else None
    result["irrelevant_fraction_at_10"] = sum(gold[item_id] == 0 for item_id in ids[:10]) / len(ids[:10]) if ids[:10] else None
    result.update({"empty_result": int(not ids), "returned_count": len(ids),
                   "returned_at_10": len(ids[:10]), "positive_count": len(positive_ids),
                   "strong_count": len(strong_ids), "false_positives_at_10": [item_id for item_id in ids[:10] if gold[item_id] == 0],
                   "false_negatives_at_10": sorted(positive_ids - set(ids[:10])),
                   "strong_false_negatives_at_10": sorted(strong_ids - set(ids[:10]))})
    return result


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields if fields is not None else list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def load_retrieval_results(directory: Path) -> list[dict]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("Missing retrieval manifest; cannot verify frozen corpus/config")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    results = []
    for name in manifest["retrievers_completed"]:
        records = read_jsonl(directory / f"{name}.jsonl")
        for record in records:
            if record["retriever"] != name or record["config_sha256"] != manifest["config_sha256"]:
                raise ValueError("Result retriever/config fingerprint disagrees with manifest")
            if record["corpus_sha256"] != manifest["corpus_sha256"]:
                raise ValueError("Result corpus fingerprint disagrees with manifest")
        results.extend(records)
    if not results:
        raise ValueError("No completed retrieval results")
    return results


def case_level_results(cases: dict[str, dict], results: list[dict], gold: dict[str, dict[str, int]]) -> tuple[list[dict], list[dict]]:
    repeated: dict[tuple, list[dict]] = defaultdict(list)
    seen: set[tuple] = set()
    run_rows = []
    for record in results:
        case_id = record["case_id"]
        if case_id not in cases:
            raise ValueError(f"Unknown result case {case_id}")
        key = (record["retriever"], record["baseline_id"], case_id, str(record["repeat_id"]))
        if key in seen:
            raise ValueError(f"Duplicate retrieval run {key}")
        seen.add(key)
        case = cases[case_id]
        metrics = ranking_metrics(record["ranking"], gold[case_id])
        row = {"retriever": key[0], "baseline_id": key[1], "case_id": case_id,
               "repeat_id": record["repeat_id"], "stratum": case["designer_notes"]["stratum"],
               "case_type": case["case_type"], "label_kind": LABEL_KIND, **metrics}
        run_rows.append(row)
        repeated[key[:3]].append(row)
    methods = {(record["retriever"], record["baseline_id"]) for record in results}
    for retriever, baseline in methods:
        absent = set(cases) - {key[2] for key in repeated if key[:2] == (retriever, baseline)}
        if absent:
            raise ValueError(f"Missing retrieval cases for {retriever}/{baseline}: {sorted(absent)}")
        repeat_sets = [{key[3] for key in seen if key[:3] == (retriever, baseline, case_id)} for case_id in cases]
        if any(repeats != repeat_sets[0] for repeats in repeat_sets):
            raise ValueError(f"Unequal repeat sets across cases for {retriever}/{baseline}")
    aggregated = []
    for (retriever, baseline, case_id), rows in sorted(repeated.items()):
        first = rows[0]
        row = {"retriever": retriever, "baseline_id": baseline, "case_id": case_id,
               "stratum": first["stratum"], "case_type": first["case_type"], "label_kind": LABEL_KIND,
               "repeat_count": len(rows), "positive_count": first["positive_count"], "strong_count": first["strong_count"]}
        for metric in METRICS:
            row[metric] = average_defined([value[metric] for value in rows])
            row[metric + "_valid_repeats"] = sum(value[metric] is not None for value in rows)
        row["empty_rate"] = mean(value["empty_result"] for value in rows)
        row["returned_count"] = mean(value["returned_count"] for value in rows)
        aggregated.append(row)
    return run_rows, aggregated


def summarize(case_rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in case_rows:
        for grouping, value in (("overall", "all"), ("stratum", row["stratum"]), ("case_type", row["case_type"])):
            grouped[(row["retriever"], row["baseline_id"], grouping, value)].append(row)
    summary = []
    for (retriever, baseline, grouping, value), rows in sorted(grouped.items()):
        record = {"retriever": retriever, "baseline_id": baseline, "grouping": grouping,
                  "group": value, "label_kind": LABEL_KIND, "case_count": len(rows),
                  "all_zero_cases": sum(row["positive_count"] == 0 for row in rows),
                  "no_strong_cases": sum(row["strong_count"] == 0 for row in rows),
                  "empty_rate": mean(row["empty_rate"] for row in rows)}
        for metric in METRICS:
            record[metric] = average_defined([row[metric] for row in rows])
            record[metric + "_valid_cases"] = sum(row[metric] is not None for row in rows)
        summary.append(record)
    return summary


def construction_clusters(case_ids: set[str]) -> list[list[str]]:
    paired = set()
    clusters = []
    for left, right in MATCHED_PAIRS:
        if left in case_ids and right in case_ids:
            clusters.append([left, right])
            paired.update([left, right])
    clusters.extend([[case_id] for case_id in sorted(case_ids - paired)])
    return clusters


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower) if lower != upper else ordered[lower]


def cluster_bootstrap(differences: dict[str, float], clusters: list[list[str]], iterations: int = 10000, seed: int = 1729) -> dict:
    usable = [[differences[case_id] for case_id in cluster if case_id in differences] for cluster in clusters]
    usable = [cluster for cluster in usable if cluster]
    if not usable:
        return {"mean_difference": None, "lower_95": None, "upper_95": None, "case_count": 0,
                "cluster_count": 0, "iterations": iterations, "seed": seed}
    random_source = random.Random(seed)
    samples = []
    for _ in range(iterations):
        sampled = [value for _ in usable for value in random_source.choice(usable)]
        samples.append(mean(sampled))
    return {"mean_difference": mean(differences.values()), "lower_95": percentile(samples, 0.025),
            "upper_95": percentile(samples, 0.975), "case_count": len(differences),
            "cluster_count": len(usable), "construction_cluster_count": len(clusters),
            "iterations": iterations, "seed": seed,
            "scope": "case-weighted, synthetic pilot only; resample whole construction clusters"}


def paired_comparisons(case_rows: list[dict], iterations: int, seed: int) -> tuple[list[dict], list[dict]]:
    by_key = {(row["retriever"], row["baseline_id"], row["case_id"]): row for row in case_rows}
    rows, intervals = [], []
    retrievers = sorted({row["retriever"] for row in case_rows})
    for retriever in retrievers:
        methods = sorted({row["baseline_id"] for row in case_rows if row["retriever"] == retriever})
        cases = {row["case_id"] for row in case_rows if row["retriever"] == retriever}
        clusters = construction_clusters(cases)
        for baseline_a, baseline_b in combinations(methods, 2):
            for metric in METRICS:
                differences = {}
                for case_id in sorted(cases):
                    value_a = by_key[(retriever, baseline_a, case_id)][metric]
                    value_b = by_key[(retriever, baseline_b, case_id)][metric]
                    difference = value_b - value_a if value_a is not None and value_b is not None else None
                    rows.append({"retriever": retriever, "baseline_a": baseline_a, "baseline_b": baseline_b,
                                 "case_id": case_id, "metric": metric, "value_a": value_a, "value_b": value_b,
                                 "difference_b_minus_a": difference})
                    if difference is not None:
                        differences[case_id] = difference
                intervals.append({"retriever": retriever, "baseline_a": baseline_a, "baseline_b": baseline_b,
                                  "metric": metric, **cluster_bootstrap(differences, clusters, iterations, seed)})
    return rows, intervals


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


def matched_pair_analysis(results: list[dict], gold: dict[str, dict[str, int]], case_rows: list[dict]) -> list[dict]:
    by_run = {(row["retriever"], row["baseline_id"], row["case_id"], str(row["repeat_id"])): row for row in results}
    methods = sorted({key[:2] for key in by_run})
    case_lookup = {(row["retriever"], row["baseline_id"], row["case_id"]): row for row in case_rows}
    report = []
    for left, right in MATCHED_PAIRS:
        if left not in gold or right not in gold:
            continue
        differences = [{"knowledge_id": item_id, "left_relevance": gold[left][item_id],
                        "right_relevance": gold[right][item_id]} for item_id in sorted(gold[left])
                       if gold[left][item_id] != gold[right][item_id]]
        pair = {"pair": [left, right], "label_kind": LABEL_KIND, "gold_differences": differences,
                "gold_different_item_count": len(differences),
                "retrieval_identifiable": bool(differences),
                "interpretation": "Matched gold has conditional distinctions" if differences else
                                  "Identical provisional labels: retrieval cannot identify the target distinction", "methods": []}
        for retriever, baseline in methods:
            left_repeats = {key[3] for key in by_run if key[:3] == (retriever, baseline, left)}
            right_repeats = {key[3] for key in by_run if key[:3] == (retriever, baseline, right)}
            if left_repeats != right_repeats:
                raise ValueError(f"Unpaired repetitions in {left}/{right}/{retriever}/{baseline}")
            runs = []
            for repeat in sorted(left_repeats):
                left_ids = [item["knowledge_id"] for item in by_run[(retriever, baseline, left, repeat)]["ranking"]]
                right_ids = [item["knowledge_id"] for item in by_run[(retriever, baseline, right, repeat)]["ranking"]]
                local = {"repeat_id": repeat, "left_top10": left_ids[:10], "right_top10": right_ids[:10],
                         "candidate_jaccard_at_10": jaccard(set(left_ids[:10]), set(right_ids[:10])),
                         "candidate_jaccard_at_20": jaccard(set(left_ids[:20]), set(right_ids[:20])),
                         "top10_same_order": left_ids[:10] == right_ids[:10],
                         "candidate_only_left_at_10": sorted(set(left_ids[:10]) - set(right_ids[:10])),
                         "candidate_only_right_at_10": sorted(set(right_ids[:10]) - set(left_ids[:10]))}
                local["conditional_item_retrieval"] = [{**difference,
                    "left_retrieved_at_10": difference["knowledge_id"] in left_ids[:10],
                    "right_retrieved_at_10": difference["knowledge_id"] in right_ids[:10]} for difference in differences]
                runs.append(local)
            left_metrics = case_lookup[(retriever, baseline, left)]
            right_metrics = case_lookup[(retriever, baseline, right)]
            pair["methods"].append({"retriever": retriever, "baseline_id": baseline,
                                    "mean_candidate_jaccard_at_10": mean(run["candidate_jaccard_at_10"] for run in runs),
                                    "mean_candidate_jaccard_at_20": mean(run["candidate_jaccard_at_20"] for run in runs),
                                    "any_candidate_change_at_10": any(run["candidate_jaccard_at_10"] < 1 for run in runs),
                                    "left_metrics": {metric: left_metrics[metric] for metric in METRICS},
                                    "right_metrics": {metric: right_metrics[metric] for metric in METRICS}, "runs": runs})
        report.append(pair)
    return report


def knowledge_group_breakdown(results: list[dict], gold: dict[str, dict[str, int]], corpus: list[dict]) -> tuple[list[dict], list[dict]]:
    groups = {"measurement_quality": {item["id"] for item in corpus if item["domain"] == "measurement_quality"},
              "personal_monitoring": {item["id"] for item in corpus if item["domain"] == "personal_monitoring"},
              "behavior_and_context": {item["id"] for item in corpus if item["domain"] not in {"measurement_quality", "personal_monitoring"}}}
    metrics = ["recall_at_10", "strong_recall_at_10", "top10_group_share", "within_group_irrelevant_fraction_at_10"]
    by_case = defaultdict(list)
    for result in results:
        case_id = result["case_id"]
        top10 = [candidate["knowledge_id"] for candidate in result["ranking"][:10]]
        for group, item_ids in groups.items():
            returned = [item_id for item_id in top10 if item_id in item_ids]
            positives = {item_id for item_id in item_ids if gold[case_id][item_id] >= 1}
            strong = {item_id for item_id in item_ids if gold[case_id][item_id] == 2}
            by_case[(result["retriever"], result["baseline_id"], case_id, group)].append({
                "recall_at_10": len(set(returned) & positives) / len(positives) if positives else None,
                "strong_recall_at_10": len(set(returned) & strong) / len(strong) if strong else None,
                "top10_group_share": len(returned) / len(top10) if top10 else None,
                "within_group_irrelevant_fraction_at_10": sum(gold[case_id][item_id] == 0 for item_id in returned) / len(returned) if returned else None,
                "positive_count": len(positives), "strong_count": len(strong), "returned_count": len(returned)})
    case_rows = []
    grouped = defaultdict(list)
    for (retriever, baseline, case_id, group), repeated in sorted(by_case.items()):
        row = {"retriever": retriever, "baseline_id": baseline, "case_id": case_id, "knowledge_group": group,
               "positive_count": repeated[0]["positive_count"], "strong_count": repeated[0]["strong_count"],
               "returned_at_10": mean(item["returned_count"] for item in repeated)}
        row.update({metric: average_defined([item[metric] for item in repeated]) for metric in metrics})
        case_rows.append(row)
        grouped[(retriever, baseline, group)].append(row)
    overall = []
    for (retriever, baseline, group), rows in sorted(grouped.items()):
        row = {"retriever": retriever, "baseline_id": baseline, "knowledge_group": group,
               "label_kind": LABEL_KIND, "case_count": len(rows), "corpus_item_count": len(groups[group])}
        for metric in metrics:
            row[metric] = average_defined([item[metric] for item in rows])
            row[metric + "_valid_cases"] = sum(item[metric] is not None for item in rows)
        overall.append(row)
    return case_rows, overall


def run(cases_path: Path, corpus_path: Path, labels_path: Path, retrieval_dir: Path,
        output_dir: Path, bootstrap_iterations: int = 10000, bootstrap_seed: int = 1729) -> dict:
    cases_list = read_jsonl(cases_path)
    corpus = read_jsonl(corpus_path)
    cases = {case["id"]: case for case in cases_list}
    if len(cases) != len(cases_list):
        raise ValueError("Duplicate case IDs")
    if len({item["id"] for item in corpus}) != len(corpus):
        raise ValueError("Duplicate knowledge IDs")
    retrieval_manifest = json.loads((retrieval_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    if sha256_json(sorted(corpus, key=lambda item: item["id"])) != retrieval_manifest["corpus_sha256"]:
        raise ValueError("Current corpus differs from the corpus used for retrieval")
    gold = read_gold(labels_path, set(cases), {item["id"] for item in corpus})
    results = load_retrieval_results(retrieval_dir)
    run_rows, case_rows = case_level_results(cases, results, gold)
    summary = summarize(case_rows)
    comparisons, intervals = paired_comparisons(case_rows, bootstrap_iterations, bootstrap_seed)
    matched = matched_pair_analysis(results, gold, case_rows)
    group_cases, group_overall = knowledge_group_breakdown(results, gold, corpus)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "per_run.csv", run_rows)
    write_csv(output_dir / "per_case.csv", case_rows)
    write_csv(output_dir / "summary.csv", summary)
    write_csv(output_dir / "paired_comparisons.csv", comparisons)
    write_csv(output_dir / "cluster_bootstrap.csv", intervals)
    write_csv(output_dir / "knowledge_group_per_case.csv", group_cases)
    write_csv(output_dir / "knowledge_group_breakdown.csv", group_overall)
    write_json(output_dir / "matched_pairs.json", matched)
    metadata = {"label_kind": LABEL_KIND, "case_count": len(cases), "knowledge_count": len(corpus),
                "label_count": sum(len(labels) for labels in gold.values()), "run_count": len(run_rows),
                "case_aggregation": "mean within each case over repeats, then equal-weight case means",
                "independent_construction_units": len(construction_clusters(set(cases))),
                "all_zero_cases": sorted(case_id for case_id, labels in gold.items() if not any(labels.values())),
                "no_strong_cases": sorted(case_id for case_id, labels in gold.items() if 2 not in labels.values()),
                "na_policy": "Recall/strong recall/nDCG zero denominators and empty irrelevant fraction are N/A",
                "graded_gain": "2^relevance - 1", "discount": "log2(rank + 1)",
                "smallest_effect_reference_ndcg": 0.05,
                "knowledge_group_diagnostics": "Same globaltop10, no subgroup reranking; measurement_quality, personal_monitoring, and six behavior/context domains separately reported",
                "comparisons_status": "exploratory; the originally planned Personal Evidence comparison is not implemented"}
    write_json(output_dir / "evaluation_manifest.json", metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--retrieval-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=1729)
    args = parser.parse_args()
    print(json.dumps(run(args.cases, args.corpus, args.labels, args.retrieval_dir, args.output_dir,
                         args.bootstrap_iterations, args.bootstrap_seed)))


if __name__ == "__main__":
    main()
