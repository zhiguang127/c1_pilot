"""Independent source-to-release acceptance check. Produces software QA, no labels.

Requires the coordinator's ignored raw files and date/identity mapping.
Run as a module with --help. Does not import or call the data importer.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from research.problem_reidentification.p1.dataset import jsonl, read_json, sha, verify_release, write_json
from research.problem_reidentification.p1.packets import verify_packets


def check(release, raw, mapping, packets):
    release, raw, packets = Path(release), Path(raw), Path(packets)
    freeze = verify_release(release)
    verify_packets(release, packets)
    cases = jsonl(release / "cases.jsonl")
    mapping = {x["case_id"]: x for x in read_json(mapping)}
    checked, sleep_checked, source_bytes = 0, 0, 0
    fields = {"resting_heart_rate_bpm": "resting_heart_rate.json",
              "fitbit_lightly_active_minutes": "lightly_active_minutes.json",
              "fitbit_moderately_active_minutes": "moderately_active_minutes.json",
              "fitbit_very_active_minutes": "very_active_minutes.json",
              "fitbit_sedentary_minutes": "sedentary_minutes.json"}
    used_days = set()
    for case in cases:
        source_map = mapping[case["case_id"]]
        directory = raw / source_map["participant"] / "fitbit"
        first = date.fromisoformat(source_map["start_date"])
        source = {}
        for metric, name in fields.items():
            path = directory / name
            entries = read_json(path) if path.exists() else []
            source[metric] = {x["dateTime"][:10]: (x["value"]["value"] if isinstance(x["value"], dict) else x["value"]) for x in entries}
        sleeps = {}
        for row in read_json(directory / "sleep.json"):
            if row.get("mainSleep", row.get("isMainSleep")) is True:
                sleeps.setdefault(row["dateOfSleep"], []).append(row)
        for row in case["days"]:
            day = first + timedelta(days=row["day"] - 1)
            source_key = (source_map["participant"], day)
            assert source_key not in used_days, "Participant windows overlap"
            used_days.add(source_key)
            assert row["weekday"] == day.isoweekday()
            assert row["phase"] == ("baseline" if row["day"] <= 28 else "current")
            for metric, values in source.items():
                value = values.get(day.isoformat())
                expected = None if value is None else float(value)
                assert row["metrics"][metric] == expected, "Numeric source mismatch"
                checked += 1
            main = sleeps.get(day.isoformat(), [])
            projections = {(x["logId"], x["minutesAsleep"], x["timeInBed"],
                            datetime.fromisoformat(x["startTime"]).strftime("%H:%M:%S"),
                            datetime.fromisoformat(x["endTime"]).strftime("%H:%M:%S"),
                            x.get("type"), x.get("infoCode"),
                            (datetime.fromisoformat(x["startTime"]).date() - day).days) for x in main}
            if len(projections) == 1:
                source_sleep = next(iter(projections))
                for index, metric in enumerate(("sleep_minutes", "time_in_bed_minutes", "sleep_start_clock", "sleep_end_clock", "sleep_log_type", "sleep_info_code", "sleep_start_day_offset"), 1):
                    assert row["metrics"][metric] == source_sleep[index], "Sleep source mismatch"
            else:
                assert row["metrics"]["sleep_minutes"] is None, "Ambiguous/absent sleep was fabricated"
            if row["metrics"]["resting_heart_rate_bpm"] == 0:
                assert "zero_rhr_source_value_not_valid_for_health_interpretation" in row["quality_flags"]
            sleep_checked += 1
    source_manifest = read_json(raw / "source_manifest.json")
    assert source_manifest["source"] == "https://osf.io/vx4bk/" and source_manifest["real_records"] is True
    assert sha(raw / "source_manifest.json") == read_json(release / "import_audit.json")["source_manifest_sha256"]
    for record in source_manifest["files"]:
        if record["status"] == "downloaded":
            data = (raw / record["path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == record["sha256"]
            source_bytes += len(data)
    cards = list(packets.glob("[AB]/CASE-*.html"))
    assert len(cards) == len(cases) * 2
    for path in cards:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\bK\d{3}\b|\bp\d{2}\b|P1-[0-9a-f]{16}|S[0-9a-f]{16}|2019-\d{2}-\d{2}|2020-\d{2}-\d{2}", text), "Blind-card identity leak"
        assert text.count("<tr>") == 43
        assert "context.symptoms: 未知（null）" in text
    templates = jsonl(packets / "A/annotations.template.jsonl") + jsonl(packets / "B/annotations.template.jsonl")
    assert all(x["status"] == "draft" and x["human_attestation"] is False and all(i["applicability"] is None for i in x["items"]) for x in templates)
    legacy = read_json("data/input_freeze.json")["file_sha256"]
    assert all(sha(path) == expected for path, expected in legacy.items())
    return {"kind": "ENGINEERING_VALIDATION_ONLY", "valid": True, "release_id": freeze["release_id"],
            "real_case_count": len(cases), "participant_count": len({c["subject_id"] for c in cases}),
            "raw_numeric_fields_checked": checked, "raw_sleep_dates_checked": sleep_checked,
            "raw_file_bytes_checked": source_bytes, "blind_cards_checked": len(cards),
            "blank_templates_checked": len(templates), "legacy_frozen_hashes_checked": len(legacy),
            "quality_flag_counts": dict(Counter(f for c in cases for r in c["days"] for f in r["quality_flags"])),
            "human_annotations_created": 0, "research_conclusion": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "raw", "mapping", "packets", "output"):
        parser.add_argument("--" + name, required=True)
    args = vars(parser.parse_args())
    output = Path(args.pop("output"))
    if output.exists(): parser.exit(2, "QA output exists; choose a new version path\n")
    result = check(**args)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(json.dumps(result, indent=2))
