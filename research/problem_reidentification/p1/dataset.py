"""Source-preserving import, pseudonymization, and immutable case releases."""
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def opaque(key, text):
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()[:16]


def number(value, maximum=None):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a measurement")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("Invalid measurement value")
    return value


def daily_metric(path, resting=False):
    result = {}
    if not path.exists():
        return result
    for row in read_json(path):
        day = date.fromisoformat(row["dateTime"][:10])
        if day in result:
            raise ValueError("Duplicate daily observation: " + path.name)
        value = row["value"]
        if resting:
            value = value["value"] if isinstance(value, dict) else value
        result[day] = None if value is None else number(value, 300 if resting else 1440)
    return result


def sleep_metric(path):
    """Only explicit main sleep; never turn timeInBed or nap sums into sleep."""
    grouped = {}
    if not path.exists():
        return {}
    for row in read_json(path):
        if row.get("mainSleep", row.get("isMainSleep")) is not True:
            continue
        start, end = datetime.fromisoformat(row["startTime"]), datetime.fromisoformat(row["endTime"])
        day = date.fromisoformat(row.get("dateOfSleep", end.date().isoformat()))
        asleep = row.get("minutesAsleep")
        projection = {"sleep_minutes": None if asleep is None else number(asleep, 1440),
                       "time_in_bed_minutes": None if row.get("timeInBed") is None else number(row["timeInBed"], 1440),
                       "sleep_start_clock": start.strftime("%H:%M:%S"),
                       "sleep_end_clock": end.strftime("%H:%M:%S"),
                       "sleep_start_day_offset": (start.date() - day).days,
                       "sleep_log_type": row.get("type"), "sleep_info_code": row.get("infoCode")}
        if projection["sleep_log_type"] not in {None, "classic", "stages"}:
            raise ValueError("Unknown source sleep log type")
        if projection["sleep_info_code"] is not None:
            projection["sleep_info_code"] = number(projection["sleep_info_code"], 100)
        grouped.setdefault(day, []).append((row.get("logId"), projection))
    result = {}
    for day, observations in grouped.items():
        distinct = {digest([log_id, projection]): projection for log_id, projection in observations}
        if len(distinct) == 1:
            result[day] = dict(next(iter(distinct.values())))
            result[day]["sleep_quality_flags"] = ["repeated_identical_selected_sleep_fields"] if len(observations) > 1 else []
        else:
            result[day] = {"sleep_quality_flags": ["ambiguous_main_sleep_all_sleep_fields_withheld"]}
    return result


def import_participant(path):
    metrics = {
        "resting_heart_rate_bpm": daily_metric(path / "resting_heart_rate.json", resting=True),
        "fitbit_lightly_active_minutes": daily_metric(path / "lightly_active_minutes.json"),
        "fitbit_moderately_active_minutes": daily_metric(path / "moderately_active_minutes.json"),
        "fitbit_very_active_minutes": daily_metric(path / "very_active_minutes.json"),
        "fitbit_sedentary_minutes": daily_metric(path / "sedentary_minutes.json"),
    }
    sleep = sleep_metric(path / "sleep.json")
    days = set(sleep).union(*(set(v) for v in metrics.values()))
    result = {}
    for day in sorted(days):
        result[day] = {name: values.get(day) for name, values in metrics.items()}
        result[day].update(sleep.get(day, {}))
    return result


METRICS = ["sleep_minutes", "time_in_bed_minutes", "sleep_start_clock", "sleep_end_clock",
           "sleep_start_day_offset", "sleep_log_type", "sleep_info_code", "resting_heart_rate_bpm", "fitbit_lightly_active_minutes",
           "fitbit_moderately_active_minutes", "fitbit_very_active_minutes", "fitbit_sedentary_minutes"]
OBSERVATION_METRICS = [x for x in METRICS if x not in {"sleep_start_day_offset", "sleep_log_type", "sleep_info_code"}]


