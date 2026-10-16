"""Independent offline review cards; private crosswalk is never in a reviewer folder."""
from html import escape
from itertools import combinations
import random
from pathlib import Path

from .dataset import ROOT, METRICS, digest, jsonl, read_json, sha, verify_release, write_json, write_jsonl
from .form import render_form


def generate_packets(release, output):
    release, output = Path(release), Path(output)
    freeze = verify_release(release)
    if output.exists():
        raise ValueError("Packet directory exists; refusing to overwrite")
    cases = jsonl(release / "cases.jsonl")
    knowledge = {k["knowledge_id"]: k for k in jsonl(release / "knowledge.jsonl")}
    plan = read_json(release / "sampling_plan.json")
    output.mkdir(parents=True)
    (output / "private").mkdir()
    maps = {}
    for reviewer in ("A", "B"):
        directory = output / reviewer
        directory.mkdir()
        rng = random.Random(plan["randomization_seed"] + ":" + reviewer + ":" + freeze["release_id"])
        ordered = list(cases)
        rng.shuffle(ordered)
        templates = []
        mapping = {}
        for index, case in enumerate(ordered, 1):
            case_ref = "CASE-" + str(index).zfill(3)
            candidates = list(case["candidate_ids"])
            rng.shuffle(candidates)
            refs = {"C" + str(i): kid for i, kid in enumerate(candidates, 1)}
            mapping[case_ref] = {"case_id": case["case_id"], "candidates": refs}
            template = {"release_id": freeze["release_id"], "reviewer_id": reviewer,
                        "case_ref": case_ref, "status": "draft", "completed_at": None,
                        "human_attestation": False,
                        "items": [{"candidate_ref": ref, "applicability": None,
                                   "observations": [], "conditions": [], "rationale": "",
                                   "missing_information": []} for ref in refs],
                        "comparisons": [],
                        "decision": {"priority": None, "top_outcome": None, "best_set": [],
                                     "observations": [], "conditions": [], "rationale": "",
                                     "missing_information": [], "reason_codes": []}}
            templates.append(template)
            title = reviewer + " / " + case_ref
            body = ["<h1>" + escape(title) + "</h1>",
                    "<p>独立人工盲评。先判断每条适用性，再比较适用候选；允许并列、不可比较和信息不足。"
                    "第 1–28 天为历史基线，第 29–42 天为当前窗口，决策时点为第 42 天末。"
                    "null 表示未知；0 是记录值，但佩戴时间未知时不能认定真实无活动。</p>",
                    "<p>指标单位：sleep/time in bed/activity/sedentary = 分钟；RHR = bpm；clock = 源本地钟点；weekday = 周一 1 至周日 7。"
                    "设备活动等级不等于独立核实的运动强度，sedentary 不证明坐姿。"
                    "证据引用格式：d29.sleep_minutes；context.population；C1.observable_conditions.0。</p>",
                    "<h2>已提供背景（null = 未知）</h2><ul>"]
            body += ["<li>context." + escape(k) + ": " + escape("未知（null）" if v is None else str(v)) + "</li>" for k, v in case["context"].items()]
            body += ["</ul><h2>数据限制</h2><ul>"] + ["<li>" + escape(x) + "</li>" for x in case["quality_notes"]] + ["</ul>"]
            body += ["<h2>原始日序列</h2><div class='table'><table><thead><tr><th>day</th><th>weekday</th><th>phase</th><th>quality_flags</th>"]
            body += ["<th>" + escape(m) + "</th>" for m in METRICS]
            body += ["</tr></thead><tbody>"]
            for row in case["days"]:
                vals = [row["day"], row["weekday"], row["phase"], ", ".join(row["quality_flags"])] + [row["metrics"][m] for m in METRICS]
                body.append("<tr>" + "".join("<td>" + escape("null" if v is None else str(v)) + "</td>" for v in vals) + "</tr>")
            body += ["</tbody></table></div><h2>随机排列的候选知识</h2>"]
            for ref, kid in refs.items():
                item = knowledge[kid]
                body += ["<section><h3>" + ref + ": " + escape(item["title"]) + "</h3><p>" + escape(item["content"]) + "</p>",
                         "<p>来源：<a href='" + escape(item["source_url"], quote=True) + "'>" + escape(item["source"]) + "</a>; " + escape(item["source_locator"]) + "; 原快照访问日期 " + item["source_accessed_on"] + "</p><ul>"]
                for field, values in item["applicability"].items():
                    body += ["<li>" + ref + "." + field + "." + str(i) + ": " + escape(v) + "</li>" for i, v in enumerate(values)]
                body += ["<li>" + ref + ".support." + str(i) + ": " + escape(v) + "</li>" for i, v in enumerate(item["support_anchors"])]
                body += ["</ul><p>" + escape(item["source_review"]) + "</p></section>"]
            html = "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>" + escape(title) + "</title>"
            html += "<style>body{font:15px/1.6 system-ui;margin:2rem;max-width:1400px}.table{overflow:auto}table{border-collapse:collapse;font-size:12px}th,td{padding:5px;border:1px solid #ccc}thead{background:#edf2f5}section{border-top:2px solid #ccc;margin-top:2rem}h1,h2{color:#193b55}</style>"
            (directory / (case_ref + ".html")).write_text(html + "".join(body) + render_form(template) + "</html>", encoding="utf-8")
        write_jsonl(directory / "annotations.template.jsonl", templates)
        (directory / "P1_ANNOTATION_GUIDE.md").write_bytes((release / "P1_ANNOTATION_GUIDE.md").read_bytes())
        write_json(directory / "packet_manifest.json", {
            "release_id": freeze["release_id"], "reviewer_id": reviewer,
            "files": {p.name: sha(p) for p in sorted(directory.iterdir())}})
        maps[reviewer] = mapping
    assignment = {"release_id": freeze["release_id"], "reviewers": maps}
    write_json(output / "private/assignments.json", assignment)
    write_json(output / "roster.template.json", {"reviewers": [
        {"reviewer_id": i, "person_id": "", "role": role, "is_human": False, "qualified": False,
         "background": "", "independence_attested": False}
        for i, role in [("A", "reviewer"), ("B", "reviewer"), ("C", "adjudicator")]]})
    write_json(output / "private/packet_freeze.json", {
        "release_id": freeze["release_id"], "assignment_sha256": sha(output / "private/assignments.json"),
        "reviewer_manifest_sha256": {r: sha(output / r / "packet_manifest.json") for r in ("A", "B")},
        "generator_sha256": sha(Path(__file__))})
    return {"case_count": len(cases), "reviewer_packets": 2, "status": "PREPARED_NOT_ANNOTATED"}


def verify_packets(release, packets):
    packets = Path(packets)
    release_freeze = verify_release(release)
    frozen = read_json(packets / "private/packet_freeze.json")
    if frozen["release_id"] != release_freeze["release_id"] or sha(packets / "private/assignments.json") != frozen["assignment_sha256"]:
        raise ValueError("Packet assignment changed or release mismatch")
    for reviewer, expected in frozen["reviewer_manifest_sha256"].items():
        folder = packets / reviewer
        if sha(folder / "packet_manifest.json") != expected:
            raise ValueError("Packet manifest changed")
        for name, expected_hash in read_json(folder / "packet_manifest.json")["files"].items():
            if Path(name).name != name or sha(folder / name) != expected_hash:
                raise ValueError("Blind card changed: " + name)
    return read_json(packets / "private/assignments.json")
