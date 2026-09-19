#!/usr/bin/env python3
"""Pure analysis helpers for the Phase 7.6 stability experiments."""
from __future__ import annotations

ALARM = ("suspect", "act")


def classify(entry: dict) -> str:
    if entry["published"] == "unknown" and entry.get("cause") == "suppressed_intervention":
        return "suppressed"
    if entry["fsm"] in ALARM:
        if entry["envelope"] or entry["act_rule"]:
            return "env_alarm"
        if entry["conservation"]:
            return "residual_only"
        return "held"
    return entry["published"]


def window_counts(timeline: list, t0_wall: float, t1_wall: float) -> dict:
    rows = sorted(
        (entry for entry in timeline if entry["t_source"] is not None),
        key=lambda entry: entry["t_source"],
    )
    counts = {"ticks": 0, "act_entries": 0, "alarm_entries": 0}
    previous = None
    for entry in rows:
        inside = t0_wall <= entry["t_source"] < t1_wall
        if inside:
            counts["ticks"] += 1
            category = classify(entry)
            counts[category] = counts.get(category, 0) + 1
            if previous is not None:
                if entry["published"] == "act" and previous["published"] != "act":
                    counts["act_entries"] += 1
                if entry["published"] in ALARM and previous["published"] not in ALARM:
                    counts["alarm_entries"] += 1
        previous = entry
    return counts


def summarize_ms(values):
    from measurements.stats import summarize

    seconds = [value / 1000.0 for value in values if value is not None]
    return summarize(seconds) if seconds else None


def tick_health(timeline: list, period_s: float = 1.0) -> dict:
    ticks = sorted(entry["t_in"] for entry in timeline)
    intervals = [(right - left) * 1000.0 for left, right in zip(ticks, ticks[1:])]
    return {
        "n": len(ticks),
        "dt": summarize_ms(intervals),
        "overruns_gt_1050ms": sum(dt > period_s * 1050 for dt in intervals),
        "gaps_gt_1500ms": sum(dt > period_s * 1500 for dt in intervals),
    }


def rss_slope(series: list) -> dict:
    if len(series) < 4:
        return {"delta_kib": None}
    second_half = series[len(series) // 2 :]
    n = len(second_half)
    mean_x = sum(t for t, _ in second_half) / n
    mean_y = sum(rss for _, rss in second_half) / n
    denominator = sum((t - mean_x) ** 2 for t, _ in second_half) or 1.0
    slope = sum(
        (t - mean_x) * (rss - mean_y) for t, rss in second_half
    ) / denominator
    delta = series[-1][1] - series[0][1]
    return {
        "delta_kib": delta,
        "delta_mib": delta / 1024.0,
        "peak_kib": max(rss for _, rss in series),
        "second_half_slope_kib_per_min": slope * 60.0,
    }
