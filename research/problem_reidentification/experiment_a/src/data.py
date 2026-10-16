"""Read P1 in place, audit provenance and freeze prediction-independent A1 panels."""
from collections import Counter
from math import atan2, cos, pi, sin, sqrt
from statistics import mean, median, pstdev

from research.problem_reidentification.p1.dataset import verify_release
from .common import ROOT, REPO, P1, digest, freeze, read, rows, sha, verify, write, write_rows

# Specified from source text before any Experiment A model prediction.
GROUPS = [
    {"id": "duration_and_timing", "ids": ["K005", "K006", "K017", "K019"],
     "contrast": "Repeated short sleep, schedule constraints, general clock variability, weekday/weekend difference"},
    {"id": "episodic_and_persistent", "ids": ["K016", "K034", "K037", "K038"],
     "contrast": "Several short nights versus reported bad sleep and months-long insomnia history"},
    {"id": "activity_intensity", "ids": ["K041", "K042", "K043", "K044", "K047"],
     "contrast": "Low activity, gradual increase, moderate/vigorous intensity, established guideline attainment"},
    {"id": "activity_sleep_context", "ids": ["K069", "K070", "K071", "K072", "K073"],
     "contrast": "General association versus exercise timing, intensity, symptoms and joint diary evidence"},
    {"id": "measurement_missingness", "ids": ["K089", "K090", "K091", "K093", "K094"],
     "contrast": "Fit, overnight coverage, missing sleep data, device changes and sleep-period interpretation"},
    {"id": "reference_windows", "ids": ["K082", "K083", "K086", "K090"],
     "contrast": "Personal ranges, repeated RHR, HRV collection period and overnight coverage"},
]


def inputs():
    verify_release(P1)
    cases = rows(P1 / "cases.jsonl")
    knowledge = rows(REPO / "data/knowledge_items.jsonl")
    if len(cases) != 48 or len({c["subject_id"] for c in cases}) != 16 or len(knowledge) != 96:
        raise ValueError("Unexpected frozen input cardinality")
    return cases, knowledge


def audit():
    cases, knowledge = inputs()
    old = read(REPO / "data/input_freeze.json")["file_sha256"]
    changed = [name for name, expected in old.items() if sha(REPO / name) != expected]
    if changed:
        raise ValueError("Legacy frozen files changed: " + repr(changed))
    return {"status": "PENDING_HUMAN_ANNOTATION", "legacy_hashes_verified": len(old),
            "p1_release_id": verify_release(P1)["release_id"], "p1_manifest_sha256": sha(P1 / "freeze.json"),
            "cases": len(cases), "participants": len({c["subject_id"] for c in cases}),
            "windows_per_participant": dict(sorted(Counter(Counter(c["subject_id"] for c in cases).values()).items())),
            "daily_rows": sum(len(c["days"]) for c in cases),
            "a0_pairs": sum(len(c["candidate_ids"]) for c in cases), "corpus_items": len(knowledge),
            "human_gold_pairs": 0, "formal_metrics": None,
            "p1_files": read(P1 / "freeze.json")["files"],
            "knowledge_conditions": [{"id": k["id"], "domain": k["domain"],
                "fields": {field: len(values) for field, values in k["applicability"].items()},
                "human_confirmed": False,
                "missingness_wording_needs_review": any(s in str(k["applicability"]).lower()
                    for s in ("unknown", "no information", "unrecorded", "no confirmed")),
                "scope_note": "Context needed for a particular claim may not be necessary for general education"}
                for k in knowledge]}


def build_a1(output):
    cases, corpus = inputs()
    output = __import__("pathlib").Path(output)
    if output.exists():
        raise ValueError("A1 release already exists; choose a new version")
    selected = sorted({kid for g in GROUPS for kid in g["ids"]})
    by_id = {k["id"]: k for k in corpus}
    output.mkdir(parents=True)
    write(output / "groups.json", {"groups": GROUPS, "selection": "Fixed source-text panels, no model predictions or labels",
        "coverage_gaps": ["No explicit source-supported recovery-state alternative identified; history-versus-recovery contrast not established",
                          "No invented numerical persistence thresholds; vague short/repeated/low conditions require human interpretation",
                          "Lexical neighbors and analyst panels do not establish human topical relevance"],
        "case_selection": "All 48 frozen windows, all 16 participants; no outcome filtering",
        "annotation_status": "PENDING_HUMAN_ANNOTATION", "condition_status": "EXISTING_MACHINE_REVIEWED_DRAFT_NOT_HUMAN_CONFIRMED",
        "pair_policy": "One judgment per unique case-knowledge pair, reused across overlapping panel descriptions"})
    write_rows(output / "knowledge.jsonl", [by_id[k] for k in selected])
    # Manifest only: no personal daily values or copied P1 records.
    write_rows(output / "cases.jsonl", [{"case_id": c["case_id"], "candidate_ids": selected} for c in cases])
    write(output / "source_audit.json", {"corpus_sha256": sha(REPO / "data/knowledge_items.jsonl"),
        "domain_counts": dict(Counter(k["domain"] for k in corpus)),
        "items": [{"id": k["id"], "source_url": k["source_url"], "condition_sha256": digest(k["applicability"]),
                   "human_confirmed": False} for k in corpus]})
    return freeze(output, ["groups.json", "knowledge.jsonl", "cases.jsonl", "source_audit.json"],
        {"version": "a1-v1", "p1_release_id": verify_release(P1)["release_id"], "cases": 48,
         "participants": 16, "unique_knowledge": len(selected), "unique_pairs": 48 * len(selected),
         "group_memberships_per_case": sum(len(g["ids"]) for g in GROUPS),
         "selection_code_sha256": sha(__file__), "human_gold": False})


