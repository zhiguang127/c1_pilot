"""C0-A: deterministic public preflight and PRIVATE blind review card preparation.

No API calls, labels, or model-generated judgments. Python 3.11+ stdlib only.
Run from the repository root: python -m research.problem_reidentification.experiment_c0.pilot ...
"""
import argparse
import hashlib
import json
import random
import re
import secrets
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
B0 = ROOT.parent / "experiment_b0"
METHODS = (
    "B1_direct", "B2_re2_style", "B3_self_refine", "B4_critic",
    "BM_critic", "S4_relative",
)
SEED = 20261018
EXPECTED_CANDIDATES = ["K006", "K017", "K041", "K083", "K094"]
METRICS = {"verified_chain_failures": None, "explanation_fidelity": None,
           "behavioral_faithfulness": None, "decision_accuracy": None,
           "decision_improvement": None, "annotator_agreement": None}


class AuditBlocked(ValueError):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status


def require(condition, detail):
    if not condition:
        raise AuditBlocked("BLOCKED_FREEZE_MISMATCH", detail)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def token(seed, *parts):
    data = "|".join(map(str, (seed, *parts)))
    return hashlib.sha256(data.encode()).hexdigest()[:18]


def public_audit(summary):
    """Aggregate-only checks; NEVER interpret output changes as correctness."""
    if summary.get("status") != "COMPLETE_EXPLORATORY_EXECUTION":
        raise ValueError("B0 summary is incomplete")
    if summary.get("record_count") != 200 or summary.get("planned_records") != 200:
        raise ValueError("B0 public record count has changed")
    if summary.get("human_gold") is not False or summary.get("decision_accuracy") is not None:
        raise ValueError("Gold/accuracy status changed; re-audit protocol before reuse")
    table = []
    for method in METHODS:
        main = summary["panels"]["main"][method]
        order = summary["candidate_order_intervention"][method]
        if main["planned_windows"] != 16 or main["completed_records"] != 16:
            raise ValueError("Method window denominator changed: " + method)
        if sum(main["status_counts"].values()) != 16:
            raise ValueError("Method status counts do not reconcile: " + method)
        if main["valid_output_windows"] != main["status_counts"].get("EXECUTED", 0):
            raise ValueError("Invalid accepted-output count: " + method)
        if not (0 <= order["same_priority_order"] <= order["valid_paired_windows"] <= 4):
            raise ValueError("Invalid reversal window denominator: " + method)
        if not (0 <= order["same_pair_relations"] <= order["pair_denominator"]):
            raise ValueError("Invalid pair stability count: " + method)
        if order["pair_denominator"] != order["valid_paired_windows"] * 10:
            raise ValueError("Pair counts must have five candidates: " + method)
        table.append({
            "method": method,
            "planned": 16,
            "valid_outputs": main["valid_output_windows"],
            "status_counts": main["status_counts"],
            "full_order_stability": [order["same_priority_order"], order["valid_paired_windows"]],
            "pair_relation_stability": [order["same_pair_relations"], order["pair_denominator"]],
            "all_tie_outputs": main["all_candidates_tied_windows"],
        })
    return {
        "status": "PUBLIC_PREFLIGHT_COMPLETE_PRIVATE_REVIEW_PENDING",
        "source_status": summary["status"],
        "source_records": summary["record_count"],
        "methods": table,
        "total_valid_method_windows": sum(x["valid_outputs"] for x in table),
        "total_planned_method_windows": len(METHODS) * 16,
        "human_gold": 0,
        **METRICS,
        "scope": "Existing B0 aggregate only; not a new model run or gold annotation",
    }


def top_pairs(output):
    """Only strict top-tier vs immediately next-tier pairs; ties NOT forced."""
    ranking = output["ranking"]
    if not ranking or any(not isinstance(group, list) or not group for group in ranking):
        raise ValueError("Invalid ranking")
    if len({item for group in ranking for item in group}) != sum(map(len, ranking)):
        raise ValueError("Duplicate candidate")
    if len(ranking) < 2:
        return []
    return [(hi, lo) for hi in sorted(ranking[0]) for lo in sorted(ranking[1])]


