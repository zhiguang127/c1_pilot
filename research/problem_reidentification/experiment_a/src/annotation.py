"""Separate A1 blind review and applicability-only import from existing P1 review."""
import json
import random
from datetime import datetime
from html import escape
from pathlib import Path

from research.problem_reidentification.p1.annotations import validate_roster
from .common import LABELS, P1, digest, freeze, private_path, read, rows, sha, verify, write, write_rows
from .data import candidates, evidence_value


def packets(stage, release, output):
    output = private_path(output)
    if output.exists():
        raise ValueError("Review packet exists; choose a new version")
    cases, knowledge, release_id = candidates(stage, release)
    output.mkdir(parents=True)
    mappings, names = {}, []
    for reviewer in ("A", "B"):
        rng = random.Random("experiment-a-blind-v1:" + release_id + reviewer)
        ordered = list(cases)
        rng.shuffle(ordered)
        templates, mapping = [], {}
        folder = output / reviewer
        folder.mkdir()
        for i, case in enumerate(ordered, 1):
            ref = f"CASE-{i:03}"
            kids = list(case["candidate_ids"])
            rng.shuffle(kids)
            refs = {f"C{j}": kid for j, kid in enumerate(kids, 1)}
            mapping[ref] = {"case_id": case["case_id"], "candidates": refs}
            template = {"release_id": release_id, "reviewer_id": reviewer, "case_ref": ref,
                        "status": "draft", "human_attestation": False, "completed_at": None,
                        "items": [{"candidate_ref": r, "topic_relevance": None, "applicability": None,
                            "observations": [], "conditions": [], "missing_information": [],
                            "condition_judgments": [], "rationale": "", "source_scope_disputed": False}
                            for r in refs]}
            templates.append(template)
            safe = {"context": case["context"], "quality_notes": case["quality_notes"], "days": case["days"]}
            body = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>" + reviewer + " / " + ref + "</title>",
                    "<style>body{font:15px/1.6 system-ui;margin:2rem;max-width:1200px}pre{white-space:pre-wrap}section{border-top:1px solid #aaa}</style>",
                    "<h1>" + reviewer + " / " + ref + "</h1><p>独立人工判断。基线 d1–d28，当前 d29–d42；null 是未知。先记录主题相关性，再判断个人适用性。来源条件是未获人工确认的草案，允许争议并暂停。无需选择至少一条适用知识。</p>",
                    "<p>将本卡附带的 JSON 模板另存为提交版本。逐条件填写 satisfied / violated / unknown / not_applicable_to_condition、观测引用和理由。请勿查看另一评审或模型预测。</p>",
                    "<pre>" + escape(json.dumps(safe, ensure_ascii=False, indent=2)) + "</pre>"]
            for r, kid in refs.items():
                k = knowledge[kid]
                body.append("<section><h2>" + r + " " + escape(k["title"]) + "</h2><p>" + escape(k["content"]) + "</p>")
                body.append("<p><a href='" + escape(k["source_url"], quote=True) + "'>" + escape(k["source"]) + "</a> " + escape(k["source_locator"]) + "</p><ul>")
                for field, values in k["applicability"].items():
                    for j, text in enumerate(values):
                        body.append("<li>" + r + "." + field + "." + str(j) + ": " + escape(text) + "</li>")
                body.append("</ul></section>")
            body.append("<h2>本卡空白提交模板</h2><pre>" + escape(json.dumps(template, ensure_ascii=False, indent=2)) + "</pre></html>")
            filename = reviewer + "/" + ref + ".html"
            (output / filename).write_text("".join(body), encoding="utf-8")
            names.append(filename)
        filename = reviewer + "/annotations.template.jsonl"
        write_rows(output / filename, templates)
        names.append(filename)
        mappings[reviewer] = mapping
    write(output / "private/assignments.json", {"release_id": release_id, "stage": stage, "reviewers": mappings})
    names.append("private/assignments.json")
    write(output / "roster.template.json", {"reviewers": [
        {"reviewer_id": r, "person_id": "", "role": "adjudicator" if r == "C" else "reviewer",
         "is_human": False, "qualified": False, "background": "", "independence_attested": False}
        for r in ("A", "B", "C")]})
    names.append("roster.template.json")
    result = freeze(output, names, {"version": "experiment-a-blind-v1", "data_release_id": release_id,
                                    "stage": stage, "status": "PENDING_HUMAN_ANNOTATION"})
    return {"packets": 2, "cases_per_reviewer": len(cases), "pairs_per_reviewer": sum(len(c["candidate_ids"]) for c in cases),
            "packet_release_id": result["release_id"], "status": "PENDING_HUMAN_ANNOTATION"}