def candidates(stage="a0", release=None):
    cases, corpus = inputs()
    if stage == "a0":
        knowledge = {k["knowledge_id"]: {**k, "id": k["knowledge_id"]} for k in rows(P1 / "knowledge.jsonl")}
        return cases, knowledge, verify_release(P1)["release_id"]
    manifest = verify(release)
    assignments = {r["case_id"]: r["candidate_ids"] for r in rows(__import__("pathlib").Path(release) / "cases.jsonl")}
    if set(assignments) != {c["case_id"] for c in cases}:
        raise ValueError("A1 does not reference exactly the frozen P1 case set")
    cases = [{**c, "candidate_ids": assignments[c["case_id"]]} for c in cases]
    return cases, {k["id"]: k for k in rows(__import__("pathlib").Path(release) / "knowledge.jsonl")}, manifest["release_id"]


def scalar_stats(points, total):
    vals = [v for _, v, _ in points]
    slope = None
    if len(points) >= 2:
        xs = [d for d, _, _ in points]
        xbar = mean(xs)
        denom = sum((x - xbar) ** 2 for x in xs)
        slope = sum((x - xbar) * (y - mean(vals)) for x, y in zip(xs, vals)) / denom if denom else None
    by_day = {d: v for d, v, _ in points}
    adjacent = [abs(v - by_day[d-1]) for d, v, _ in points if d-1 in by_day]
    return {"n": len(vals), "missing_or_unusable": total-len(vals),
            "mean": mean(vals) if vals else None, "median": median(vals) if vals else None,
            "sd": pstdev(vals) if vals else None, "min": min(vals) if vals else None,
            "max": max(vals) if vals else None, "slope_per_day": slope,
            "adjacent_mean_abs_change": mean(adjacent) if adjacent else None,
            "observations": [ref for _, _, ref in points]}


def representation(case, mode):
    """All views preserve missingness/quality; no source identity or sampling rationale."""
    base = {"context": case["context"], "quality_notes": case["quality_notes"],
            "baseline_day_range": [1, 28], "current_day_range": [29, 42]}
    if mode == "full":
        return {**base, "days": case["days"], "representation": "full_42_daily_rows_no_truncation"}
    if mode not in ("current", "statistics"):
        raise ValueError("Unknown information view")
    statistics = {}
    phases = ("current",) if mode == "current" else ("baseline", "current")
    for phase in phases:
        daily = [d for d in case["days"] if d["phase"] == phase]
        summary = {}
        for metric in daily[0]["metrics"]:
            raw = [(d["day"], d["metrics"][metric], f"d{d['day']}.{metric}") for d in daily]
            numeric = [(day, v, ref) for day, v, ref in raw if isinstance(v, (int, float)) and not isinstance(v, bool)
                       and not (metric == "resting_heart_rate_bpm" and v == 0)]
            if numeric or all(v is None or isinstance(v, (int, float)) for _, v, _ in raw):
                summary[metric] = scalar_stats(numeric, len(daily))
            elif metric.endswith("_clock"):
                valid = [(day, sum(int(n)*m for n, m in zip(v.split(":"), [60, 1, 1/60])), ref)
                         for day, v, ref in raw if v is not None]
                xs = [v/1440*2*pi for _, v, _ in valid]
                s, c = sum(sin(x) for x in xs), sum(cos(x) for x in xs)
                summary[metric] = {"n": len(xs), "missing": len(daily)-len(xs),
                    "circular_mean_minute": (atan2(s, c) % (2*pi))*1440/(2*pi) if xs else None,
                    "circular_resultant_length": sqrt(s*s+c*c)/len(xs) if xs else None,
                    "observations": [ref for _, _, ref in valid], "timezone_or_dst_known": False}
            else:
                summary[metric] = {"value_counts": dict(Counter(str(v) for _, v, _ in raw)),
                                   "interpretation": "source category, not independently verified quality"}
        statistics[phase] = {"day_range": [daily[0]["day"], daily[-1]["day"]], "metrics": summary,
                             "quality_flags": {f"d{d['day']}": d["quality_flags"] for d in daily if d["quality_flags"]}}
    return {**base, "statistics": statistics, "representation": mode,
            "sufficiency_limit": "Descriptive moments, slopes and clock concentration are not sufficient statistics for every possible temporal condition"}


def evidence_value(case, reference):
    if reference.startswith("context."):
        return case["context"].get(reference.removeprefix("context."))
    import re
    match = re.fullmatch(r"d(\d+)\.([a-z_]+)", reference)
    if not match:
        raise ValueError("Unknown evidence reference: " + reference)
    day, metric = int(match[1]), match[2]
    row = next((d for d in case["days"] if d["day"] == day), None)
    if row is None or metric not in row["metrics"]:
        raise ValueError("Unknown evidence reference: " + reference)
    return row["metrics"][metric]
