#!/usr/bin/env python3
"""Pure latency decomposition and aggregation for Lesson 7.5."""
from __future__ import annotations

ALARM = ("suspect", "act")


def _ms(a, b):
    return None if a is None or b is None else (b - a) * 1000.0


def decompose(trial: dict, timeline: list, writes: list, perf_mono: list) -> dict:
    t_a, t_b = trial["tA"], trial["tB"]
    after = sorted((e for e in timeline if e["t_in"] > t_b), key=lambda e: e["t_in"])
    before = [e for e in timeline if e["t_in"] <= t_a]
    observed = next(
        (e for e in after if e["envelope"] or e["conservation"] or e["act_rule"]),
        None,
    )
    alarm = next((e for e in after if e["published"] in ALARM), None)
    out = {
        "trial": trial["i"],
        "warmup": trial.get("warmup", False),
        "detected": alarm is not None,
    }
    if before and after:
        previous = max(before, key=lambda e: e["t_in"])
        first = after[0]
        span = first["t_in"] - previous["t_in"]
        out["inject_phase"] = (t_a - previous["t_in"]) / span if span > 0 else None
        out["tick_dt_across_inject_ms"] = span * 1000.0
        out["inject_offset_s"] = t_a - previous["t_in"]
        seq_ticks = sorted(
            e["t_in"]
            for e in timeline
            if previous["t_in"] <= e["t_in"] <= first["t_in"]
        )
        out["ticks_inside_cmd"] = sum(1 for tick in seq_ticks if t_a < tick <= t_b)
        out["max_consecutive_dt_ms"] = max(
            (right - left) * 1000.0
            for left, right in zip(seq_ticks, seq_ticks[1:])
        )
    if alarm is None:
        return out

    boot, alarm_seq = alarm["bootId"], alarm["seq"]
    write = next(
        (
            item
            for item in sorted(writes, key=lambda item: item["seq"])
            if item["ok"]
            and item["bootId"] == boot
            and item["seq"] >= alarm_seq
            and item["published"] in ALARM
        ),
        None,
    )
    perf = next(
        (
            item
            for item in sorted(perf_mono, key=lambda item: item["seq"])
            if item["source"] == "sse"
            and item["bootId"] == boot
            and item["seq"] >= alarm_seq
            and item["state"] in ALARM
            and item["t5"] is not None
        ),
        None,
    )
    t_obs = (observed or {}).get("t_in")
    t1, t2 = alarm["t1"], alarm["t2"]
    t3 = write["t3"] if write else None
    t4, t_dom, t5 = (
        (perf["t4"], perf["tDom"], perf["t5"])
        if perf
        else (None, None, None)
    )
    out.update(
        {
            "seq_alarm": alarm_seq,
            "seq_written": write["seq"] if write else None,
            "seq_shown": perf["seq"] if perf else None,
            "state_first": alarm["published"],
            "conflated": bool(write and write["seq"] > alarm_seq),
            "layers_ms": {
                "phys_obs": _ms(t_b, t_obs),
                "detect": _ms(t_obs, t1),
                "mailbox": _ms(t1, t2),
                "write_2xx": _ms(t2, t3),
                "fanout_sse": _ms(t2, t4),
                "vue_flush": _ms(t4, t_dom),
                "paint": _ms(t_dom, t5),
            },
            "budget_ms": {
                "s4_like_from_cmd": _ms(t_a, t1),
                "twin_ui": _ms(t1, t5),
                "e2e_from_event": _ms(t_b, t5),
                "e2e_from_cmd": _ms(t_a, t5),
                "inject_cmd": _ms(t_a, t_b),
            },
        }
    )
    return out


LAYER_KEYS = [
    "phys_obs", "detect", "mailbox", "write_2xx", "fanout_sse", "vue_flush", "paint"
]
BUDGET_KEYS = [
    "s4_like_from_cmd", "twin_ui", "e2e_from_event", "e2e_from_cmd", "inject_cmd"
]
BUDGET_TARGETS_MS = {
    "s4_like_from_cmd": 3000,
    "twin_ui": 1000,
    "e2e_from_event": 5000,
}


def _summ(values_ms):
    from measurements.stats import summarize

    values = [value / 1000.0 for value in values_ms if value is not None]
    return summarize(values) if values else None


def aggregate(rows: list) -> dict:
    used = [row for row in rows if not row["warmup"]]
    detected = [row for row in used if row["detected"]]
    budgets = {
        key: _summ([row["budget_ms"][key] for row in detected])
        for key in BUDGET_KEYS
    }
    phases = sorted(
        row["inject_offset_s"] % 1.0
        for row in used
        if row.get("inject_offset_s") is not None
    )
    return {
        "n_trials": len(used),
        "n_detected": len(detected),
        "warmup_excluded": [row["trial"] for row in rows if row["warmup"]],
        "layers": {
            key: _summ([row["layers_ms"][key] for row in detected])
            for key in LAYER_KEYS
        },
        "budgets": budgets,
        "verdict_p95": {
            key: budgets[key] is not None and budgets[key]["p95_ms"] <= target
            for key, target in BUDGET_TARGETS_MS.items()
        },
        "randomization": {
            "inject_phase_sorted": [round(value, 3) for value in phases],
            "inject_offset_s_sorted": [round(value, 3) for value in phases],
            "definition": "v2: (tA - t_in previous tick) mod nominal 1.0 s",
            "quartile_counts": [
                sum(q / 4 <= value < (q + 1) / 4 for value in phases)
                for q in range(4)
            ],
        },
        "tick_dt_across_inject": _summ(
            [row.get("tick_dt_across_inject_ms") for row in used]
        ),
        "max_consecutive_dt": _summ(
            [row.get("max_consecutive_dt_ms") for row in used]
        ),
        "ticks_inside_cmd_total": sum(row.get("ticks_inside_cmd", 0) for row in used),
        "conflated_trials": sum(row.get("conflated", False) for row in detected),
    }


def plot(rows: list, path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    keys = ["phys_obs", "detect", "mailbox", "fanout_sse", "vue_flush", "paint"]
    complete = [
        row
        for row in rows
        if row.get("detected")
        and not row["warmup"]
        and all(row["layers_ms"][key] is not None for key in keys)
    ]
    if not complete:
        return False
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 4.5))
    bottom = [0.0] * len(complete)
    for key in keys:
        values = [row["layers_ms"][key] for row in complete]
        left.bar(range(len(complete)), values, bottom=bottom, label=key)
        bottom = [base + value for base, value in zip(bottom, values)]
    left.axhline(5000, ls="--", c="r", lw=1)
    left.set(title="Per-trial critical path", xlabel="trial", ylabel="ms")
    left.legend(fontsize=7)
    right.hist([row["budget_ms"]["e2e_from_event"] for row in complete], bins=12)
    right.set(title="e2e_from_event", xlabel="ms", ylabel="trials")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True
