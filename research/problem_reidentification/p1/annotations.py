"""Human annotation validation and agreement analysis. No model client is used."""
from collections import Counter
from datetime import datetime
from html import escape
from itertools import combinations
import json
from pathlib import Path
import shutil

from .dataset import jsonl, read_json, sha, verify_release, write_json, write_jsonl
from .form import render_form
from .packets import verify_packets

APPLICABILITY = {"applicable", "not_applicable", "insufficient_information"}
RELATIONS = {"left_preferred", "right_preferred", "tie", "incomparable", "insufficient_information"}
PRIORITY = {"clear", "partial", "none", "insufficient_information", "not_comparable"}
TOP = {"unique_best", "tied_best", "undetermined", "insufficient_information", "not_comparable"}
MISSING = {"symptoms", "diagnoses", "medications", "goals", "preferences", "age",
           "work_schedule", "wear_time", "measurement_quality", "activity_intensity",
           "posture", "sleep_experience", "timezone", "history", "other"}
REASONS = {"applicability_condition", "observation_interpretation", "measurement_uncertainty",
           "missing_context", "priority_criterion", "reasonable_tie", "source_scope", "other"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_roster(roster):
    people = roster.get("reviewers", [])
    require(len(people) == 3 and {p["reviewer_id"] for p in people} == {"A", "B", "C"}, "Need exactly reviewers A/B and adjudicator C")
    require(all(p.get("person_id") and p.get("background", "").strip() for p in people), "Human identities/backgrounds are required")
    require(len({p["person_id"] for p in people}) == 3, "Three different humans are required")
    require(all(p.get("is_human") is True and p.get("independence_attested") is True for p in people), "Independent human attestation required")
    require(all(p.get("role") == ("adjudicator" if p["reviewer_id"] == "C" else "reviewer") for p in people), "Invalid reviewer roles")
    require(any(p.get("qualified") is True for p in people if p["reviewer_id"] in {"A", "B"}), "At least one primary reviewer must have relevant health expertise")
    require(next(p for p in people if p["reviewer_id"] == "C").get("qualified") is True, "Qualified third-party adjudicator required")


def observation_refs(case):
    refs = {"context." + k for k, v in case["context"].items() if v is not None}
    refs |= {"d" + str(r["day"]) + "." + k for r in case["days"] for k, v in r["metrics"].items() if v is not None}
    return refs


def condition_refs(knowledge, mapping):
    refs = set()
    for ref, kid in mapping.items():
        for field, values in knowledge[kid]["applicability"].items():
            refs |= {ref + "." + field + "." + str(i) for i in range(len(values))}
        refs |= {ref + ".support." + str(i) for i in range(len(knowledge[kid]["support_anchors"]))}
    return refs


def evidence(record, obs, conditions, need_observation=False):
    require(isinstance(record.get("rationale"), str) and record["rationale"].strip(), "Evidence rationale is required")
    require(isinstance(record.get("observations"), list) and set(record["observations"]) <= obs, "Invalid or missing-value observation reference")
    require(isinstance(record.get("conditions"), list) and bool(record["conditions"]) and set(record["conditions"]) <= conditions, "Source applicability condition references are required")
    require(not need_observation or bool(record["observations"]), "Applicable/priority judgments need observed evidence")
    missing = record.get("missing_information")
    require(isinstance(missing, list) and len(missing) == len(set(missing)) and set(missing) <= MISSING, "Invalid missing-information codes")


def validate_record(record, case, mapping, knowledge, release_id, reviewer):
    require(record.get("reviewer_id") == reviewer and record.get("release_id") == release_id, "Reviewer/release mismatch")
    require(record.get("status") == "complete" and record.get("human_attestation") is True, "Draft or non-human record cannot be analyzed")
    completed = datetime.fromisoformat(record.get("completed_at") or "")
    require(completed.tzinfo is not None, "Completion timestamp requires timezone")
    items = record.get("items", [])
    require(len(items) == len(mapping) and {x["candidate_ref"] for x in items} == set(mapping), "Each candidate needs exactly one applicability judgment")
    obs, conditions = observation_refs(case), condition_refs(knowledge, mapping)
    for item in items:
        require(item.get("applicability") in APPLICABILITY, "Invalid applicability")
        own_conditions = {x for x in conditions if x.startswith(item["candidate_ref"] + ".")}
        evidence(item, obs, own_conditions, item["applicability"] == "applicable")
        if item["applicability"] == "insufficient_information":
            require(bool(item["missing_information"]), "Uncertain applicability requires missing-information codes")
    applicable = sorted(x["candidate_ref"] for x in items if x["applicability"] == "applicable")
    pairs = record.get("comparisons", [])
    expected_pairs = {tuple(p) for p in combinations(applicable, 2)}
    actual_pairs = set()
    edges, ties, unresolved = [], [], []
    for pair in pairs:
        left, right = pair.get("left"), pair.get("right")
        require(left != right and left in applicable and right in applicable, "Pair must use distinct applicable candidates")
        key = tuple(sorted((left, right)))
        require(key not in actual_pairs, "Duplicate pair judgment")
        actual_pairs.add(key)
        relation = pair.get("relation")
        require(relation in RELATIONS, "Invalid priority relation")
        evidence(pair, obs, conditions, relation in {"left_preferred", "right_preferred", "tie"})
        require(any(c.startswith(left + ".") for c in pair["conditions"]) and any(c.startswith(right + ".") for c in pair["conditions"]), "Pair evidence must reference both candidates")
        if relation == "left_preferred": edges.append((left, right))
        elif relation == "right_preferred": edges.append((right, left))
        elif relation == "tie": ties.append((left, right))
        else: unresolved.append(relation)
        if relation == "insufficient_information":
            require(bool(pair["missing_information"]), "Unknown pair needs missing-information codes")
    require(actual_pairs == expected_pairs, "Every pair of applicable candidates must be judged; no silent defaults")
    # Ties form equivalence classes; strict preferences must be acyclic on those classes.
    parent = {x: x for x in applicable}
    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for left, right in ties:
        parent[find(left)] = find(right)
    require(all(find(a) != find(b) for a, b in edges), "Preference contradicts tied candidates")
    graph = {find(x): set() for x in applicable}
    for left, right in edges:
        graph[find(left)].add(find(right))
    def visit(node, active, done):
        require(node not in active, "Cyclic priority judgments")
        if node in done: return
        for other in graph[node]: visit(other, active | {node}, done)
        done.add(node)
    done = set()
    for node in graph: visit(node, set(), done)
    # Explicit pair labels must respect transitive ties/preferences.
    def reachable(a, b, seen=None):
        seen = set() if seen is None else seen
        if a in seen: return False
        return b in graph[a] or any(reachable(x, b, seen | {a}) for x in graph[a])
    for pair in pairs:
        a, b = find(pair["left"]), find(pair["right"])
        if a == b:
            require(pair["relation"] == "tie", "Tie transitivity contradiction")
        elif reachable(a, b):
            require(pair["relation"] == "left_preferred", "Transitive preference contradiction")
        elif reachable(b, a):
            require(pair["relation"] == "right_preferred", "Transitive preference contradiction")
    decision = record.get("decision", {})
    require(decision.get("priority") in PRIORITY and decision.get("top_outcome") in TOP, "Case decision is required")
    evidence(decision, obs, conditions, len(applicable) >= 2 and decision["top_outcome"] in {"unique_best", "tied_best"})
    require(isinstance(decision.get("reason_codes"), list) and bool(decision["reason_codes"]) and set(decision["reason_codes"]) <= REASONS, "Decision reason codes required")
    best = decision.get("best_set", [])
    require(len(best) == len(set(best)) and set(best) <= set(applicable), "Invalid best set")
    if len(applicable) < 2:
        require(decision["priority"] == decision["top_outcome"] == "not_comparable" and not best, "Fewer than two applicable candidates cannot establish P1 priority")
    else:
        priority = ("partial" if unresolved else "clear") if edges else ("insufficient_information" if "insufficient_information" in unresolved else "none")
        require(decision["priority"] == priority, "Priority decision contradicts pair judgments")
        winners = [x for x in applicable if all(x == y or find(x) == find(y) or (x, y) in edges for y in applicable)]
        unknown_applicability = any(x["applicability"] == "insufficient_information" for x in items)
        if unknown_applicability:
            winners = []  # An unassessed candidate could change the best set.
        expected_top = "insufficient_information" if unknown_applicability else "unique_best" if len(winners) == 1 else "tied_best" if winners else "insufficient_information" if "insufficient_information" in unresolved else "undetermined"
        require(decision["top_outcome"] == expected_top and set(best) == set(winners), "Best-set decision contradicts explicit comparisons")
    if decision["top_outcome"] == "insufficient_information" or decision["priority"] == "insufficient_information":
        require(bool(decision["missing_information"]), "Insufficient information requires missing-information codes")
    if reviewer == "C":
        require(record.get("reviewed_reviewers") == ["A", "B"], "Adjudicator must review both independent human records")
    return normalize(record, case["case_id"], mapping)


def normalize(record, case_id, mapping):
    items = {mapping[x["candidate_ref"]]: x["applicability"] for x in record["items"]}
    pairs = {}
    for p in record["comparisons"]:
        left, right = mapping[p["left"]], mapping[p["right"]]
        relation = p["relation"]
        if left > right:
            left, right = right, left
            relation = {"left_preferred": "right_preferred", "right_preferred": "left_preferred"}.get(relation, relation)
        pairs[left + "|" + right] = relation
    return {"case_id": case_id, "reviewer_id": record["reviewer_id"], "items": items,
            "pairs": pairs, "priority": record["decision"]["priority"],
            "top_outcome": record["decision"]["top_outcome"],
            "best_set": sorted(mapping[x] for x in record["decision"]["best_set"]), "raw": record}


def semantic(record):
    return {k: record[k] for k in ("items", "pairs", "priority", "top_outcome", "best_set")}


def load_annotations(path, reviewer, release, assignments, knowledge):
    cases = {c["case_id"]: c for c in jsonl(Path(release) / "cases.jsonl")}
    mapping = assignments["reviewers"]["A" if reviewer == "C" else reviewer]
    result = {}
    for record in jsonl(path):
        require(record.get("case_ref") in mapping, "Unknown case reference")
        assignment = mapping[record["case_ref"]]
        case_id = assignment["case_id"]
        require(case_id not in result, "Duplicate case annotation")
        result[case_id] = validate_record(record, cases[case_id], assignment["candidates"], knowledge, assignments["release_id"], reviewer)
    return result


def agreement(left, right):
    require(len(left) == len(right), "Agreement vectors differ in length")
    n = len(left)
    if not n:
        return {"n": 0, "exact_agreement": None, "cohens_kappa": None, "kappa_note": "No paired human observations", "confusion": {}}
    observed = sum(a == b for a, b in zip(left, right)) / n
    ca, cb = Counter(left), Counter(right)
    chance = sum(ca[k] * cb[k] for k in ca.keys() | cb.keys()) / (n * n)
    confusion = Counter(a + "|" + b for a, b in zip(left, right))
    return {"n": n, "exact_agreement": observed,
            "cohens_kappa": (observed - chance) / (1 - chance) if chance < 1 else None,
            "kappa_note": "Undefined: both reviewers use one identical category" if chance == 1 else "Nominal, unweighted; descriptive within-participant dependence remains",
            "confusion": dict(sorted(confusion.items()))}


def distribution(values, categories):
    count = Counter(values)
    n = sum(count.values())
    return {"denominator": n, "counts": {k: count[k] for k in sorted(categories)},
            "proportions": {k: count[k] / n if n else None for k in sorted(categories)}}


def analyze(release, packets=None, roster=None, a=None, b=None, adjudications=None):
    freeze = verify_release(release)
    audit = read_json(Path(release) / "import_audit.json")
    cases = jsonl(Path(release) / "cases.jsonl")
    result = {"release_id": freeze["release_id"], "status": audit["status"],
              "real_case_count": len(cases), "participant_count": audit["participant_count"],
              "human_annotation_counts": {"A": 0, "B": 0, "C": 0},
              "agreement": None, "applicability": None, "priority": None, "top_outcome": None,
              "clearly_prioritized_case_proportion": None, "unresolved_case_ids": [c["case_id"] for c in cases],
              "reason_counts": None, "missing_information_counts": None,
              "conclusion": "No research conclusion without complete independent human review and adjudication."}
    if not any((a, b, adjudications)):
        return result
    require(packets is not None and roster is not None, "Frozen packets and human roster required")
    assignments = verify_packets(release, packets)
    validate_roster(read_json(roster))
    knowledge = {k["knowledge_id"]: k for k in jsonl(Path(release) / "knowledge.jsonl")}
    aa = load_annotations(a, "A", release, assignments, knowledge) if a else {}
    bb = load_annotations(b, "B", release, assignments, knowledge) if b else {}
    cc = load_annotations(adjudications, "C", release, assignments, knowledge) if adjudications else {}
    result["human_annotation_counts"] = {"A": len(aa), "B": len(bb), "C": len(cc)}
    paired = sorted(aa.keys() & bb.keys())
    disagreements = [cid for cid in paired if semantic(aa[cid]) != semantic(bb[cid])]
    require(set(cc) <= set(disagreements), "Adjudication must resolve a genuine A/B disagreement")
    for cid in cc:
        require(datetime.fromisoformat(cc[cid]["raw"]["completed_at"]) >= max(datetime.fromisoformat(aa[cid]["raw"]["completed_at"]), datetime.fromisoformat(bb[cid]["raw"]["completed_at"])), "Adjudication cannot precede the independent submissions")
    result["input_sha256"] = {r: sha(p) for r, p in (("A", a), ("B", b), ("C", adjudications), ("roster", roster)) if p}
    result["paired_case_count"] = len(paired)
    result["disagreement_case_ids"] = disagreements
    result["agreement"] = {
        "applicability": agreement([aa[c]["items"][k] for c in paired for k in sorted(aa[c]["items"])],
                                   [bb[c]["items"][k] for c in paired for k in sorted(aa[c]["items"])]),
        "priority": agreement([aa[c]["priority"] for c in paired], [bb[c]["priority"] for c in paired]),
        "top_outcome": agreement([aa[c]["top_outcome"] for c in paired], [bb[c]["top_outcome"] for c in paired]),
        "case_exact": {"n": len(paired), "exact_agreement": (len(paired) - len(disagreements)) / len(paired) if paired else None}}
    shared_pairs = [(c, p) for c in paired for p in sorted(aa[c]["pairs"].keys() & bb[c]["pairs"].keys())]
    result["agreement"]["pairwise_priority"] = agreement([aa[c]["pairs"][p] for c, p in shared_pairs], [bb[c]["pairs"][p] for c, p in shared_pairs])
    result["agreement"]["best_set_exact"] = {"n": len(paired), "exact_agreement": sum(aa[c]["best_set"] == bb[c]["best_set"] for c in paired) / len(paired) if paired else None}
    result["reviewer_distributions"] = {r: {
        "applicability": distribution([v for x in rows.values() for v in x["items"].values()], APPLICABILITY),
        "priority": distribution([x["priority"] for x in rows.values()], PRIORITY),
        "top_outcome": distribution([x["top_outcome"] for x in rows.values()], TOP)} for r, rows in (("A", aa), ("B", bb))}
    resolved = {c: cc[c] if c in cc else aa[c] for c in paired if c not in disagreements or c in cc}
    unresolved = sorted({c["case_id"] for c in cases} - resolved.keys())
    result["unresolved_case_ids"] = unresolved
    result["status"] = "PARTIALLY_ANNOTATED" if len(paired) < len(cases) else "AWAITING_ADJUDICATION" if unresolved else "ANNOTATED"
    if audit["status"] == "BLOCKED_REAL_DATA": result["status"] = "BLOCKED_REAL_DATA"
    if not unresolved and result["status"] == "ANNOTATED":
        result["applicability"] = distribution([v for x in resolved.values() for v in x["items"].values()], APPLICABILITY)
        result["priority"] = distribution([x["priority"] for x in resolved.values()], PRIORITY)
        result["top_outcome"] = distribution([x["top_outcome"] for x in resolved.values()], TOP)
        result["clearly_prioritized_case_proportion"] = sum(x["priority"] == "clear" and x["top_outcome"] != "insufficient_information" for x in resolved.values()) / len(cases)
        eligible = [x for x in resolved.values() if sum(v == "applicable" for v in x["items"].values()) >= 2]
        result["multi_applicable_denominator"] = len(eligible)
        result["clearly_prioritized_among_multi_applicable"] = sum(x["priority"] == "clear" and x["top_outcome"] != "insufficient_information" for x in eligible) / len(eligible) if eligible else None
        result["decidable_best_set_case_proportion"] = sum(x["top_outcome"] in {"unique_best", "tied_best"} for x in resolved.values()) / len(cases)
        result["information_insufficient_case_proportion"] = sum("insufficient_information" in x["items"].values() or "insufficient_information" in x["pairs"].values() or x["top_outcome"] == "insufficient_information" for x in resolved.values()) / len(cases)
        result["reasonable_tie_case_proportion"] = sum("tie" in x["pairs"].values() for x in resolved.values()) / len(cases)
        result["conclusion"] = "Human descriptive results available; evaluate P1 without assuming reliable priority supervision. No algorithmic or clinical efficacy conclusion."
        # Participant-level descriptions expose repeated windows; no iid confidence interval.
        result["participant_breakdown"] = {sid: distribution([resolved[c["case_id"]]["priority"] for c in cases if c["subject_id"] == sid], PRIORITY) for sid in sorted({c["subject_id"] for c in cases})}
    result["reason_counts"] = dict(Counter(code for c in disagreements if c in cc for code in cc[c]["raw"]["decision"]["reason_codes"]))
    result["reason_count_note"] = "Third-party adjudicated reasons only; not inferred from label differences"
    result["missing_information_counts"] = {r: dict(Counter(code for x in rows.values() for part in x["raw"]["items"] + x["raw"]["comparisons"] + [x["raw"]["decision"]] for code in part["missing_information"])) for r, rows in (("A", aa), ("B", bb), ("C", cc))}
    return result


def adjudication_queue(release, packets, roster, a, b, output):
    result = analyze(release, packets, roster, a, b)
    assignment = verify_packets(release, packets)
    reverse_a = {v["case_id"]: k for k, v in assignment["reviewers"]["A"].items()}
    reverse_b = {v["case_id"]: k for k, v in assignment["reviewers"]["B"].items()}
    templates = {r["case_ref"]: r for r in jsonl(Path(packets) / "A/annotations.template.jsonl")}
    original_a = {r["case_ref"]: r for r in jsonl(a)}
    original_b = {r["case_ref"]: r for r in jsonl(b)}
    output = Path(output)
    require(not output.exists(), "Adjudication output exists")
    output.mkdir(parents=True)
    (output / "cards/A").mkdir(parents=True)
    (output / "cards/B").mkdir(parents=True)
    queue, forms = [], []
    for cid in result["disagreement_case_ids"]:
        ref = reverse_a[cid]
        form = templates[ref]
        form["reviewer_id"] = "C"
        form["reviewed_reviewers"] = ["A", "B"]
        forms.append(form)
        card_a = "cards/A/" + ref + ".html"
        card_b = "cards/B/" + reverse_b[cid] + ".html"
        shutil.copyfile(Path(packets) / "A" / (ref + ".html"), output / card_a)
        shutil.copyfile(Path(packets) / "B" / (reverse_b[cid] + ".html"), output / card_b)
        queue.append({"case_id": cid, "A_card": card_a, "B_card": card_b,
                      "A": original_a[ref], "B": original_b[reverse_b[cid]],
                      "candidate_crosswalk": {"A": assignment["reviewers"]["A"][ref]["candidates"],
                                              "B": assignment["reviewers"]["B"][reverse_b[cid]]["candidates"]}})
        card = "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>C / " + ref + "</title><h1>C / " + ref + "</h1>"
        card += "<p>请查看两份原始卡片及独立提交。使用 A 卡片的候选引用编号填写裁决，不覆盖 A/B 原始记录。</p>"
        card += "<p><a href='" + card_a + "'>A 原始卡片</a> · <a href='" + card_b + "'>B 原始卡片</a></p><pre style='white-space:pre-wrap'>"
        card += escape(json.dumps(queue[-1], ensure_ascii=False, indent=2)) + "</pre>" + render_form(form) + "</html>"
        (output / (ref + ".html")).write_text(card, encoding="utf-8")
    write_json(output / "queue.json", queue)
    write_jsonl(output / "adjudications.template.jsonl", forms)
    (output / "P1_ANNOTATION_GUIDE.md").write_bytes((Path(release) / "P1_ANNOTATION_GUIDE.md").read_bytes())
    return {"disagreement_count": len(queue)}
