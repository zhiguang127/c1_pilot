"""Human-Gold-gated evaluation. Unjudged knowledge never becomes a negative."""
from collections import Counter, defaultdict
from math import log2
from pathlib import Path
import random

from .common import LABELS, private_path, read, rows, verify, write, write_rows
from .data import candidates, evidence_value

ERROR_TYPES = ("retrieval_failure", "temporal_reasoning_failure", "condition_matching_failure",
               "missing_information_failure", "knowledge_scope_failure", "annotation_ambiguity")


def classification(gold, predicted):
    counts = Counter(zip(gold, predicted))
    classes = {}
    for label in LABELS:
        tp = counts[label, label]
        support = sum(a == label for a in gold)
        positive = sum(b == label for b in predicted)
        precision = tp/positive if positive else 0.0
        recall = tp/support if support else 0.0
        classes[label] = {"precision": precision, "recall": recall,
                          "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.0,
                          "support": support}
    not_applicable = sum(a != "applicable" for a in gold)
    false_app = sum(a != "applicable" and b == "applicable" for a, b in zip(gold, predicted))
    app_predictions = sum(b == "applicable" for b in predicted)
    return {"n": len(gold), "macro_f1_fixed_three_classes": sum(c["f1"] for c in classes.values())/3,
            "classes": classes, "confusion": {a: {b: counts[a, b] for b in LABELS} for a in LABELS},
            "false_applicability_rate": false_app/not_applicable if not_applicable else None,
            "false_applicability_denominator": not_applicable,
            "false_discovery_among_applicable_predictions": false_app/app_predictions if app_predictions else None,
            "unknown_detection_rate": classes["insufficient_information"]["recall"] if classes["insufficient_information"]["support"] else None,
            "missing_condition_error_rate": None,
            "missing_condition_note": "Requires separately adjudicated necessary-condition and error annotations"}


def trusted_gold(directory, release_id):
    directory = private_path(directory)
    verify(directory)
    provenance = read(directory / "provenance.json")
    if provenance["data_release_id"] != release_id or provenance["gold_kind"] != "INDEPENDENT_HUMAN_DOUBLE_REVIEW_ADJUDICATED":
        raise ValueError("Wrong release, provisional/model labels or unproven human Gold")
    records = rows(directory / "gold.jsonl")
    keys = [(g["case_id"], g["knowledge_id"]) for g in records]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate human Gold pair")
    return {key: row for key, row in zip(keys, records)}, provenance


def evaluate(stage, release, predictions, gold_dir, output, bootstrap=0):
    cases, knowledge, release_id = candidates(stage, release)
    if not gold_dir:
        result = {"status": "PENDING_HUMAN_ANNOTATION", "stage": stage, "data_release_id": release_id,
                  "formal_metrics": None, "gold_pairs": 0,
                  "reason": "No independent human applicability Gold; no synthetic or old Qwen labels substituted"}
        write(output, result)
        return result
    gold, provenance = trusted_gold(gold_dir, release_id)
    valid_pairs = {(c["case_id"], k) for c in cases for k in c["candidate_ids"]}
    if not gold.keys() <= valid_pairs:
        raise ValueError("Gold contains out-of-panel cases or knowledge")
    case_map = {c["case_id"]: c for c in cases}
    grouped = defaultdict(list)
    for p in rows(private_path(predictions)):
        if p["data_release_id"] != release_id:
            raise ValueError("Prediction data version mismatch")
        grouped[(p["method"], p["model"], p["information_view"])].append(p)
    methods = []
    for group, ps in grouped.items():
        keys = [(p["case_id"], p["knowledge_id"]) for p in ps]
        if len(keys) != len(set(keys)) or not set(keys) <= valid_pairs:
            raise ValueError("Duplicate or out-of-panel prediction")
        paired = [(gold[k], p) for k, p in zip(keys, ps) if k in gold and p["parse_status"] == "ok"]
        gvals, pvals = [g["applicability"] for g, _ in paired], [p["predicted_applicability"] for _, p in paired]
        report = {"method": group[0], "model": group[1], "information_view": group[2],
                  "gold_release_status": provenance["status"], "gold_coverage": len(gold)/len(valid_pairs),
                  "predicted_pairs": len(ps), "parse_failures": sum(p["parse_status"] != "ok" for p in ps),
                  "gold_pairs_without_valid_prediction": len(gold)-len(paired),
                  "conditional_on_valid_predictions": classification(gvals, pvals) if paired else None,
                  "participants": len({case_map[g["case_id"]]["subject_id"] for g, _ in paired})}
        by_subject = defaultdict(list)
        for g, p in paired:
            by_subject[case_map[g["case_id"]]["subject_id"]].append((g["applicability"], p["predicted_applicability"]))
        report["participant_descriptions"] = {s: classification([a for a, _ in vals], [b for _, b in vals]) for s, vals in sorted(by_subject.items())}
        if bootstrap and len(by_subject) >= 8 and set(gvals) == set(LABELS):
            rng, estimates = random.Random(20261016), []
            subjects = sorted(by_subject)
            for _ in range(bootstrap):
                sample = [pair for s in rng.choices(subjects, k=len(subjects)) for pair in by_subject[s]]
                estimates.append(classification([a for a, _ in sample], [b for _, b in sample])["macro_f1_fixed_three_classes"])
            estimates.sort()
            report["participant_cluster_bootstrap"] = {"replicates": bootstrap, "seed": 20261016,
                "percentile_95_interval": [estimates[int(.025*(bootstrap-1))], estimates[int(.975*(bootstrap-1))]],
                "note": "Exploratory with 16 participants; repeated windows are clustered, not iid pairs"}
        else:
            report["participant_cluster_bootstrap"] = None
        methods.append(report)
    result = {"status": "HUMAN_JUDGED_DESCRIPTIVE_RESULTS", "stage": stage, "data_release_id": release_id,
              "gold_pairs": len(gold), "expected_pairs": len(valid_pairs), "methods": methods,
              "evidence_correctness": None, "evidence_note": "Reference existence is software-checked, semantic/time/scope correctness needs human review"}
    write(output, result)
    return result


