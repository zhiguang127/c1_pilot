"""Validate schema, dated intervals, quality, recomputed statistics and frozen pairs."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path

try:
    from .case_statistics import NUMERIC_METRICS, RAW_METRICS, compute_derived_statistics, metric_value
except ImportError:
    from case_statistics import NUMERIC_METRICS, RAW_METRICS, compute_derived_statistics, metric_value

DAY_METRICS = ("steps", "activity_duration_minutes", "low_movement_minutes")
NIGHT_METRICS = ("sleep_duration_minutes", "sleep_start_at", "sleep_end_at",
                 "resting_heart_rate_bpm", "hrv_rmssd_ms")
MATCHED_PAIRS = (("C003", "C005"), ("C009", "C011"), ("C016", "C018"),
                 ("C021", "C023"), ("C022", "C024"))


def _walk_finite(value, path: str = "") -> list[str]:
    errors = []
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{path}: non-finite JSON number")
    elif isinstance(value, dict):
        for key, child in value.items():
            errors.extend(_walk_finite(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_finite(child, f"{path}[{index}]"))
    return errors


def _compare(actual, expected, path: str) -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            return [f"{path}: incorrect object fields"]
        return [error for key in expected for error in _compare(actual[key], expected[key], path + "." + key)]
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: incorrect array length"]
        return [error for i, value in enumerate(expected) for error in _compare(actual[i], value, f"{path}[{i}]")]
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool) or not math.isclose(
                actual, expected, abs_tol=1e-7, rel_tol=1e-8):
            return [f"{path}: {actual!r} does not equal recomputed {expected!r}"]
    elif actual != expected:
        return [f"{path}: {actual!r} does not equal {expected!r}"]
    return []


def _timestamp(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() != timedelta(hours=8):
        raise ValueError("pilot timestamps require explicit UTC+08:00 offset")
    return instant


def _duration(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60


def validate_case(case: dict, schema: dict | None = None) -> list[str]:
    errors = _walk_finite(case)
    if schema is not None:
        try:
            import jsonschema
        except ImportError:
            return errors + ["jsonschema dependency unavailable; schema not validated"]
        validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())
        schema_errors = sorted(validator.iter_errors(case), key=lambda error: str(list(error.absolute_path)))
        if schema_errors:
            return errors + [f"schema {list(error.absolute_path)}: {error.message}" for error in schema_errors]
    try:
        if case["baseline_days"] != 28 or case["window_days"] != 14:
            errors.append("design-v1 requires 28 baseline and 14 window days")
        baseline_end = date.fromisoformat(case["periods"]["baseline"]["end_date"])
        window_start = date.fromisoformat(case["periods"]["window"]["start_date"])
        if window_start != baseline_end + timedelta(days=1):
            errors.append("baseline and window are not contiguous and nonoverlapping")
        all_rows = []
        for period in ("baseline", "window"):
            rows = case["observations"][period + "_daily"]
            start = date.fromisoformat(case["periods"][period]["start_date"])
            end = date.fromisoformat(case["periods"][period]["end_date"])
            expected_dates = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
            if [row["date"] for row in rows] != expected_dates or len(rows) != case[period + "_days"]:
                errors.append(f"{period}: daily rows do not match the complete calendar period")
            all_rows.extend(rows)
        sleep_intervals = []
        daytime_intervals = []
        for row in all_rows:
            day = date.fromisoformat(row["date"])
            metrics, reasons = row["metrics"], row["missing_reasons"]
            if set(metrics) != set(RAW_METRICS):
                errors.append(f"{day}: all cases require the same eight raw metric fields")
                continue
            null_metrics = {key for key, value in metrics.items() if value is None}
            if set(reasons) != null_metrics:
                errors.append(f"{day}: null metric and missing reason sets differ")
            wear = row["daytime_wear_minutes"]
            if wear is None or wear < case["metadata"]["quality_policy"]["daytime_required_wear_minutes"]:
                if any(metrics[key] is not None for key in DAY_METRICS):
                    errors.append(f"{day}: valid daytime metrics below the shared wear requirement")
            start_value, end_value = metrics["sleep_start_at"], metrics["sleep_end_at"]
            coverage = row.get("nighttime_coverage_minutes")
            if start_value is not None and end_value is not None:
                start, end = _timestamp(start_value), _timestamp(end_value)
                opportunity = _duration(start, end)
                if not 0 < opportunity <= 1440 or end.date() != day:
                    errors.append(f"{day}: invalid sleep duration or wake-date assignment")
                if end.date() - start.date() not in (timedelta(0), timedelta(days=1)):
                    errors.append(f"{day}: sleep spans unsupported dates")
                if metrics["sleep_duration_minutes"] is not None and metrics["sleep_duration_minutes"] > opportunity:
                    errors.append(f"{day}: total sleep estimate exceeds sleep opportunity")
                if coverage is not None and coverage > opportunity:
                    errors.append(f"{day}: night coverage exceeds the recorded opportunity")
                if coverage is None or coverage < 180 or coverage < .85 * opportunity:
                    if any(metrics[key] is not None for key in NIGHT_METRICS):
                        errors.append(f"{day}: valid nocturnal metrics without required night coverage")
                sleep_intervals.append((start, end))
                if not 0 <= metric_value(row, "sleep_start_minutes_from_local_noon") < 1440:
                    errors.append(f"{day}: sleep starts outside the documented local-noon anchor range")
                if not 0 < metric_value(row, "sleep_end_minutes_from_local_noon") <= 1440:
                    errors.append(f"{day}: sleep ends outside the documented local-noon anchor range")
            elif any(metrics[key] is not None for key in NIGHT_METRICS):
                errors.append(f"{day}: nocturnal validity cannot be established without sleep bounds")
            row_intervals = []
            for interval_field, total_metric in (("activity_intervals", "activity_duration_minutes"),
                                                  ("low_movement_intervals", "low_movement_minutes")):
                previous_end = None
                intervals = []
                for interval in row.get(interval_field, []):
                    start, end = _timestamp(interval["start_at"]), _timestamp(interval["end_at"])
                    if start >= end or start.date() != day or end > datetime.combine(
                            day + timedelta(days=1), datetime.min.time(), tzinfo=start.tzinfo):
                        errors.append(f"{day}: {interval_field} invalid bounds or unsplit midnight crossing")
                    if previous_end is not None and start < previous_end:
                        errors.append(f"{day}: {interval_field} unordered or overlapping")
                    if interval_field == "activity_intervals" and interval["intensity"] != "unknown":
                        errors.append(f"{day}: synthetic pilot must not infer activity intensity")
                    intervals.append((start, end))
                    previous_end = end
                total = metrics[total_metric]
                if total is None and intervals:
                    errors.append(f"{day}: intervals supplied for unavailable {total_metric}")
                if total is not None and not math.isclose(sum(_duration(*interval) for interval in intervals), total, abs_tol=1e-7):
                    errors.append(f"{day}: intervals do not add to {total_metric}")
                row_intervals.extend(intervals)
            row_intervals.sort()
            if any(end > next_start for (_, end), (next_start, _) in zip(row_intervals, row_intervals[1:])):
                errors.append(f"{day}: active and low-movement intervals overlap")
            observed_minutes = sum(_duration(*interval) for interval in row_intervals)
            if wear is not None and observed_minutes > wear:
                errors.append(f"{day}: active plus low-movement minutes exceed daytime wear")
            daytime_intervals.extend(row_intervals)
        sleep_intervals.sort()
        if any(end > next_start for (_, end), (next_start, _) in zip(sleep_intervals, sleep_intervals[1:])):
            errors.append("recorded sleep opportunities overlap")
        for row in all_rows:
            day = date.fromisoformat(row["date"])
            midnight = datetime.combine(day, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
            tomorrow = midnight + timedelta(days=1)
            # Coverage must be budgeted on natural days, not credited entirely to the wake day.
            nighttime_intersection = sum(max(0.0, _duration(max(start, midnight), min(end, tomorrow)))
                                         for start, end in sleep_intervals)
            wear = row["daytime_wear_minutes"]
            if wear is not None and wear + nighttime_intersection > 1440 + 1e-7:
                errors.append(f"{day}: actual natural-day daytime/nighttime coverage exceeds 1440 minutes")
        if any(max(day_start, night_start) < min(day_end, night_end)
               for day_start, day_end in daytime_intervals for night_start, night_end in sleep_intervals):
            errors.append("active/low-movement intervals overlap a recorded sleep opportunity")
        if set(case["derived_statistics"]["metric_statistics"]) != set(NUMERIC_METRICS):
            errors.append("numeric statistics must cover all eight metrics uniformly")
        errors.extend(_compare(case["derived_statistics"], compute_derived_statistics(case), "derived_statistics"))
    except (KeyError, TypeError, ValueError, StopIteration) as error:
        errors.append(f"semantic validation failed: {type(error).__name__}: {error}")
    return errors


def _without(rows: list[dict], metric_keys: tuple = (), row_keys: tuple = ()):
    result = deepcopy(rows)
    for row in result:
        for key in metric_keys:
            row["metrics"].pop(key, None)
        for key in row_keys:
            row.pop(key, None)
    return result


def _marginal(rows: list[dict], metric: str):
    return sorted(metric_value(row, metric) for row in rows)


def validate_matched_pairs(cases: list[dict]) -> list[dict]:
    lookup = {case["id"]: case for case in cases}
    results = []
    for a_id, b_id in MATCHED_PAIRS:
        errors = []
        a, b = lookup.get(a_id), lookup.get(b_id)
        if a is None or b is None:
            results.append({"pair": [a_id, b_id], "valid": False, "errors": ["matched case absent"]})
            continue
        if a["metadata"] != b["metadata"] or a["periods"] != b["periods"]:
            errors.append("matched metadata, device, quality policy or dates differ")
        if a["designer_notes"]["matched_group"] != b["designer_notes"]["matched_group"]:
            errors.append("matched group identifiers differ")
        ab, bb = a["observations"]["baseline_daily"], b["observations"]["baseline_daily"]
        aw, bw = a["observations"]["window_daily"], b["observations"]["window_daily"]
        if a_id == "C009":
            if aw != bw or _without(ab, ("resting_heart_rate_bpm",)) != _without(bb, ("resting_heart_rate_bpm",)):
                errors.append("only baseline RHR may differ in C009/C011")
            if not all(y["metrics"]["resting_heart_rate_bpm"] - x["metrics"]["resting_heart_rate_bpm"] == 10 for x, y in zip(ab, bb)):
                errors.append("baseline RHR difference must be ten bpm on every matched day")
        else:
            if ab != bb:
                errors.append("matched baselines differ")
            if a_id == "C003":
                excluded = ("sleep_duration_minutes", "sleep_start_at")
                if _without(aw, excluded, ("nighttime_coverage_minutes",)) != _without(bw, excluded, ("nighttime_coverage_minutes",)):
                    errors.append("C003/C005 non-sleep backgrounds differ")
                if _marginal(aw, "sleep_duration_minutes") != _marginal(bw, "sleep_duration_minutes"):
                    errors.append("C003/C005 sleep value multisets differ")
                if not all(metric_value(x, "sleep_duration_minutes") > 420 for x in aw[:7]) or not all(metric_value(x, "sleep_duration_minutes") < 420 for x in aw[7:]):
                    errors.append("C003 does not have the frozen high-then-low block direction")
                if not all(metric_value(x, "sleep_duration_minutes") < 420 for x in bw[:7]) or not all(metric_value(x, "sleep_duration_minutes") > 420 for x in bw[7:]):
                    errors.append("C005 does not have the frozen low-then-high block direction")
            elif a_id == "C016":
                interval_fields = ("low_movement_intervals", "activity_intervals")
                if _without(aw, row_keys=interval_fields) != _without(bw, row_keys=interval_fields):
                    errors.append("C016/C018 only low-movement segmentation and corresponding movement timing may differ; daily totals are matched")
                alengths = [_duration(_timestamp(i["start_at"]), _timestamp(i["end_at"])) for r in aw for i in r["low_movement_intervals"]]
                blengths = [_duration(_timestamp(i["start_at"]), _timestamp(i["end_at"])) for r in bw for i in r["low_movement_intervals"]]
                if not alengths or not all(120 <= length <= 180 for length in alengths):
                    errors.append("C016 lacks 120-180-minute bouts")
                if not blengths or not all(10 <= length <= 20 for length in blengths):
                    errors.append("C018 lacks 10-20-minute interrupted bouts")
                for row in bw:
                    intervals = row["low_movement_intervals"]
                    for previous, following in zip(intervals, intervals[1:]):
                        gap_start, gap_end = _timestamp(previous["end_at"]), _timestamp(following["start_at"])
                        if not any(gap_start <= _timestamp(interval["start_at"]) < _timestamp(interval["end_at"]) <= gap_end
                                   for interval in row["activity_intervals"]):
                            errors.append(f"C018 {row['date']}: a low-movement break lacks recorded movement")
            elif a_id == "C021":
                excluded = ("sleep_duration_minutes", "sleep_start_at", "sleep_end_at")
                if _without(aw, excluded, ("nighttime_coverage_minutes",)) != _without(bw, excluded, ("nighttime_coverage_minutes",)):
                    errors.append("C021/C023 non-sleep backgrounds or activity intervals differ")
                for metric in ("sleep_duration_minutes", "sleep_start_minutes_from_local_noon", "sleep_end_minutes_from_local_noon", "activity_duration_minutes"):
                    if _marginal(aw, metric) != _marginal(bw, metric):
                        errors.append(f"C021/C023 marginal mismatch: {metric}")
                    for weekday in range(7):
                        ar = [r for r in aw if date.fromisoformat(r["date"]).weekday() == weekday]
                        br = [r for r in bw if date.fromisoformat(r["date"]).weekday() == weekday]
                        if _marginal(ar, metric) != _marginal(br, metric):
                            errors.append(f"C021/C023 permutation changed weekday {weekday} marginal: {metric}")
                counts = []
                for rows in (aw, bw):
                    by_date = {date.fromisoformat(r["date"]): r for r in rows}
                    following_short = 0
                    exposures = 0
                    for day, row in by_date.items():
                        late = any(_timestamp(i["start_at"]).hour >= 20 and _duration(
                            _timestamp(i["start_at"]), _timestamp(i["end_at"])) >= 80 for i in row["activity_intervals"])
                        if late:
                            exposures += 1
                            next_row = by_date.get(day + timedelta(days=1))
                            if next_row is not None and next_row["metrics"]["sleep_duration_minutes"] < 420:
                                following_short += 1
                    counts.append((exposures, following_short))
                if counts != [(6, 6), (6, 3)]:
                    errors.append(f"C021/C023 next-wake-date activity/sleep constraint failed: {counts}")
            elif a_id == "C022":
                if _without(aw, ("hrv_rmssd_ms",)) != _without(bw, ("hrv_rmssd_ms",)):
                    errors.append("C022/C024 only HRV timing may differ")
                for metric in ("resting_heart_rate_bpm", "hrv_rmssd_ms"):
                    if _marginal(aw, metric) != _marginal(bw, metric):
                        errors.append(f"C022/C024 marginal mismatch: {metric}")
                rhr_dates = {r["date"] for r in aw if r["metrics"]["resting_heart_rate_bpm"] > 60}
                a_hrv = {r["date"] for r in aw if r["metrics"]["hrv_rmssd_ms"] < 30}
                b_hrv = {r["date"] for r in bw if r["metrics"]["hrv_rmssd_ms"] < 30}
                if len(rhr_dates) != 4 or rhr_dates != a_hrv or len(b_hrv) != 4 or rhr_dates & b_hrv:
                    errors.append("C022/C024 four-date simultaneous versus disjoint constraint failed")
        results.append({"pair": [a_id, b_id], "valid": not errors, "errors": errors})
    return results


def validate_dataset(cases: list[dict], schema: dict | None = None) -> dict:
    global_errors = []
    ids = [case.get("id") for case in cases]
    if len(cases) != 24 or set(ids) != {f"C{i:03}" for i in range(1, 25)} or len(ids) != len(set(ids)):
        global_errors.append("dataset must contain exactly the 24 unique design-v1 identifiers")
    strata = Counter(case.get("designer_notes", {}).get("stratum") for case in cases)
    types = Counter(case.get("case_type") for case in cases)
    if strata != Counter({"A": 8, "B": 8, "C": 8}) or sorted(types.values()) != [6, 6, 6, 6]:
        global_errors.append("design-v1 stratum or type balance changed")
    for case_type in types:
        counts = Counter(case.get("designer_notes", {}).get("stratum") for case in cases if case.get("case_type") == case_type)
        if counts != Counter({"A": 2, "B": 2, "C": 2}):
            global_errors.append(f"{case_type}: expected two cases in each A/B/C stratum")
    per_case = [{"case_id": case.get("id"), "errors": validate_case(case, schema)} for case in cases]
    matched = validate_matched_pairs(cases)
    valid = not global_errors and not any(row["errors"] for row in per_case) and all(row["valid"] for row in matched)
    return {
        "valid": valid, "schema_validation": "checked" if schema is not None else "not_requested",
        "case_count": len(cases), "daily_row_count": sum(len(rows) for case in cases for rows in case["observations"].values()),
        "global_errors": global_errors, "cases": per_case, "matched_pairs": matched,
        "checks": ["JSON schema and date/time formats", "finite values", "contiguous 28/14-day calendars",
                   "uniform raw metric keys and null reasons", "metric-specific coverage policy",
                   "sleep wake-date assignment and duration bounds", "sorted disjoint actual intervals and sums",
                   "natural-day nighttime/daytime coverage budget", "sleep/daytime interval separation",
                   "all eight arithmetic metric statistics recomputed", "weekday/weekend arithmetic statistics",
                   "calendar-aligned lagged Pearson arithmetic", "five frozen matched-pair constraints"],
    }


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=base / "data/wearable_cases.jsonl")
    parser.add_argument("--schema", type=Path, default=base / "schemas/wearable_case.schema.json")
    parser.add_argument("--report", type=Path, default=base / "outputs/metrics/cases_validation.json")
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = validate_dataset(cases, json.loads(args.schema.read_text(encoding="utf-8")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, allow_nan=False))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