def construct_cases(records, plan, key):
    cases, exclusions, mapping = [], [], []
    start = date.fromisoformat(plan["study_start"])
    length = plan["baseline_days"] + plan["current_days"]
    for participant, daily in sorted(records.items()):
        subject_id = "S" + opaque(key, participant)
        for block in range(plan["blocks_per_participant"]):
            first = start + timedelta(days=block * length)
            case_id = "P1-" + opaque(key, participant + ":" + str(block))
            rows = []
            for index in range(length):
                day = first + timedelta(days=index)
                values = {metric: daily.get(day, {}).get(metric) for metric in METRICS}
                flags = list(daily.get(day, {}).get("sleep_quality_flags", []))
                if values["resting_heart_rate_bpm"] == 0:
                    flags.append("zero_rhr_source_value_not_valid_for_health_interpretation")
                if values["sleep_info_code"] not in (None, 0):
                    flags.append("nonzero_sleep_info_code_raw_device_quality_unknown")
                rows.append({"day": index + 1, "weekday": day.isoweekday(),
                             "phase": "baseline" if index < plan["baseline_days"] else "current",
                             "metrics": values,
                             "quality_flags": flags,
                             "missing_metrics": [k for k, v in values.items() if v is None]})
            observed = {phase: sum(any(r["metrics"][m] is not None for m in OBSERVATION_METRICS)
                                   for r in rows if r["phase"] == phase)
                        for phase in ("baseline", "current")}
            included = min(observed.values()) >= plan["minimum_observed_days_per_phase"]
            mapping.append({"case_id": case_id, "participant": participant,
                            "start_date": first.isoformat(), "block": block, "included": included})
            if not included:
                exclusions.append({"case_id": case_id, "subject_id": subject_id,
                                   "reason": "insufficient_observed_days", "observed_days": observed})
                continue
            cases.append({"case_id": case_id, "subject_id": subject_id, "data_origin": "real_PMData",
                          "block": block, "baseline_days": plan["baseline_days"],
                          "current_days": plan["current_days"], "observed_days": observed,
                          "context": {"device": "Fitbit Versa 2 (dataset documentation)",
                                      "population": "Adult cohort, age range 25-60 in PMData publication section 3 (DOI: 10.1145/3339825.3394926); individual age not imported",
                                      "age": None, "symptoms": None, "diagnoses": None,
                                      "goals": None, "preferences": None, "medications": None,
                                      "work_schedule": None, "timezone": None,
                                      "wear_time": None, "device_change_history": None},
                          "quality_notes": ["Missing is unknown, not zero or absence.",
                                            "Device active-minute classes are not independently verified intensity.",
                                            "Sedentary minutes do not establish posture or continuous sitting.",
                                            "Local sleep clocks have unknown timezone/DST; no offset invented.",
                                            "Only explicit main sleep is imported; naps are excluded.",
                                            "A source RHR of zero is preserved but flagged as unusable for physiological interpretation; it does not mean a zero heartbeat.",
                                            "sleep_log_type and sleep_info_code are preserved source fields; classic logs do not establish availability of Light/Deep/REM stages.",
                                            "Repeated logs with identical logId and imported fields are collapsed; conflicting main sleep records are withheld and flagged.",
                                            "Participant metadata and self-reports have not been imported."],
                          "days": rows, "candidate_ids": plan["candidate_panel"]})
    return cases, exclusions, mapping


def candidate_knowledge(ids, repo=REPO):
    corpus = {x["id"]: x for x in jsonl(repo / "data/knowledge_items.jsonl")}
    seeds = read_json(repo / "data/corpus_seed.json")
    # Source seed order defines K001..K096 in the existing frozen corpus.
    if isinstance(seeds, dict):
        seeds = seeds["items"]
    result = []
    for kid in ids:
        item = corpus[kid]
        seed = seeds[int(kid[1:]) - 1]
        source_key = seed["source_key"]
        snapshot = repo / "data/source_snapshots" / (source_key + ".txt")
        text = snapshot.read_text(encoding="utf-8")
        anchors = [seed["support_anchor"]] + seed.get("additional_support_anchors", [])
        if any(anchor.casefold() not in text.casefold() for anchor in anchors):
            raise ValueError("Missing supporting source anchor for " + kid)
        result.append({"knowledge_id": kid, "title": item["title"], "content": item["content"],
                       "source": item["source"], "source_url": item["source_url"],
                       "source_locator": item["source_locator"],
                       "source_accessed_on": item["source_accessed_on"],
                       "applicability": item["applicability"], "support_anchors": anchors,
                       "source_snapshot_sha256": sha(snapshot),
                       "source_review": "Existing fetched source and provisional LLM review; human source review pending"})
    return result