def validate_a1_record(record, reviewer, mapping, cases, knowledge, release_id):
    if (record.get("status") != "complete" or record.get("human_attestation") is not True
        or record.get("reviewer_id") != reviewer or record.get("release_id") != release_id):
        raise ValueError("Completed independent human submission and exact release required")
    dt = datetime.fromisoformat(record["completed_at"])
    if dt.tzinfo is None:
        raise ValueError("Human completion timestamp needs timezone")
    assignment = mapping[record["case_ref"]]
    case = cases[assignment["case_id"]]
    expected = assignment["candidates"]
    if len(record["items"]) != len(expected) or {i["candidate_ref"] for i in record["items"]} != set(expected):
        raise ValueError("Missing, duplicate or unknown human candidate")
    normalized = {}
    for item in record["items"]:
        kid = expected[item["candidate_ref"]]
        k = knowledge[kid]
        if item["applicability"] not in LABELS or item["topic_relevance"] not in ("related", "not_related", "uncertain"):
            raise ValueError("Separate valid topic and applicability labels required")
        if not item["rationale"].strip() or not item["conditions"]:
            raise ValueError("Human source-grounded rationale and condition references required")
        known = {f"{field}.{i}" for field, values in k["applicability"].items() for i, _ in enumerate(values)}
        prefix = item["candidate_ref"] + "."
        conds = [c.removeprefix(prefix) for c in item["conditions"]]
        if any(c not in known for c in conds):
            raise ValueError("Unknown condition citation")
        for ref in item["observations"]:
            value = evidence_value(case, ref)
            if value is None or (ref.endswith(".resting_heart_rate_bpm") and value == 0):
                raise ValueError("Missing or unusable physiological evidence cited")
        if item["applicability"] == "insufficient_information" and not item["missing_information"]:
            raise ValueError("Unknown needs an explicit missing-information description")
        if item["applicability"] in ("applicable", "not_applicable") and not item["observations"]:
            raise ValueError("Definite judgment requires observed personal evidence")
        judgments = item["condition_judgments"]
        if len(judgments) != len(known) or {j["condition_id"].removeprefix(prefix) for j in judgments} != known:
            raise ValueError("Every draft condition requires one human status")
        for judgment in judgments:
            if judgment["status"] not in {"satisfied", "violated", "unknown", "not_applicable_to_condition"} or not judgment["rationale"].strip():
                raise ValueError("Invalid condition judgment")
            for ref in judgment["observations"]:
                if evidence_value(case, ref) is None:
                    raise ValueError("Condition evidence is missing")
        normalized[kid] = {"case_id": case["case_id"], "knowledge_id": kid, **item,
                           "condition_judgments": [{**j, "condition_id": j["condition_id"].removeprefix(prefix)} for j in judgments],
                           "conditions": conds}
        normalized[kid].pop("candidate_ref")
    return normalized


def semantic(item):
    return {"applicability": item["applicability"], "topic_relevance": item.get("topic_relevance"),
            "source_scope_disputed": item.get("source_scope_disputed", False),
            "conditions": sorted((j["condition_id"], j["status"]) for j in item.get("condition_judgments", []))}


def import_gold(stage, release, packets_path, roster, a, b, adjudications, output):
    output = private_path(output)
    case_list, knowledge, release_id = candidates(stage, release)
    cases = {c["case_id"]: c for c in case_list}
    validate_roster(read(roster))
    completed = {r: {} for r in ("A", "B", "C")}
    if stage == "a0":
        from research.problem_reidentification.p1.annotations import load_annotations
        from research.problem_reidentification.p1.packets import verify_packets
        assignment = verify_packets(P1, packets_path)
        k_original = {k["knowledge_id"]: k for k in rows(P1 / "knowledge.jsonl")}
        parsed = {}
        for role, path in (("A", a), ("B", b), ("C", adjudications)):
            data = load_annotations(path, role, P1, assignment, k_original) if path else {}
            completed[role] = {cid: datetime.fromisoformat(r["raw"]["completed_at"]) for cid, r in data.items()}
            parsed[role] = {cid: {kid: {"case_id": cid, "knowledge_id": kid, "applicability": label,
                                      "topic_relevance": None, "source_scope_disputed": "source_scope" in r["raw"]["decision"]["reason_codes"]}
                                    for kid, label in r["items"].items()} for cid, r in data.items()}
    else:
        verify(packets_path)
        assignment = read(Path(packets_path) / "private/assignments.json")
        if assignment["release_id"] != release_id or assignment["stage"] != stage:
            raise ValueError("Review packets belong to a different data release")
        parsed = {}
        for role, path in (("A", a), ("B", b), ("C", adjudications)):
            parsed[role] = {}
            for record in rows(path) if path else []:
                mapping = assignment["reviewers"]["A" if role == "C" else role]
                if role == "C" and record.get("reviewed_reviewers") != ["A", "B"]:
                    raise ValueError("C must explicitly review A and B")
                normalized = validate_a1_record(record, role, mapping, cases, knowledge, release_id)
                cid = mapping[record["case_ref"]]["case_id"]
                if cid in parsed[role]:
                    raise ValueError("Duplicate human case")
                parsed[role][cid] = normalized
                completed[role][cid] = datetime.fromisoformat(record["completed_at"])
    final, unresolved = [], []
    for case in case_list:
        cid = case["case_id"]
        for kid in case["candidate_ids"]:
            left, right = parsed["A"].get(cid, {}).get(kid), parsed["B"].get(cid, {}).get(kid)
            chosen = None
            if left and right:
                if semantic(left) == semantic(right):
                    chosen = left
                else:
                    chosen = parsed["C"].get(cid, {}).get(kid)
                    if chosen is not None and completed["C"][cid] < max(completed["A"][cid], completed["B"][cid]):
                        raise ValueError("Adjudication cannot precede either independent submission")
            if chosen is None or chosen.get("source_scope_disputed"):
                unresolved.append({"case_id": cid, "knowledge_id": kid})
            else:
                final.append(chosen)
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / "gold.jsonl", final)
    report = {"stage": stage, "data_release_id": release_id,
              "status": "ANNOTATED" if not unresolved else "PENDING_HUMAN_ANNOTATION",
              "gold_kind": "INDEPENDENT_HUMAN_DOUBLE_REVIEW_ADJUDICATED", "resolved_pairs": len(final),
              "expected_pairs": sum(len(c["candidate_ids"]) for c in case_list), "unresolved": unresolved,
              "priority_labels_imported": False, "source_files_sha256": {role: sha(path) for role, path in
                  (("A", a), ("B", b), ("C", adjudications), ("roster", roster)) if path}}
    write(output / "provenance.json", report)
    freeze(output, ["gold.jsonl", "provenance.json"], {"version": "human-gold-v1", "data_release_id": release_id})
    return {k: v for k, v in report.items() if k != "unresolved"}
