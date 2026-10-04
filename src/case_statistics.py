"""Uniform arithmetic statistics and the design-v1 model input whitelist."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import mean, median, pvariance

RAW_METRICS = (
    "sleep_duration_minutes", "sleep_start_at", "sleep_end_at", "steps",
    "activity_duration_minutes", "low_movement_minutes",
    "resting_heart_rate_bpm", "hrv_rmssd_ms",
)
NUMERIC_METRICS = (
    "sleep_duration_minutes", "steps", "activity_duration_minutes",
    "low_movement_minutes", "resting_heart_rate_bpm", "hrv_rmssd_ms",
    "sleep_start_minutes_from_local_noon", "sleep_end_minutes_from_local_noon",
)
PAIRS = (
    ("activity_duration_minutes", "sleep_duration_minutes", 1),
    ("resting_heart_rate_bpm", "hrv_rmssd_ms", 0),
    ("steps", "activity_duration_minutes", 0),
)


def clean_number(value):
    return None if value is None else round(float(value), 12)


def metric_value(row: dict, metric: str):
    if metric not in NUMERIC_METRICS[-2:]:
        return row["metrics"][metric]
    source = "sleep_start_at" if metric.startswith("sleep_start") else "sleep_end_at"
    timestamp = row["metrics"][source]
    if timestamp is None:
        return None
    instant = datetime.fromisoformat(timestamp)
    anchor = datetime.combine(
        date.fromisoformat(row["date"]) - timedelta(days=1),
        datetime.min.time(), tzinfo=instant.tzinfo,
    ) + timedelta(hours=12)
    return (instant - anchor).total_seconds() / 60


def descriptive_statistics(rows: list[dict], metric: str) -> dict:
    values = [(date.fromisoformat(row["date"]), metric_value(row, metric)) for row in rows]
    valid = [(day, value) for day, value in values if value is not None]
    numbers = [value for _, value in valid]
    slope = None
    if len(valid) >= 2:
        origin = min(day for day, _ in valid)
        offsets = [(day - origin).days for day, _ in valid]
        xbar, ybar = mean(offsets), mean(numbers)
        denominator = sum((x - xbar) ** 2 for x in offsets)
        if denominator:
            slope = sum((x - xbar) * (y - ybar) for x, y in zip(offsets, numbers)) / denominator
    by_date = dict(values)
    adjacent = [abs(value - by_date[day - timedelta(days=1)])
                for day, value in valid
                if by_date.get(day - timedelta(days=1)) is not None]
    return {
        "valid_count": len(valid), "missing_count": len(rows) - len(valid),
        "mean": clean_number(mean(numbers)) if numbers else None,
        "median": clean_number(median(numbers)) if numbers else None,
        "variance": clean_number(pvariance(numbers)) if numbers else None,
        "min": clean_number(min(numbers)) if numbers else None,
        "max": clean_number(max(numbers)) if numbers else None,
        "slope_per_day": clean_number(slope),
        "adjacent_mean_abs_delta": clean_number(mean(adjacent)) if adjacent else None,
    }


def paired_statistics(rows: list[dict], x_metric: str, y_metric: str, lag_days: int) -> dict:
    by_date = {date.fromisoformat(row["date"]): row for row in rows}
    pairs = []
    for day, row in sorted(by_date.items()):
        other = by_date.get(day + timedelta(days=lag_days))
        x = metric_value(row, x_metric)
        y = metric_value(other, y_metric) if other is not None else None
        if x is not None and y is not None:
            pairs.append((x, y))
    correlation = None
    if len(pairs) >= 3:
        xs, ys = zip(*pairs)
        xbar, ybar = mean(xs), mean(ys)
        sx = sum((x - xbar) ** 2 for x in xs)
        sy = sum((y - ybar) ** 2 for y in ys)
        if sx and sy:
            correlation = max(-1.0, min(1.0, sum(
                (x - xbar) * (y - ybar) for x, y in pairs
            ) / sqrt(sx * sy)))
    return {"x_metric": x_metric, "y_metric": y_metric, "lag_days": lag_days,
            "paired_count": len(pairs), "pearson_r": clean_number(correlation)}


def compute_derived_statistics(case: dict) -> dict:
    periods = {name: case["observations"][name + "_daily"] for name in ("baseline", "window")}
    result = {"calculation_revision": "stats-v1", "metric_statistics": {},
              "grouped_statistics": [], "paired_statistics": []}
    for metric in NUMERIC_METRICS:
        statistics = {name: descriptive_statistics(rows, metric) for name, rows in periods.items()}
        baseline, window = statistics["baseline"]["mean"], statistics["window"]["mean"]
        difference = window - baseline if baseline is not None and window is not None else None
        statistics["comparison"] = {
            "mean_difference": clean_number(difference),
            "relative_mean_difference": clean_number(difference / baseline)
            if difference is not None and baseline != 0 else None,
        }
        result["metric_statistics"][metric] = statistics
        for period, rows in periods.items():
            for group in ("weekday", "weekend"):
                subset = [row for row in rows if
                          (date.fromisoformat(row["date"]).weekday() < 5) == (group == "weekday")]
                result["grouped_statistics"].append({
                    "metric": metric, "period": period, "group": group,
                    "statistics": descriptive_statistics(subset, metric),
                })
    for period, rows in periods.items():
        for x_metric, y_metric, lag in PAIRS:
            result["paired_statistics"].append({
                "period": period, **paired_statistics(rows, x_metric, y_metric, lag),
            })
    return result


def model_input(case: dict) -> dict:
    result = {key: deepcopy(case[key]) for key in
              ("window_days", "baseline_days", "periods", "observations", "derived_statistics")}
    result["metadata"] = {key: deepcopy(case["metadata"][key]) for key in
                          ("age_band", "timezone", "device", "quality_policy")}
    return result