def prepare(raw_dir, output, key_file=None):
    raw_dir, output = Path(raw_dir), Path(output)
    if output.exists():
        raise ValueError("Release exists; use a new version directory")
    manifest = read_json(raw_dir / "source_manifest.json")
    if manifest.get("real_records") is not True or manifest.get("source") != "https://osf.io/vx4bk/":
        raise ValueError("Official real-data provenance required")
    plan = read_json(ROOT / "sampling_plan.json")
    if manifest["sampling_plan_sha256"] != sha(ROOT / "sampling_plan.json"):
        raise ValueError("Download and sampling plan revisions differ")
    participants = manifest["participants"]
    if len(participants) != len(set(participants)) or any(not re.fullmatch(r"p\d{2}", p) for p in participants):
        raise ValueError("Invalid source participant inventory")
    for record in manifest["files"]:
        if record["status"] not in {"downloaded", "absent_at_source"}:
            raise ValueError("Unknown source-file status")
        path = (raw_dir / record["path"]).resolve()
        if not path.is_relative_to(raw_dir.resolve()):
            raise ValueError("Unsafe source path")
        if record["status"] == "downloaded":
            if not record["url"].startswith("https://osf.io/download/") or sha(path) != record["sha256"]:
                raise ValueError("Raw file changed or unsafe source path")
        elif path.exists():
            raise ValueError("File declared absent exists locally")
    expected = {(p + "/fitbit/" + name) for p in manifest["participants"] for name in plan["metrics"]}
    if len(manifest["files"]) != len(expected) or {r["path"] for r in manifest["files"]} != expected:
        raise ValueError("Incomplete source inventory")
    key_file = Path(key_file) if key_file else ROOT / "local/pseudonym.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_bytes(secrets.token_bytes(32))
    key = key_file.read_bytes()
    if len(key) < 32:
        raise ValueError("Pseudonym key requires at least 32 bytes")
    records = {p: import_participant(raw_dir / p / "fitbit") for p in manifest["participants"]}
    cases, exclusions, mapping = construct_cases(records, plan, key)
    cases.sort(key=lambda case: case["case_id"])  # Do not expose source participant order.
    knowledge = candidate_knowledge(plan["candidate_panel"])
    if not cases:
        raise ValueError("BLOCKED_REAL_DATA: no eligible real longitudinal cases")
    private_mapping = key_file.parent / ("mapping-" + output.name + ".json")
    if private_mapping.exists():
        raise ValueError("Mapping already exists; use a unique release name")
    output.mkdir(parents=True)
    write_jsonl(output / "cases.jsonl", cases)
    write_jsonl(output / "knowledge.jsonl", knowledge)
    write_json(output / "sampling_plan.json", plan)
    for document in ("P1_PROTOCOL.md", "P1_ANNOTATION_GUIDE.md"):
        (output / document).write_bytes((ROOT / document).read_bytes())
    write_json(output / "import_audit.json", {
        "status": "PREPARED_NOT_ANNOTATED" if plan["target_min"] <= len(cases) <= plan["target_max"] else "BLOCKED_REAL_DATA",
        "real_case_count": len(cases), "participant_count": len({x["subject_id"] for x in cases}),
        "attempted_case_count": len(mapping), "excluded_cases": exclusions,
        "source_manifest_sha256": sha(raw_dir / "source_manifest.json"),
        "raw_file_count": sum(x["status"] == "downloaded" for x in manifest["files"]),
        "license": manifest["license_text"], "downloaded_at": manifest["downloaded_at"],
        "missing_counts": dict(Counter(m for c in cases for row in c["days"] for m in row["missing_metrics"])),
        "quality_flag_counts": dict(Counter(flag for c in cases for row in c["days"] for flag in row["quality_flags"])),
        "source_file_hashes": sorted(x["sha256"] for x in manifest["files"] if x["status"] == "downloaded"),
        "human_annotations": 0})
    write_json(private_mapping, mapping)
    hashes = {p.name: sha(p) for p in sorted(output.iterdir())}
    write_json(output / "freeze.json", {"revision": "p1-v1", "files": hashes,
                                        "release_id": digest(hashes),
                                        "code_sha256": {p.name: sha(p) for p in sorted(ROOT.glob("*.py"))}})
    return read_json(output / "import_audit.json")


def verify_release(release):
    release = Path(release)
    freeze = read_json(release / "freeze.json")
    if freeze["release_id"] != digest(freeze["files"]):
        raise ValueError("Freeze manifest is inconsistent")
    if {p.name for p in release.iterdir()} != set(freeze["files"]) | {"freeze.json"}:
        raise ValueError("Release inventory differs from freeze")
    for name, expected in freeze["files"].items():
        path = (release / name).resolve()
        if not path.is_relative_to(release.resolve()) or sha(path) != expected:
            raise ValueError("Frozen artifact changed: " + name)
    for name, expected in freeze.get("code_sha256", {}).items():
        if Path(name).name != name or sha(ROOT / name) != expected:
            raise ValueError("Frozen pipeline code changed: " + name)
    return freeze