def make_cards(cases, runs, seed=SEED, methods=METHODS):
    """Pure builder; all resulting cards/private crosswalk MUST remain local."""
    case_ids = [c["case_id"] for c in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Duplicate case IDs")
    by_run = {}
    for r in runs:
        key = (r["case_id"], r["method"])
        if key in by_run:
            raise ValueError("Duplicate model record")
        by_run[key] = r
    case_cards, explanation_cards, crosswalk, missing = [], [], [], []
    for c in sorted(cases, key=lambda x: x["case_id"]):
        ident = c["case_id"]
        case_card_id = "C-" + token(seed, "case", ident)
        # Blind the source candidate presentation order, without altering evidence.
        private_packet = json.loads(json.dumps(c["packet"], ensure_ascii=False))
        private_packet["records"].pop("case_id", None)
        private_packet["records"].pop("subject_id", None)
        random.Random(token(seed, "candidate_order", ident)).shuffle(private_packet["candidates"])
        case_cards.append({
            "card_id": case_card_id,
            "goal_policy": "UNSPECIFIED_IN_B0",
            "review_task": "Check source scope and whether priority is identifiable; DO NOT infer a unique top-1",
            "data_and_sources": private_packet,
        })
        crosswalk.append({"card_id": case_card_id, "case_id": ident, "method": None})
        for method in methods:
            r = by_run.get((ident, method))
            if not r or r.get("status") != "EXECUTED":
                missing.append({"case_id": ident, "method": method,
                                "status": "MISSING_RECORD" if not r else r.get("status", "UNKNOWN"),
                                "error_type": r.get("error_type") if r else None,
                                "error": r.get("error") if r else None,
                                "validation_errors": r.get("validation_errors", []) if r else []})
                continue
            output = r["output"]
            ranking = output["ranking"]
            if sorted(k for group in ranking for k in group) != sorted(c["candidate_ids"]):
                raise ValueError("Accepted ranking does not partition frozen candidates")
            items = {x["id"]: x for x in output["items"]}
            if set(items) != set(c["candidate_ids"]) or len(output["items"]) != len(items):
                raise ValueError("Accepted output has incorrect item set")
            pairs = top_pairs(output)
            if not pairs:
                # Keep ties in the denominator rather than silently discarding them.
                pairs = [(None, None)]
            for index, (hi, lo) in enumerate(pairs):
                card_id = "E-" + token(seed, "explanation", ident, method, index)
                reasons = [x["reason"] for x in output.get("pairwise_reasons", [])
                           if x.get("higher") == hi and x.get("lower") == lo]
                card = {
                    "card_id": card_id,
                    "case_card_id": case_card_id,
                    "goal_policy": "UNSPECIFIED_IN_B0",
                    "higher": hi, "lower": lo,
                    "ranking": ranking,
                    "higher_item": items.get(hi) if hi else None,
                    "lower_item": items.get(lo) if lo else None,
                    "explicit_pairwise_reasons": reasons,
                    "pairwise_reason_absent": bool(hi and not reasons),
                    "task": "Audit local support and whether the stated relative claim follows. Do not judge hidden model internals.",
                }
                explanation_cards.append(card)
                crosswalk.append({"card_id": card_id, "case_id": ident,
                                  "method": method, "higher": hi, "lower": lo})
    rng = random.Random(seed)
    rng.shuffle(case_cards)
    rng.shuffle(explanation_cards)
    return case_cards, explanation_cards, crosswalk, missing


def check_blinding(case_cards, explanation_cards, private_ids):
    """Refuse to alter explanations to hide self-identification; block instead.

    Text/style may still suggest a method. Masking is not empirically established
    blinding, and is not a behavioral-faithfulness measurement.
    """
    text = json.dumps([case_cards, explanation_cards], ensure_ascii=False)
    if any(ident in text for ident in private_ids):
        raise ValueError("Private source identity remains in review cards")
    pattern = r"(?i)\b(?:B[1-5]_[a-z_]+|BM_[a-z_]+|S3[ab]_[a-z_]+|S4(?:_relative)?|CRITIC|RE2|Self[-_ ]Refine|RARR)\b"
    if re.search(pattern, text):
        raise ValueError("Method identifier remains in review cards; steward review required")
    for card in case_cards:
        if any(k in card for k in ("method", "output", "ranking")):
            raise ValueError("Stage 1 contains model metadata")
    return {"method_identifier_matches": 0, "private_identity_matches": 0,
            "stage1_model_metadata_matches": 0}


def check_freeze(frozen, cases, release, packets):
    from ..experiment_b0.core import digest
    require(frozen["id"] == digest({k: v for k, v in frozen.items() if k != "id"}),
            "Frozen manifest self-hash mismatch")
    for name, expected_sha in frozen["files"].items():
        require(file_sha(B0 / name) == expected_sha, "Frozen B0 code/protocol mismatch")
    require(file_sha(B0 / "results/upstream_pins.json") == frozen["upstream_pins_sha256"],
            "B0 upstream pins mismatch")
    require(release == frozen["p1_release_id"], "P1 release identity mismatch")
    expected = {c["case_id"]: c for c in frozen["cases"]}
    require(len(cases) == len(expected) == len(frozen["cases"]) == 16,
            "Frozen case count mismatch")
    require(len({c["subject_id"] for c in cases}) == 16, "Participant count mismatch")
    for c in cases:
        old = expected.get(c["case_id"])
        require(old is not None and all(old[k] == c[k] for k in
                ("subject_id", "block", "candidate_ids")), "Frozen case identity mismatch")
        require(c["candidate_ids"] == EXPECTED_CANDIDATES and len(c["days"]) == 42,
                "Frozen candidate/window mismatch")
        require(digest(packets[c["case_id"]]) == old["input_sha256"],
                "Frozen case payload hash mismatch")
    return expected


def check_runs(cases, runs, frozen):
    """Missing files block preparation; recorded B0 failures retain their slots."""
    from ..experiment_b0.core import validate
    expected = {c["case_id"]: c for c in frozen["cases"]}
    by_case = {c["case_id"]: c for c in cases}
    seen = set()
    statuses = {m: Counter() for m in METHODS}
    for r in runs:
        if r["method"] not in METHODS:
            continue
        key = (r["case_id"], r["method"])
        require(key not in seen, "Duplicate diagnostic record")
        seen.add(key)
        old = expected.get(r["case_id"])
        require(old is not None and r.get("subject_id") == old["subject_id"],
                "Run case identity mismatch")
        require(r.get("input_sha256") == old["input_sha256"], "Run input hash mismatch")
        require(r.get("status") in ("EXECUTED", "FAILED", "INVALID_OUTPUT"),
                "Unknown B0 diagnostic run status")
        if r["status"] == "EXECUTED":
            try:
                errors = validate(r.get("output"), by_case[r["case_id"]])
            except (TypeError, KeyError, ValueError) as exc:
                raise AuditBlocked("BLOCKED_FREEZE_MISMATCH", "Malformed accepted B0 output") from exc
            require(not errors, "Previously accepted B0 output no longer validates")
        statuses[r["method"]][r["status"]] += 1
    missing = [{"case_id": c["case_id"], "method": m, "status": "MISSING_RECORD"}
               for c in cases for m in METHODS if (c["case_id"], m) not in seen]
    if missing:
        raise AuditBlocked("BLOCKED_MISSING_PRIVATE_DATA", "Missing diagnostic run files; no cards created")
    return {m: dict(v) for m, v in statuses.items()}


def prepare_local(output):
    """Run only on the machine holding ignored B0/local data and frozen inputs."""
    private_root = (ROOT / "local").resolve()
    dest = Path(output).resolve()
    if not dest.is_relative_to(private_root):
        raise ValueError("Refusing to write private review cards outside experiment_c0/local")
    if dest.exists():
        raise FileExistsError("Choose a new output version; existing private output is immutable")
    import subprocess
    from ..experiment_b0.core import REPO
    ignored = subprocess.run(["git", "check-ignore", "-q", str(dest / "manifest.json")],
                             cwd=REPO, capture_output=True)
    if ignored.returncode != 0:
        raise ValueError("Private output is not Git-ignored")
    from ..experiment_b0.core import selected, payload
    from ..experiment_b0.run import verify
    # Read-only verification; neither Client nor any inference entry point is used.
    verify()
    frozen = load(B0 / "configs" / "freeze.json")
    cases, knowledge, release = selected()
    payloads = {c["case_id"]: payload(c, knowledge) for c in cases}
    check_freeze(frozen, cases, release, payloads)
    packets = [{"case_id": c["case_id"], "candidate_ids": c["candidate_ids"],
                "packet": payloads[c["case_id"]]} for c in cases]
    files = sorted((B0 / "local" / "runs" / "main").rglob("*.json"))
    if not files:
        raise AuditBlocked("BLOCKED_MISSING_PRIVATE_DATA", "B0 private predictions unavailable. No cards created.")
    runs = [load(p) for p in files]
    statuses = check_runs(cases, runs, frozen)
    public = public_audit(load(B0 / "results/comparison.json"))
    require(all(statuses[r["method"]] == r["status_counts"] for r in public["methods"]),
            "Private diagnostic statuses disagree with public B0 aggregate")
    # Public fixed seeds allow reverse-mapping opaque IDs. Keep the real seed private.
    seed = secrets.token_hex(32)
    case_cards, explanation_cards, key, missing = make_cards(packets, runs, seed=seed)
    blinding = check_blinding(case_cards, explanation_cards,
                             [c[k] for c in cases for k in ("case_id", "subject_id")])
    dest.mkdir(parents=True, exist_ok=False)
    stage1 = dest / "review_packets/stage1"
    stage2 = dest / "review_packets/stage2"
    steward = dest / "steward"
    for directory in (stage1, stage2, steward):
        directory.mkdir(parents=True)
    jsonl(stage1 / "stage1_cases.jsonl", case_cards)
    jsonl(stage2 / "stage2_explanations.jsonl", explanation_cards)
    # This crosswalk reveals methods and MUST NOT be shown to reviewers.
    jsonl(steward / "STUDY_STEWARD_ONLY_crosswalk.jsonl", key)
    jsonl(steward / "all_failure_slots.jsonl", missing)
    jsonl(steward / "all_slots.jsonl", [
        {"case_id": r["case_id"], "method": r["method"], "status": r["status"]}
        for r in runs if r["method"] in METHODS])
    write(steward / "reproducibility.json", {"private_seed": seed,
          "source_run_files": {p.relative_to(B0).as_posix(): file_sha(p) for p in files},
          "source_freeze_sha256": file_sha(B0 / "configs/freeze.json"),
          "source_comparison_sha256": file_sha(B0 / "results/comparison.json")})
    stage1_fields = ["card_id", "source_scope", "priority_determinable", "notes"]
    stage2_fields = ["card_id", "evidence_grounding", "local_support",
                     "contrastive_support", "error_tags", "notes"]
    for directory, stage, cards, fields in ((stage1, "stage1", case_cards, stage1_fields),
                                           (stage2, "stage2", explanation_cards, stage2_fields)):
        template = [{"card_id": x["card_id"], **{f: "" for f in fields[1:]}} for x in cards]
        jsonl(directory / (stage + "_rater_A_TEMPLATE.jsonl"), template)
        jsonl(directory / (stage + "_rater_B_TEMPLATE.jsonl"), template)
    card_counts = Counter(r["method"] for r in key if r["method"] is not None)
    def git_value(*args):
        return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()
    source_ref = "origin/research/experiment-b0-sota"
    summary = {"status": "PREPARED_NOT_ANNOTATED", "case_cards": len(case_cards),
               "explanation_cards": len(explanation_cards), "missing_or_invalid_slots": len(missing),
               "planned_slots": len(cases) * len(METHODS), "valid_slots": len(cases) * len(METHODS) - len(missing),
               "participants": 16, "days_per_case": 42, "candidates_per_case": 5,
               "diagnostic_methods": len(METHODS), "missing_record_slots": 0,
               "human_raters_recorded": 0, "human_gold": 0, **METRICS,
               "method_counts": [{"method": m, "planned": 16,
                   "valid_outputs": statuses[m].get("EXECUTED", 0),
                   "status_counts": statuses[m], "explanation_cards": card_counts[m]} for m in METHODS],
               "blinding_checks": blinding,
               "provenance": {"b0_head": git_value("rev-parse", source_ref),
                   "execution_head": git_value("rev-parse", "HEAD"),
                   "b0_comparison_blob": git_value("rev-parse", source_ref + ":research/problem_reidentification/experiment_b0/results/comparison.json"),
                   "b0_freeze_id": frozen["id"], "p1_release_id": release,
                   "c0_code_sha256": {p.name: file_sha(p) for p in sorted(ROOT.glob("*.py"))}},
               "frozen_payload_hashes_verified": 16, "model_requests": 0,
               "review_status": "Both stages await independent humans; no annotation or fidelity claim"}
    inventory = []
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            inventory.append({"path": p.relative_to(dest).as_posix(), "bytes": p.stat().st_size,
                              "sha256": file_sha(p),
                              "rows": len(p.read_text(encoding="utf-8").splitlines()) if p.suffix == ".jsonl" else None})
    write(dest / "manifest.json", {**summary, "artifacts": inventory})
    return summary


def main():
    ap = argparse.ArgumentParser(description="C0-A offline preflight / private blind-review cards")
    ap.add_argument("action", choices=["public-audit", "prepare-local"])
    ap.add_argument("--output", default=str(ROOT / "local" / "c0a-v1"))
    ap.add_argument("--input", default=str(B0 / "results" / "comparison.json"),
                    help="Public B0 comparison file; optional verified subset for offline replay")
    args = ap.parse_args()
    try:
        if args.action == "public-audit":
            result = public_audit(load(args.input))
        else:
            result = prepare_local(args.output)
    except (FileNotFoundError, AuditBlocked) as exc:
        status = exc.status if isinstance(exc, AuditBlocked) else "BLOCKED_MISSING_PRIVATE_DATA"
        print(json.dumps({"status": status, "human_gold": 0, **METRICS}))
        raise
    except ValueError:
        # Underlying frozen-release/source verifiers raise ValueError on mismatch.
        print(json.dumps({"status": "BLOCKED_FREEZE_MISMATCH", "human_gold": 0, **METRICS}))
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
