"""Fail-closed, offline integrity and completion checks for the executed pilot."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re

import jsonschema

from case_statistics import model_input
from evaluate import METRICS, MATCHED_PAIRS, case_level_results, matched_pair_analysis, ranking_metrics, read_gold, summarize
from io_utils import ROOT, fingerprint, read_json, read_jsonl, write_json
from retrieval import normalize_config, reciprocal_rank_fusion, representation_queries, sha256_json, truncate_query
from validate_cases import validate_dataset

LABEL_KIND = "PROVISIONAL_LLM_GOLD"
CASE_IDS = {f"C{i:03d}" for i in range(1, 25)}
KNOWLEDGE_IDS = {f"K{i:03d}" for i in range(1, 97)}
BASELINES = {"B1", "B2", "B3", "B4"}
RETRIEVERS = {"bm25", "dense"}
DOMAINS = {"sleep_duration": 16, "sleep_timing": 16, "temporary_variation": 8,
           "daily_activity": 16, "low_movement": 12, "activity_sleep_context": 8,
           "personal_monitoring": 12, "measurement_quality": 8}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_index(records, fields, expected=None):
    """Reject duplicate, missing and extra keys instead of silently overwriting."""
    indexed = {}
    for record in records:
        key = tuple(record[field] for field in fields)
        require(key not in indexed, f"Duplicate {fields} key: {key}")
        indexed[key] = record
    if expected is not None:
        actual = set(indexed)
        require(actual == expected, f"Incomplete {fields} matrix: {len(expected - actual)} missing, "
                f"{len(actual - expected)} unexpected, {len(records)} records")
    return indexed


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)),
                f"Missing or duplicate CSV headings: {path}")
        rows = list(reader)
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            f"Malformed CSV row: {path}")
    return rows


def label_value(value, allow_null=False):
    if allow_null and value in (None, ""):
        return None
    require(type(value) is int or isinstance(value, str), f"Invalid label type: {value!r}")
    require(value in (0, 1, 2, "0", "1", "2"), f"Invalid label value: {value!r}")
    return int(value)


def annotation_value(row, allow_pending=False):
    pending = row.get("status") == "needs_review"
    value = label_value(row["relevance"], allow_null=allow_pending and pending)
    require((pending and allow_pending and value is None) or
            (row.get("status") == "labeled" and value is not None),
            "An annotation is unresolved or its status disagrees with relevance")
    return value


def csv_boolean(value):
    require(type(value) is bool or value in ("True", "False", "true", "false"), f"Invalid boolean: {value!r}")
    return value is True or value in ("True", "true")


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def check_annotation_revision(rows, expected_revision, context):
    require(rows and all(row.get("annotation_revision") == expected_revision for row in rows),
            f"{context} has missing, mixed or superseded annotation revisions; expected {expected_revision}")


def check_gold_annotation_revision(rows, metadata, expected_revision):
    require(rows and metadata.get("annotation_revision") == expected_revision,
            f"Gold producer metadata has a missing or superseded annotation revision; expected {expected_revision}")
    # The current producer writes a three-column gold CSV and its revision in metadata.
    if any("annotation_revision" in row for row in rows):
        check_annotation_revision(rows, expected_revision, "Gold CSV")


def validate_ranking(ranking, knowledge_ids=KNOWLEDGE_IDS, size=20):
    require(isinstance(ranking, list) and len(ranking) == size, f"Ranking must contain exactly {size} items")
    seen = set()
    order = []
    for rank, candidate in enumerate(ranking, 1):
        require(type(candidate["rank"]) is int and candidate["rank"] == rank, "Ranking ranks must be consecutive")
        item_id, score = candidate["knowledge_id"], candidate["score"]
        require(item_id in knowledge_ids and item_id not in seen, f"Unknown or duplicate candidate: {item_id}")
        require(type(score) in (int, float) and math.isfinite(score), "Ranking scores must be finite numbers")
        seen.add(item_id)
        order.append((-score, item_id))
    require(order == sorted(order), "Ranking violates descending score / knowledge_id ascending tie breaking")


def rankings_equal(actual, expected):
    require(len(actual) == len(expected), "Ranking size does not match recomputed fusion")
    for left, right in zip(actual, expected):
        require(left["rank"] == right["rank"] and left["knowledge_id"] == right["knowledge_id"]
                and math.isclose(left["score"], right["score"], rel_tol=1e-12, abs_tol=1e-12),
                "Saved ranking differs from its query rankings / recomputed RRF")


def contained_path(root, relative):
    require(isinstance(relative, str), "Manifest path must be a relative string")
    path = (root / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(root.resolve()),
            f"Manifest path leaves project: {relative}")
    return path


def check_freeze(root):
    path = root / "data/input_freeze.json"
    if not path.exists():
        return {"present": False, "note": "No freeze manifest is present; absence does not certify preregistration."}
    frozen = read_json(path)
    require(frozen.get("label_name") == LABEL_KIND, "Freeze uses a different label kind")
    require(frozen.get("no_benchmark_changes_after_results") is True, "Freeze lacks no-change declaration")
    hashes = frozen["file_sha256"]
    require(isinstance(hashes, dict) and hashes, "Freeze hash inventory is empty")
    mismatches = []
    for relative, expected in hashes.items():
        item = contained_path(root, relative)
        require(valid_hash(expected), f"Invalid frozen SHA256: {relative}")
        if not item.is_file() or hashlib.sha256(item.read_bytes()).hexdigest() != expected:
            mismatches.append(relative)
    require(not mismatches, "Frozen file integrity mismatch: " + ", ".join(mismatches))
    return {"present": True, "files_checked": len(hashes), "integrity_valid": True}


def check_cases(root, state):
    cases = read_jsonl(root / "data/wearable_cases.jsonl")
    report = validate_dataset(cases, read_json(root / "schemas/wearable_case.schema.json"))
    require(report["valid"], f"Case validation failed: {report}")
    unique_index(cases, ("id",), {(case_id,) for case_id in CASE_IDS})
    state["cases"] = cases
    state["inputs"] = {case["id"]: fingerprint(model_input(case)) for case in cases}
    return {"count": len(cases), "daily_rows": report["daily_row_count"],
            "matched_pairs": report["matched_pairs"], "schema_and_statistics_valid": True}


def check_corpus(root, state):
    items = read_jsonl(root / "data/knowledge_items.jsonl")
    unique_index(items, ("id",), {(item_id,) for item_id in KNOWLEDGE_IDS})
    validator = jsonschema.Draft7Validator(read_json(root / "schemas/knowledge_item.schema.json"),
                                         format_checker=jsonschema.FormatChecker())
    for item in items:
        validator.validate(item)
        require(item["status"] == "verified" and item["content"].strip(), f"Unverified corpus item: {item['id']}")
    require(dict(Counter(item["domain"] for item in items)) == DOMAINS, "Knowledge taxonomy quotas do not match")
    require(len({" ".join((item["title"] + item["content"]).casefold().split()) for item in items}) == 96,
            "Exact duplicated knowledge title/content")
    verification = read_json(root / "data/corpus_verification.json")
    checks = unique_index(verification["checks"], ("knowledge_id",), {(item_id,) for item_id in KNOWLEDGE_IDS})
    seed = read_json(root / "data/corpus_seed.json")
    require(len(seed) == 96, "Corpus seed count differs")
    sources = read_json(root / "data/source_manifest.json")
    used_source_keys = {entry["source_key"] for entry in seed}
    for key in used_source_keys:
        source = sources[key]
        require(source["status"] == "fetched" and source["http_status"] == 200, f"Source was not fetched: {key}")
        text_path = contained_path(root, source["text_path"])
        html_path = contained_path(root, source["html_path"])
        require(hashlib.sha256(html_path.read_bytes()).hexdigest() == source["html_sha256"], f"Source HTML hash mismatch: {key}")
        require(hashlib.sha256(text_path.read_text(encoding="utf-8").encode()).hexdigest() == source["text_sha256"],
                f"Source text hash mismatch: {key}")
    for item in items:
        entry = seed[int(item["id"][1:]) - 1]
        source = sources[entry["source_key"]]
        check = checks[(item["id"],)]
        require(check["support_anchor_found"] is True and check["source_text_sha256"] == source["text_sha256"],
                f"Source verification mismatch: {item['id']}")
        require(all(item[field] == entry[field] for field in ("title", "content", "domain")),
                f"Corpus differs from source-backed seed: {item['id']}")
        require(item["source_url"] == source["source_url"] and item["source_accessed_on"] == source["source_accessed_on"],
                f"Corpus source provenance mismatch: {item['id']}")
        text = " ".join(contained_path(root, source["text_path"]).read_text(encoding="utf-8").casefold().split())
        anchors = [entry["support_anchor"], *entry.get("support_anchors", [])]
        require(all(" ".join(anchor.casefold().split()) in text for anchor in anchors), f"Missing source anchor: {item['id']}")
    review = read_json(root / "data/independent_corpus_review.json")
    require(review["corpus_sha256"] == fingerprint(items), "Independent source review belongs to an older corpus")
    require(review["cases_or_outputs_visible"] is False and not review["requires_correction"], "Source review is not clean / blinded")
    reviews = unique_index(review["reviews"], ("knowledge_id",), {(item_id,) for item_id in KNOWLEDGE_IDS})
    require(all(row["assessment"] == "supported" and row["rationale"].strip() for row in reviews.values()),
            "Independent source review has unresolved or unsupported items")
    state["corpus"] = items
    return {"count": len(items), "domain_counts": DOMAINS, "source_count": len(sources),
            "used_source_count": len(used_source_keys),
            "corpus_sha256": sha256_json(sorted(items, key=lambda item: item["id"])),
            "verification_kind": "machine/source review, not human clinical review"}


def check_annotations(root, state):
    from annotate_relevance import ANNOTATION_REVISION, agreement, grouped_agreement
    config = state["config"]
    pairs = {(case_id, item_id) for case_id in CASE_IDS for item_id in KNOWLEDGE_IDS}
    judges = {}
    for role in ("judge_a", "judge_b", "adjudicated"):
        rows = csv_rows(root / f"annotations/{role}.csv")
        check_annotation_revision(rows, ANNOTATION_REVISION, role)
        index = unique_index(rows, ("case_id", "knowledge_id"), pairs)
        model_role = "adjudicator" if role == "adjudicated" else role
        for row in rows:
            row["relevance"] = annotation_value(row, allow_pending=role != "adjudicated")
            require(all(row[field].strip() for field in ("rationale", "raw_data_evidence", "item_condition_evidence")),
                    f"Empty annotation evidence: {role}")
            require(row["model"] == config["llm"][model_role + "_model"] and valid_hash(row["input_sha256"]),
                    f"Wrong annotation model or missing input hash: {role}")
            if role != "adjudicated":
                require(row["annotator_id"] == role, "Annotator identity mismatch")
        judges[role] = index
    gold = read_gold(root / "data/relevance_labels_provisional.csv", CASE_IDS, KNOWLEDGE_IDS)
    for pair, row in judges["adjudicated"].items():
        a, b = judges["judge_a"][pair], judges["judge_b"][pair]
        require(row["label_name"] == LABEL_KIND and row["relevance"] == gold[pair[0]][pair[1]],
                f"Gold/adjudication mismatch: {pair}")
        for role, opinion in (("judge_a", a), ("judge_b", b)):
            require(label_value(row[role], allow_null=True) == opinion["relevance"] and
                    row[role + "_status"] == opinion["status"], f"Saved judge opinion mismatch: {pair}")
        agreed = a["relevance"] is not None and a["relevance"] == b["relevance"]
        require(csv_boolean(row["judges_agreed"]) == agreed and
                csv_boolean(row["adjudicator_changed_agreement"]) == (agreed and row["relevance"] != a["relevance"]),
                f"Adjudication agreement flags mismatch: {pair}")
        require(a["input_sha256"] != b["input_sha256"], f"Judge prompts were not independently constructed: {pair}")
    metadata = read_json(root / "data/relevance_labels_provisional.metadata.json")
    check_gold_annotation_revision(csv_rows(root / "data/relevance_labels_provisional.csv"), metadata, ANNOTATION_REVISION)
    require(metadata["label_name"] == LABEL_KIND and metadata["pairs"] == 2304 and metadata["complete_2304_pairs"] is True
            and metadata["human_reviewed"] is False, "Provisional gold metadata does not certify complete, nonhuman labels")
    require(metadata["model_ids"] == {role: config["llm"][role + "_model"] for role in ("judge_a", "judge_b", "adjudicator")},
            "Gold metadata model configuration mismatch")
    a, b = list(judges["judge_a"].values()), list(judges["judge_b"].values())
    recomputed = agreement(a, b)
    saved = read_json(root / "outputs/metrics/judge_agreement.json")
    require(all(saved.get(key) == value for key, value in recomputed.items()), "Judge agreement/confusion/kappa differs from saved opinions")
    require(read_json(root / "outputs/metrics/judge_agreement_subgroups.json") == grouped_agreement(a, b, state["cases"]),
            "Subgroup judge agreement differs from saved opinions")
    state["gold"] = gold
    return {"gold_pairs": 2304, "judge_a_pairs": len(a), "judge_b_pairs": len(b), "adjudicated_pairs": 2304,
            "pending_judge_a": recomputed["pending_judge_a"], "pending_judge_b": recomputed["pending_judge_b"],
            "label_kind": LABEL_KIND, "annotation_revision": ANNOTATION_REVISION}


def check_representations(root, state):
    import tiktoken
    from generate_representations import raw_statistical_facts
    config = state["config"]
    configured_backend = config["llm"]["backend"]
    expected_backend = "openai_compatible_chat_completions" if configured_backend == "openai_compatible" else configured_backend
    require(config["repeats"] == 3, "Pilot requires exactly three representation repeats")
    records = read_jsonl(root / "outputs/representations/representations.jsonl")
    keys = {(case_id, baseline, repeat) for case_id in CASE_IDS for baseline in BASELINES for repeat in (1, 2, 3)}
    index = unique_index(records, ("case_id", "baseline_id", "repeat_id"), keys)
    encoder = tiktoken.get_encoding("cl100k_base")
    cases = {case["id"]: case for case in state["cases"]}
    for key, record in index.items():
        metadata = record["metadata"]
        require(type(record["repeat_id"]) is int, f"Noninteger representation repeat: {key}")
        require(metadata["status"] == "completed", f"Incomplete representation: {key}")
        require(record["input_sha256"] == state["inputs"][record["case_id"]], f"Representation input changed: {key}")
        require(metadata["configuration_revision"] == config["revision"], f"Representation uses another execution revision: {key}")
        require(all(metadata.get(field) is False for field in ("knowledge_corpus_visible", "designer_fields_visible", "official_PHIA_execution")),
                f"Unblinded representation / official PHIA claim: {key}")
        queries = representation_queries(record)
        require(queries and record["text"].strip(), f"Empty representation: {key}")
        if record["baseline_id"] == "B3":
            require(record["text"] == "\n".join(queries).strip(), f"B3 text differs from its five queries: {key}")
        else:
            require(record["queries"] == [], f"Non-QueryGen baseline has query slots: {key}")
        tokens = len(encoder.encode(record["text"]))
        require(record["output_tokens"] == tokens and metadata["token_counter"] == "cl100k_base", f"Representation token count mismatch: {key}")
        if record["baseline_id"] == "B4":
            require(metadata["model"] is None and metadata["backend"] == "deterministic" and
                    record["text"] == raw_statistical_facts(model_input(cases[record["case_id"]])), f"B4 is not the deterministic factual representation: {key}")
        else:
            require(metadata["model"] == config["llm"]["generator_model"] and
                    metadata["backend"] == expected_backend, f"Representation uses another provider/model: {key}")
            require(metadata["budget_tokens"] == config["representation_output_tokens"] and
                    tokens <= config["representation_output_tokens"] and metadata["independent_fresh_context_repeat"] is True,
                    f"Representation budget/context controls violated: {key}")
    manifest = read_json(root / "outputs/representations/generation_manifest.json")
    require(manifest["input_hashes"] == state["inputs"] and manifest["same_input_for_all_conditions"] is True and
            manifest["configuration_revision"] == config["revision"], "Generation manifest input/revision mismatch")
    state["representations"], state["representation_index"] = records, index
    return {"count": len(records), "cases": 24, "baselines": 4, "repeats": 3, "shared_input_hashes_valid": True}


def check_retrieval(root, state):
    config = normalize_config(read_json(root / "config/retrieval.json"))
    config_hash = sha256_json(config)
    corpus_hash = sha256_json(sorted(state["corpus"], key=lambda item: item["id"]))
    manifest = read_json(root / "outputs/retrieval/manifest.json")
    require(manifest["config"] == config and manifest["config_sha256"] == config_hash and manifest["corpus_sha256"] == corpus_hash,
            "Retrieval manifest corpus/config hash mismatch")
    require(manifest["representations_sha256"] == sha256_json(state["representations"]) and
            manifest["corpus_count"] == 96 and manifest["representation_count"] == 288, "Retrieval manifest representation/count mismatch")
    require(set(manifest["retrievers_completed"]) == RETRIEVERS and len(manifest["retrievers_completed"]) == 2,
            "Both BM25 and dense must be completed")
    require(set(manifest["retrievers_requested"]) == RETRIEVERS and len(manifest["retrievers_requested"]) == 2,
            "Retrieval manifest must request the two standalone retrievers")
    dense = manifest["dense_runtime"]
    require(all(dense[field] == config["dense"][field] for field in ("model", "revision", "max_length")) and
            dense["similarity"] == "cosine" and dense["normalized_embeddings"] is True, "Dense model/version/similarity mismatch")
    records = []
    for retriever in sorted(RETRIEVERS):
        selected = read_jsonl(root / f"outputs/retrieval/{retriever}.jsonl")
        require(all(record["retriever"] == retriever for record in selected), "Retrieval record stored under wrong retriever")
        records.extend(selected)
    expected = {(case_id, baseline, repeat, retriever) for case_id in CASE_IDS for baseline in BASELINES
                for repeat in (1, 2, 3) for retriever in RETRIEVERS}
    index = unique_index(records, ("case_id", "baseline_id", "repeat_id", "retriever"), expected)
    for key, record in index.items():
        representation = state["representation_index"][key[:3]]
        require(record["representation_status"] == "completed" and
                record["representation_input_sha256"] == representation["input_sha256"], f"Retrieval representation mismatch: {key}")
        require(record["config_sha256"] == config_hash and record["corpus_sha256"] == corpus_hash,
                f"Retriever configuration/corpus varied across baselines: {key}")
        validate_ranking(record["ranking"])
        originals = representation_queries(representation)
        queries = record["queries"]
        require(len(queries) == len(originals), f"Retrieval query count mismatch: {key}")
        for number, (query, original) in enumerate(zip(queries, originals)):
            text, diagnostic = truncate_query(original, config["query_max_tokens"])
            require(query["query_index"] == number and query["query"] == text and
                    all(query[field] == value for field, value in diagnostic.items()), f"Query truncation changed across methods: {key}")
            validate_ranking(query["ranking"])
            if record["retriever"] == "dense":
                require(query["model_max_length"] == dense["max_length"] and
                        type(query["model_tokens_including_prefix"]) is int and query["model_tokens_including_prefix"] >= 0 and
                        query["model_truncated"] == (query["model_tokens_including_prefix"] > dense["max_length"]),
                        f"Dense query truncation diagnostics invalid: {key}")
        query_rankings = [query["ranking"] for query in queries]
        if record["baseline_id"] == "B3":
            require(record["fusion"] == "five-query RRF", "QueryGen fusion differs")
            rankings_equal(record["ranking"], reciprocal_rank_fusion(query_rankings, 20, config["rrf_k"]))
        else:
            require(record["fusion"] == "single-query", "Unexpected single-query fusion")
            rankings_equal(record["ranking"], query_rankings[0])
    state["retrieval"], state["retrieval_index"] = records, index
    return {"count": len(records), "retrievers": sorted(RETRIEVERS), "top_k": 20,
            "config_sha256": config_hash, "corpus_sha256": corpus_hash, "fixed_tie_breaking_verified": True}


def compare_metric_csv(saved, expected, fields):
    expected_index = unique_index(expected, fields)
    actual_index = unique_index(saved, fields, set(expected_index))
    for key, row in actual_index.items():
        reference = expected_index[key]
        require(row["label_kind"] == LABEL_KIND, f"Metric label kind mismatch: {key}")
        for metric in METRICS:
            actual = None if row[metric] == "" else float(row[metric])
            value = reference[metric]
            require((actual is None and value is None) or (actual is not None and value is not None and
                    math.isfinite(actual) and math.isclose(actual, value, rel_tol=1e-10, abs_tol=1e-10)),
                    f"Metric {metric} differs from recomputed rankings/gold: {key}")
        for field in ("case_count", "repeat_count"):
            if field in reference:
                require(int(row[field]) == reference[field], f"Metric aggregation count mismatch: {key}")


def check_metrics(root, state):
    cases = {case["id"]: case for case in state["cases"]}
    runs, case_rows = case_level_results(cases, state["retrieval"], state["gold"])
    summaries = summarize(case_rows)
    directory = root / "outputs/metrics"
    saved_runs = csv_rows(directory / "per_run.csv")
    for row in saved_runs:
        row["repeat_id"] = int(row["repeat_id"])
    compare_metric_csv(saved_runs, runs, ("retriever", "baseline_id", "case_id", "repeat_id"))
    compare_metric_csv(csv_rows(directory / "per_case.csv"), case_rows, ("retriever", "baseline_id", "case_id"))
    saved = csv_rows(directory / "summary.csv")
    compare_metric_csv(saved, summaries, ("retriever", "baseline_id", "grouping", "group"))
    overall = [row for row in saved if row["grouping"] == "overall"]
    unique_index(overall, ("retriever", "baseline_id"), {(retriever, baseline) for retriever in RETRIEVERS for baseline in BASELINES})
    require(all(row["group"] == "all" and int(row["case_count"]) == 24 for row in overall), "Overall metrics exclude cases")
    matched = read_json(directory / "matched_pairs.json")
    require(len(matched) == 5 and {tuple(row["pair"]) for row in matched} == set(MATCHED_PAIRS), "Missing / duplicate matched-pair analysis")
    require(matched == matched_pair_analysis(state["retrieval"], state["gold"], case_rows),
            "Matched-pair results differ from saved candidates / provisional gold")
    for pair in matched:
        unique_index(pair["methods"], ("retriever", "baseline_id"), {(retriever, baseline) for retriever in RETRIEVERS for baseline in BASELINES})
    metadata = read_json(directory / "evaluation_manifest.json")
    require(metadata["label_kind"] == LABEL_KIND and metadata["case_count"] == 24 and metadata["knowledge_count"] == 96 and
            metadata["label_count"] == 2304 and metadata["run_count"] == 576, "Evaluation manifest is incomplete")
    return {"overall_rows": len(overall), "summary_rows": len(saved), "per_case_rows": len(case_rows),
            "per_run_rows": len(runs), "matched_pairs": len(matched), "six_metrics_recomputed": True}


def check_analysis_summary(aggregate):
    available = aggregate["semantic_audit_available_for_cases"]
    failures = aggregate["top_five_failure_candidates"]
    require(isinstance(available, list) and len(available) == 24 and set(available) == CASE_IDS and
            isinstance(failures, list) and len(failures) == 5 and
            len(set(failures)) == 5 and set(failures) <= CASE_IDS,
            "Final failure analysis is incomplete")


def check_analysis(root, state):
    directory = root / "outputs/case_analysis/semantic_audit"
    summary = read_json(directory / "summary.json")
    require(summary["all_cases_completed"] is True and summary["case_count"] == 24 and
            summary["requested_case_count"] == 24 and summary["failures"] == [] and
            summary["audit_model"] == state["config"]["llm"]["audit_model"], "Semantic audit is incomplete / uses another model")
    require({path.stem for path in directory.glob("C*.json")} == CASE_IDS, "Semantic audit inventory must be exactly 24 cases")
    for case_id in sorted(CASE_IDS):
        record = read_json(directory / f"{case_id}.json")
        require(record["case_id"] == case_id and record["audit_kind"] == "PROVISIONAL_LLM_AUDIT" and
                record["label_kind"] == LABEL_KIND and record["case_input_sha256"] == state["inputs"][case_id] and
                record["positive_label_input_sha256"] == fingerprint(state["gold"][case_id]), f"Stale semantic audit: {case_id}")
        require(record["llm_metadata"]["model"] == state["config"]["llm"]["audit_model"], f"Semantic audit model mismatch: {case_id}")
        mapping = record["anonymous_reference_mapping"]
        expected = {(baseline, repeat) for baseline in ("B1", "B2", "B3") for repeat in (1, 2, 3)}
        unique_index(list(mapping.values()), ("baseline_id", "repeat_id"), expected)
        for reference in mapping.values():
            representation = state["representation_index"][(case_id, reference["baseline_id"], reference["repeat_id"])]
            require(reference["text"] == representation["text"], f"Semantic audit used another representation: {case_id}")
        for fact in record["audit"]["facts"]:
            require(fact["fact_statement"].strip() and fact["knowledge_ids"] and
                    all(state["gold"][case_id].get(item_id, 0) > 0 for item_id in fact["knowledge_ids"]),
                    f"Semantic audit fact references nonpositive / unknown gold: {case_id}")
            unique_index(fact["representation_checks"], ("representation_ref",), {(reference,) for reference in mapping})
            require(all(check["status"] in {"retained", "omitted", "contradicted", "uncertain"} for check in fact["representation_checks"]),
                    f"Invalid semantic audit retention status: {case_id}")
        analysis = read_json(root / f"outputs/case_analysis/{case_id}.json")
        require(analysis["case_id"] == case_id and analysis["label_kind"] == LABEL_KIND and
                analysis["gold_relevance"] == state["gold"][case_id], f"Case failure analysis gold mismatch: {case_id}")
        require(analysis["raw_data"] == next(case for case in state["cases"] if case["id"] == case_id),
                f"Case failure analysis raw data mismatch: {case_id}")
        representations = unique_index([row["representation"] for row in analysis["baseline_outputs"]], ("baseline_id", "repeat_id"),
                                      {(baseline, repeat) for baseline in BASELINES for repeat in (1, 2, 3)})
        require(all(value == state["representation_index"][(case_id, *key)] for key, value in representations.items()),
                f"Case analysis has stale baseline outputs: {case_id}")
        retrieval = unique_index(analysis["retrieval"], ("retriever", "baseline_id", "repeat_id"),
                                 {(retriever, baseline, repeat) for retriever in RETRIEVERS for baseline in BASELINES for repeat in (1, 2, 3)})
        for (retriever, baseline, repeat), local in retrieval.items():
            original = state["retrieval_index"][(case_id, baseline, repeat, retriever)]
            rankings_equal(local["retrieved_top_k"], original["ranking"])
            require(all(candidate["gold_relevance"] == state["gold"][case_id][candidate["knowledge_id"]]
                        for candidate in local["retrieved_top_k"]), f"Candidate gold enrichment mismatch: {case_id}")
            metrics = ranking_metrics(original["ranking"], state["gold"][case_id])
            require(local["metrics"] == {metric: metrics[metric] for metric in METRICS} and
                    all(local[field] == metrics[field] for field in ("false_negatives_at_10", "strong_false_negatives_at_10", "false_positives_at_10")),
                    f"False positive/negative analysis differs from actual retrieval: {case_id}")
        require(analysis.get("semantic_audit") == record, f"Case analysis omits / differs from semantic audit: {case_id}")
    aggregate = read_json(root / "outputs/case_analysis/analysis_summary.json")
    check_analysis_summary(aggregate)
    return {"semantic_audit_cases": 24, "failure_analysis_cases": 24, "audit_kind": "PROVISIONAL_LLM_AUDIT"}


def check_reports(root, state):
    for name in ("PILOT_RESULTS.md", "FAILURE_ANALYSIS.md", "VALIDITY_NOTES.md"):
        text = (root / "reports" / name).read_text(encoding="utf-8")
        require(text.strip() and LABEL_KIND in text, f"Missing / unqualified final report: {name}")
    final = read_json(root / "outputs/metrics/final_summary.json")
    assessment = final["assessment"]
    require(assessment["category"] in {"A", "B", "C", "D", "E"} and assessment["hypothesis_status"] in
            {"supported", "partially supported", "unsupported", "inconclusive"}, "Final assessment must explicitly classify the research question")
    require(all(assessment[field].strip() for field in ("reasoning", "next_step", "strongest")), "Research assessment is incomplete")
    require(final["case_count"] == 24 and final["knowledge_count"] == 96 and final["provisional_label_count"] == 2304 and
            final["retrieval_runs"] == 576 and len(final["overall_metrics"]) == 8 and len(final["top_five_failure_cases"]) == 5,
            "Final handoff summary does not contain complete pilot counts")
    return {"reports": 3, "category": assessment["category"], "hypothesis_status": assessment["hypothesis_status"],
            "note": "Integrity validation is not independent scientific or clinical endorsement."}


def validate_pilot(root=ROOT):
    root = Path(root).resolve()
    state = {}
    stages = {}
    tasks = [("configuration", lambda: load_config(root, state)), ("cases", lambda: check_cases(root, state)),
             ("corpus", lambda: check_corpus(root, state)), ("annotations", lambda: check_annotations(root, state)),
             ("representations", lambda: check_representations(root, state)), ("retrieval", lambda: check_retrieval(root, state)),
             ("metrics", lambda: check_metrics(root, state)), ("analysis", lambda: check_analysis(root, state)),
             ("reports", lambda: check_reports(root, state)), ("freeze", lambda: check_freeze(root))]
    for name, task in tasks:
        try:
            stages[name] = {"valid": True, "details": task()}
        except Exception as error:
            stages[name] = {"valid": False, "error_type": type(error).__name__, "error": str(error)}
    valid = all(stage["valid"] for stage in stages.values())
    return {"validation_revision": "pilot-completion-v1", "validated_at_utc": datetime.now(timezone.utc).isoformat(),
            "valid": valid, "status": "COMPLETE" if valid else "INCOMPLETE_OR_INVALID", "label_kind": LABEL_KIND,
            "offline_only": True, "stages": stages,
            "limitations": ["Structural/hash agreement does not prove factual correctness or clinical validity.",
                            "Judge uncertainty remains explicit; only adjudication and provisional gold must be fully resolved.",
                            "When no input freeze is present, this check cannot certify pre-result freezing."]}


def load_config(root, state):
    state["config"] = read_json(root / "config/experiment.json")
    require(state["config"]["label_name"] == LABEL_KIND and state["config"]["design_revision"] == "design-v1",
            "Execution configuration does not preserve design-v1 and provisional labels")
    return {"execution_revision": state["config"]["revision"], "design_revision": "design-v1"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_pilot(args.root)
    write_json(args.output or args.root / "outputs/metrics/pilot_validation.json", report)
    import json
    print(json.dumps({"valid": report["valid"], "status": report["status"],
                      "failed_stages": [name for name, value in report["stages"].items() if not value["valid"]]}))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