def retrieval_metrics(rankings, gold_dir, stage, release, output):
    cases, _, release_id = candidates(stage, release)
    gold, provenance = trusted_gold(gold_dir, release_id)
    by_case = defaultdict(dict)
    for (cid, kid), g in gold.items():
        by_case[cid][kid] = g
    result = []
    for r in rows(private_path(rankings)):
        judged = by_case.get(r["case_id"], {})
        relevant = {k for k, g in judged.items() if g["applicability"] == "applicable"}
        per_k = {}
        for k in (5, 10, 20):
            top = [p["knowledge_id"] for p in r["ranking"][:k]]
            known_top = [kid for kid in top if kid in judged]
            per_k[str(k)] = {"known_positive_recall": len(relevant.intersection(top))/len(relevant) if relevant else None,
                "known_positive_denominator": len(relevant), "topk_judged_coverage": len(known_top)/len(top) if top else None,
                "not_applicable_fraction_among_judged_topk": sum(judged[kid]["applicability"] == "not_applicable" for kid in known_top)/len(known_top) if known_top else None}
        # Restricted judged pool, explicitly remove unjudged positions. Not full-corpus nDCG.
        restricted = [p["knowledge_id"] for p in r["ranking"] if p["knowledge_id"] in judged][:10]
        dcg = sum((kid in relevant)/log2(i+2) for i, kid in enumerate(restricted))
        ideal = sum(1/log2(i+2) for i in range(min(len(relevant), 10)))
        result.append({"case_id": r["case_id"], "at_k": per_k,
                       "judged_pool_ndcg10": dcg/ideal if ideal else None,
                       "topic_relevance_available": all(g.get("topic_relevance") is not None for g in judged.values()) if judged else False})
    report = {"setting": "JUDGED_POOL_ONLY_NOT_FULL_CORPUS_RECALL", "gold_status": provenance["status"],
              "unjudged_are_negative": False, "per_case": result,
              "topic_relevance": "Separate human topic labels required; applicability never substitutes topic relevance"}
    write(output, report)
    return {"setting": report["setting"], "cases": len(result)}


def failure_queue(stage, release, predictions, gold_dir, output):
    output = private_path(output)
    _, _, release_id = candidates(stage, release)
    if not gold_dir:
        write(output, {"status": "PENDING_HUMAN_ANNOTATION", "gold_verified_errors": None,
                       "error_type_counts": {e: None for e in ERROR_TYPES}, "cases": [],
                       "note": "Model disagreement, parse failure and missing credentials are not Gold-verified research errors"})
        return {"status": "PENDING_HUMAN_ANNOTATION"}
    gold, _ = trusted_gold(gold_dir, release_id)
    queue = []
    for p in rows(private_path(predictions)):
        key = p["case_id"], p["knowledge_id"]
        if key in gold:
            queue.append({"case_id": key[0], "knowledge_id": key[1], "method": p["method"],
                          "gold": gold[key], "prediction": p,
                          "outcome": "parse_failure" if p["parse_status"] != "ok" else "success" if p["predicted_applicability"] == gold[key]["applicability"] else "error",
                          "failure_type": None, "alternative_explanation": None, "reviewed_by_human": False,
                          "repair_checks": {k: None for k in ("explicit_statistics", "prompt", "trialgpt", "pha_tools", "pha_trialgpt_combination")}})
    write(output, {"status": "PENDING_HUMAN_FAILURE_ATTRIBUTION", "records": queue,
                   "allowed_error_types": ERROR_TYPES, "error_type_counts": None,
                   "note": "Includes successes and errors; attribution is never guessed from label mismatch alone"})
    return {"review_records": len(queue)}
