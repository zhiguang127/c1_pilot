"""Reproducible design-v1 synthetic records, not patient observations."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import random

try:
    from .case_statistics import compute_derived_statistics
except ImportError:
    from case_statistics import compute_derived_statistics

SEED = 20261003
START = date(2026, 3, 2)
OFFSET = timezone(timedelta(hours=8))
GROUPS = {3: "M003_005", 5: "M003_005", 9: "M009_011", 11: "M009_011",
          16: "M016_018", 18: "M016_018", 21: "M021_023", 23: "M021_023",
          22: "M022_024", 24: "M022_024"}
STRATA = {1: "A", 2: "A", 3: "B", 4: "B", 5: "C", 6: "C",
          7: "A", 8: "B", 9: "B", 10: "A", 11: "C", 12: "C",
          13: "A", 14: "A", 15: "B", 16: "B", 17: "C", 18: "C",
          19: "A", 20: "A", 21: "B", 22: "B", 23: "C", 24: "C"}
PATTERNS = {
    1: "Fourteen nights around 5.75 hours after around 7.75 hours.",
    2: "Fourteen days around 2500 steps after around 8000 steps.",
    3: "Seven around-eight-hour nights followed by seven around-six-hour nights.",
    4: "RMSSD around 22-28 ms on window nights 5-8, then returns to prior range.",
    5: "Same sleep multiset as C003 in reverse block order, ending near baseline.",
    6: "One lower RMSSD night among thirteen near-personal-range nights.",
    7: "Sleep duration rises from around 5.5 to around 7.5 hours.",
    8: "Steps decline from around 9500 to around 6500; one insufficient-wear day.",
    9: "Current RHR around 62 bpm after baseline around 52 bpm.",
    10: "Steps rise from around 2800 to around 8000.",
    11: "Current observations identical to C009; baseline RHR around 62 bpm.",
    12: "RMSSD varies within a broad personal baseline range without sustained direction.",
    13: "Sleep start and end alternate by 2.5 hours while duration stays near eight hours.",
    14: "Fourteen days with 0-10 active minutes and low steps.",
    15: "Each week has around-6.5-hour weekdays and around-9.5-hour weekends with later timing.",
    16: "Around 480 daily low-movement minutes in 120-180-minute bouts.",
    17: "Regular 01:00-09:00 sleep opportunities near eight hours in both periods.",
    18: "Same daily activity and low-movement totals as C016 in 10-20-minute bouts.",
    19: "Around 5.5-hour sleep and 2500 daily steps throughout the window.",
    20: "Around 10 active minutes and 600 low-movement minutes each day.",
    21: "Six long 20:30 activities are followed by shorter sleep ending next morning.",
    22: "Four RHR increases and RMSSD decreases occur on the same dates, then return.",
    23: "Same activity and sleep marginals as C021, with three short nights per exposure group.",
    24: "Same RHR and RMSSD marginals as C022, with disjoint four-date changes.",
}


def _values(rng: random.Random, center: int, half_width: int, count: int = 42):
    return [center + rng.randint(-half_width, half_width) for _ in range(count)]


def _specification(case_number: int, seed: int) -> dict:
    representative = {5: 3, 11: 9, 18: 16, 23: 21, 24: 22}.get(case_number, case_number)
    rng = random.Random(seed + representative * 1009)
    spec = {
        "sleep": _values(rng, 470, 8), "wake": [420] * 42,
        "steps": _values(rng, 8000, 420), "activity": _values(rng, 55, 5),
        "low": _values(rng, 450, 12), "rhr": _values(rng, 56, 1),
        "hrv": _values(rng, 45, 2), "activity_start": [1260] * 42,
        "bout_style": ["ordinary"] * 42, "sleep_opportunity": [None] * 42,
    }
    window = slice(28, 42)
    if case_number == 1:
        spec["sleep"][:28] = _values(rng, 465, 10, 28)
        spec["sleep"][window] = _values(rng, 345, 10, 14)
    elif case_number == 2:
        spec["steps"][window] = _values(rng, 2500, 450, 14)
    elif case_number in (3, 5):
        spec["sleep"][:28] = _values(rng, 480, 8, 28)
        high, low = _values(rng, 480, 8, 7), _values(rng, 360, 8, 7)
        spec["sleep"][window] = high + low if case_number == 3 else low + high
    elif case_number == 4:
        spec["hrv"][32:36] = [22, 25, 28, 24]
    elif case_number == 6:
        spec["hrv"][34] = 23
    elif case_number == 7:
        spec["sleep"][:28] = _values(rng, 330, 8, 28)
        spec["sleep"][window] = _values(rng, 450, 8, 14)
    elif case_number == 8:
        spec["steps"][:28] = _values(rng, 9500, 300, 28)
        spec["steps"][window] = _values(rng, 6500, 250, 14)
    elif case_number in (9, 11):
        noise = _values(rng, 0, 1, 28)
        spec["rhr"][:28] = [(52 if case_number == 9 else 62) + x for x in noise]
        spec["rhr"][window] = _values(rng, 62, 1, 14)
    elif case_number == 10:
        spec["steps"][:28] = _values(rng, 2800, 240, 28)
        spec["steps"][window] = _values(rng, 8000, 400, 14)
    elif case_number == 12:
        spec["hrv"][:28] = [26, 44, 54, 32, 48, 36, 40] * 4
        spec["hrv"][window] = [30, 48, 38, 52, 34, 44, 40, 50, 32, 42, 28, 46, 36, 40]
    elif case_number == 13:
        spec["sleep"][window] = _values(rng, 480, 6, 14)
        spec["wake"][window] = [390 if i % 2 == 0 else 540 for i in range(14)]
    elif case_number == 14:
        spec["activity"][window] = [0, 5, 8, 4, 10, 2, 6, 5, 7, 0, 9, 3, 5, 4]
        spec["steps"][window] = _values(rng, 2200, 300, 14)
    elif case_number == 15:
        spec["sleep"][window] = [
            (570 if (START + timedelta(days=28+i)).weekday() >= 5 else 390) + rng.randint(-5, 5)
            for i in range(14)
        ]
        spec["wake"][window] = [660 if i % 7 >= 5 else 420 for i in range(14)]
    elif case_number in (16, 18):
        spec["low"][window] = [480] * 14
        spec["bout_style"][window] = ["long" if case_number == 16 else "broken"] * 14
    elif case_number == 17:
        spec["sleep"] = _values(rng, 476, 4)
        spec["wake"] = [540] * 42
        spec["sleep_opportunity"] = [480] * 42
    elif case_number == 19:
        spec["sleep"][window] = _values(rng, 330, 8, 14)
        spec["steps"][window] = _values(rng, 2500, 350, 14)
    elif case_number == 20:
        spec["activity"][window] = _values(rng, 10, 2, 14)
        spec["low"][window] = _values(rng, 600, 8, 14)
    elif case_number in (21, 23):
        exposure_indices = {0, 2, 4, 8, 10, 12}
        sleeps = _values(rng, 480, 6, 14)
        for i in range(14):
            spec["activity"][28+i] = 90 if i in exposure_indices else 45
            spec["activity_start"][28+i] = 1230 if i in exposure_indices else 1050
            if i - 1 in exposure_indices:
                sleeps[i] = 390 + rng.randint(-6, 6)
        if case_number == 23:
            for i in (1, 3, 5):
                sleeps[i], sleeps[i+7] = sleeps[i+7], sleeps[i]
        spec["sleep"][window] = sleeps
    elif case_number in (22, 24):
        spec["rhr"][32:36] = [65, 66, 67, 65]
        spec["hrv"][32:36] = [24, 26, 25, 23]
        if case_number == 24:
            spec["hrv"][32:36], spec["hrv"][36:40] = spec["hrv"][36:40], spec["hrv"][32:36]
    return spec


def _instant(day: date, minute: float) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=OFFSET) + timedelta(minutes=minute)


def _parts(total: int, count: int) -> list[int]:
    quotient, remainder = divmod(total, count)
    return [quotient + (i < remainder) for i in range(count)]


def _daily_row(spec: dict, index: int) -> dict:
    day = START + timedelta(days=index)
    wake = _instant(day, spec["wake"][index])
    duration = spec["sleep"][index]
    opportunity = spec["sleep_opportunity"][index] or duration + 20
    start = wake - timedelta(minutes=opportunity)
    activity_start = _instant(day, spec["activity_start"][index])
    activity_duration = spec["activity"][index]
    activity_end = activity_start + timedelta(minutes=activity_duration)
    activity = [] if activity_duration == 0 else [{
        "start_at": activity_start.isoformat(), "end_at": activity_end.isoformat(), "intensity": "unknown",
    }]
    low_duration = spec["low"][index]
    style = spec["bout_style"][index]
    if style == "long":
        lengths, gap = [150, 160, 170], 15
    elif style == "broken":
        lengths, gap = [15] * 32, 5
    else:
        lengths, gap = _parts(low_duration, 10), 5
    cursor = max(_instant(day, 600), wake + timedelta(minutes=30))
    low = []
    for length in lengths:
        endpoint = cursor + timedelta(minutes=length)
        if activity and cursor < activity_end and endpoint > activity_start:
            cursor = activity_end + timedelta(minutes=5)
            endpoint = cursor + timedelta(minutes=length)
        low.append({"start_at": cursor.isoformat(), "end_at": endpoint.isoformat()})
        cursor = endpoint + timedelta(minutes=gap)
    if style == "broken":
        # A gap alone is not observed movement; record an active minute in each break.
        activity = []
        for interval in low[:-1]:
            break_start = datetime.fromisoformat(interval["end_at"]) + timedelta(minutes=1)
            activity.append({"start_at": break_start.isoformat(),
                             "end_at": (break_start + timedelta(minutes=1)).isoformat(),
                             "intensity": "unknown"})
        remainder = activity_duration - len(activity)
        if remainder < 0:
            raise ValueError("daily active minutes cannot support the recorded moving breaks")
        if remainder:
            activity.append({"start_at": activity_start.isoformat(),
                             "end_at": (activity_start + timedelta(minutes=remainder)).isoformat(),
                             "intensity": "unknown"})
    return {
        "date": day.isoformat(), "daytime_wear_minutes": 720,
        "nighttime_coverage_minutes": opportunity,
        "metrics": {
            "sleep_duration_minutes": duration, "sleep_start_at": start.isoformat(),
            "sleep_end_at": wake.isoformat(), "steps": spec["steps"][index],
            "activity_duration_minutes": activity_duration, "low_movement_minutes": low_duration,
            "resting_heart_rate_bpm": spec["rhr"][index], "hrv_rmssd_ms": spec["hrv"][index],
        },
        "missing_reasons": {}, "activity_intervals": activity, "low_movement_intervals": low,
    }


def generate_cases(seed: int = SEED) -> list[dict]:
    cases = []
    types = ("single_variable", "personal_baseline", "temporal_pattern", "multivariable")
    for number in range(1, 25):
        spec = _specification(number, seed)
        rows = [_daily_row(spec, i) for i in range(42)]
        if number == 8:
            row = rows[36]
            row["daytime_wear_minutes"] = 360
            for metric in ("steps", "activity_duration_minutes", "low_movement_minutes"):
                row["metrics"][metric] = None
                row["missing_reasons"][metric] = "insufficient_coverage"
            row["activity_intervals"], row["low_movement_intervals"] = [], []
        stratum = STRATA[number]
        case = {
            "schema_version": "1.0", "id": f"C{number:03}", "case_type": types[(number-1)//6],
            "window_days": 14, "baseline_days": 28,
            "periods": {
                "baseline": {"start_date": rows[0]["date"], "end_date": rows[27]["date"]},
                "window": {"start_date": rows[28]["date"], "end_date": rows[41]["date"]},
            },
            "observations": {"baseline_daily": rows[:28], "window_daily": rows[28:]},
            "metadata": {
                "synthetic": True, "data_origin": f"design-v1 deterministic synthetic generation; seed={seed}",
                "age_band": "18-60", "timezone": "Asia/Shanghai",
                "device": {"name": "synthetic common wearable, not a commercial device export",
                           "metric_definition_revision": "synthetic-wearable-v1; active=moving minutes; low movement not posture; night RMSSD"},
                "quality_policy": {
                    "revision": "quality-v1", "daytime_required_wear_minutes": 720,
                    "nighttime_validity_rule": "For sleep, sleep timestamps, nocturnal RHR and RMSSD: observed nighttime coverage >=180 minutes and >=85% of recorded sleep opportunity; synthetic coverage equals opportunity. Day metrics require >=720 daytime wear minutes.",
                },
            },
            "designer_notes": {
                "intended_pattern": PATTERNS[number], "stratum": stratum,
                "expected_difficulty": {"A": "easy", "B": "representation_sensitive", "C": "negative_distractor"}[stratum],
                "rationale": "Frozen design-v1 construction stratum; not a relevance label or observed method failure.",
                "matched_group": GROUPS.get(number),
            },
        }
        case["derived_statistics"] = compute_derived_statistics(case)
        cases.append(case)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data/wearable_cases.jsonl")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    cases = generate_cases(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
    print(json.dumps({"output": str(args.output), "case_count": len(cases), "daily_rows": 1008, "seed": args.seed}))


if __name__ == "__main__":
    main()
