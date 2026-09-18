"""Metric nghiem thu la ham thuan cua RunTrace va sidecar; khong I/O."""
from __future__ import annotations

from ml.acceptance_pass import ALARM_ZONE
from ml.acceptance_stats import false_alarm_rate_upper


def event_of(meta: dict, kind: str) -> dict:
    found = [event for event in meta["events"] if event["kind"] == kind]
    if len(found) != 1:
        raise ValueError("can dung mot su kien %s, co %d" % (kind, len(found)))
    return found[0]


def inject_clock(meta: dict) -> float:
    event = event_of(meta, "inject")
    return float(event["t_source"]) - float(event.get("apply_ms", 0.0)) / 1000.0


def window(meta: dict) -> tuple[int, int]:
    return event_of(meta, "inject")["tick"] + 1, event_of(meta, "revert")["tick"]


def entries(trace, channel: str, lo=None, hi=None) -> list:
    out = []
    for row in trace.rows:
        prev, state, changed, _ = row.state[channel]
        if changed and state in ALARM_ZONE and prev not in ALARM_ZONE and row.tick is not None:
            if (lo is None or row.tick >= lo) and (hi is None or row.tick <= hi):
                out.append(row)
    return out


def raw_runs(trace, channel: str) -> int:
    count, previous = 0, False
    for row in trace.rows:
        now = row.raw[channel]
        count += bool(now and not previous)
        previous = now
    return count


def incident(trace, meta: dict, channel: str) -> dict:
    lo, hi = window(meta)
    hits = entries(trace, channel, lo, hi)
    in_window = [row for row in trace.rows if row.tick is not None and lo <= row.tick <= hi]
    ks = [row.k for row in in_window if row.k is not None]
    out = {
        "detected": bool(hits),
        "max_k": max(ks) if ks else None,
        "first_tick": hits[0].tick if hits else None,
        "t_detect_ms": None,
    }
    if hits:
        if hits[0].t_available is None:
            raise ValueError("thieu t_cycle_end o tick %s" % hits[0].tick)
        out["t_detect_ms"] = (hits[0].t_available - inject_clock(meta)) * 1000.0
    return out


def s4_nearest_rank_p95(values_ms: list) -> float | None:
    if not values_ms:
        return None
    values = sorted(values_ms)
    index = min(len(values) - 1, max(0, round(0.95 * (len(values) - 1))))
    return values[index]


def s1_s4(incidents: dict) -> dict:
    detected = {key: value for key, value in incidents.items() if value["detected"]}
    censored = {key: value for key, value in incidents.items() if not value["detected"]}
    times = [value["t_detect_ms"] for value in detected.values()]
    return {
        "n_incidents": len(incidents),
        "n_detected": len(detected),
        "detection_rate": len(detected) / len(incidents) if incidents else None,
        "t_detect_p95_ms": s4_nearest_rank_p95(times),
        "t_detect_max_ms": max(times) if times else None,
        "n_censored_channels_left_envelope": sum((value["max_k"] or 0) > 0 for value in censored.values()),
        "n_censored_no_channel_left_envelope": sum((value["max_k"] or 0) == 0 for value in censored.values()),
    }


def s2_s3(traces: list, channel: str) -> dict:
    n_events = sum(len(entries(trace, channel)) for trace in traces)
    at_risk = sum(sum(row.at_risk[channel] for row in trace.rows) for trace in traces)
    return {
        **false_alarm_rate_upper(n_events, at_risk),
        "sensitivity_raw_consecutive_runs": sum(raw_runs(trace, channel) for trace in traces),
    }


def s10(trace, channel: str) -> dict:
    alarm = [row for row in trace.rows if row.state[channel][1] in ALARM_ZONE]

    def column(evidence_of):
        values = [evidence_of(row) for row in alarm]
        return {
            "fp_ticks": sum(value is False for value in values),
            "undetermined_ticks": sum(value is None for value in values),
        }

    return {
        "alarm_ticks": len(alarm),
        "raw_alarm_ticks": sum(row.raw[channel] for row in trace.rows),
        "col_a": column(lambda row: row.ev_strict),
        "col_b": column(lambda row: row.ev_sensitive),
        "col_c": column(lambda row: True if row.cons_alarm else row.ev_sensitive),
    }


# ================================================================ B.2
# Cac ham duoi day dung nhan y. Chi goi trong rehearsal Phase 5 hoac lan mo.
from ml.labels import labels_from_events  # noqa: E402
from ml.oscillation import s7_v1_violations, s7_v2  # noqa: E402

WARMUP_TICKS = 1
LEVELS = {
    "suspect_level": frozenset({"suspect", "act"}),
    "act_level": frozenset({"act"}),
}


def labels_of(trace, meta) -> list:
    return labels_from_events(len(trace.rows), meta["events"])


def fp_ticks_a2(trace, labels, channel: str, level: str) -> list:
    """Amendment 2: y=0 sau warmup va FSM state thuoc level."""
    group = LEVELS[level]
    return [
        row.tick
        for row in trace.rows
        if row.tick is not None
        and row.tick >= WARMUP_TICKS
        and labels[row.tick] == 0
        and row.state[channel][1] in group
    ]


def clusters(ticks: list) -> int:
    """So chuoi toi da cac tick lien ke, theo fp_event cua amendment 2."""
    ticks = sorted(ticks)
    return 0 if not ticks else 1 + sum(
        right - left > 1 for left, right in zip(ticks, ticks[1:])
    )


def s7(trace, meta, channel: str, cooldown_ticks: int) -> dict:
    """S7 tren cua so [inject+1, revert+cooldown], dung chuoi state tho."""
    lo, hi = window(meta)
    states = [
        row.state[channel][1]
        for row in trace.rows
        if row.tick is not None and lo <= row.tick <= hi + cooldown_ticks
    ]
    return {**s7_v2(states), "v1_violations": s7_v1_violations(states)}


def upstream_switch(link_key: str) -> str:
    return link_key.split("-")[0]


def rho_of(trace, record) -> float | None:
    """Median target-link txRate ticks 2..20 chia nang luc duoc cap."""
    params = record["fault_parameters"]
    values = sorted(
        row.probe["target_tx"]
        for row in trace.rows
        if row.tick is not None
        and 2 <= row.tick <= 20
        and row.probe.get("target_tx") is not None
    )
    if not values:
        return None
    n_values = len(values)
    median = (
        values[n_values // 2]
        if n_values % 2
        else (values[n_values // 2 - 1] + values[n_values // 2]) / 2
    )
    capacity = max(1.0, params["baseline"] * (1 - params["factor"])) * 1e6 / 8
    return median / capacity


def residual_run(trace, meta) -> dict:
    """P1/P2/P3/F3/F4/F5 cho mot run R-D, theo tick eval_primary."""
    labels = labels_of(trace, meta)
    record = meta["record"]
    rows = [
        row
        for row in trace.rows
        if row.tick is not None and row.tick >= WARMUP_TICKS
    ]
    fault = [row for row in rows if labels[row.tick] == 1]
    background = [row for row in rows if labels[row.tick] == 0]
    alarm_fault = [row for row in fault if row.cons_alarm]
    expected = upstream_switch(record["fault_target"])
    return {
        "rho": rho_of(trace, record),
        "fault_ticks": len(fault),
        "residual_fault_fraction": len(alarm_fault) / len(fault) if fault else None,
        "background_ticks": len(background),
        "background_alarm_ticks": sum(row.cons_alarm for row in background),
        "alarm_ticks_all": sum(row.cons_alarm for row in rows),
        "argmax_correct_ticks": sum(
            row.cons_alarm and row.cons_switch == expected for row in rows
        ),
        "incremental_ticks": sum(
            row.cons_alarm and not row.envelope_suspect for row in fault
        ),
        "residual_alarms_on_unscored_ticks": sum(
            row.cons_alarm and row.status != "scored" for row in rows
        ),
    }


def amendment1_verdicts(
    per_run: dict, s2_combined_upper: float, s2_target: float = 3.0
) -> dict:
    """Tinh F1-F6 va outcome bang dung nguong amendment 1."""
    detected = {
        key: (value["residual_fault_fraction"] or 0.0) >= 0.50
        for key, value in per_run.items()
    }
    high = [
        key
        for key, value in per_run.items()
        if value["rho"] is not None and value["rho"] >= 1.10
    ]
    low = [
        key
        for key, value in per_run.items()
        if value["rho"] is not None and value["rho"] <= 0.90
    ]
    band = [
        key
        for key, value in per_run.items()
        if value["rho"] is None or 0.90 < value["rho"] < 1.10
    ]
    background = sum(value["background_ticks"] for value in per_run.values())
    background_alarm = sum(
        value["background_alarm_ticks"] for value in per_run.values()
    )
    alarms = sum(value["alarm_ticks_all"] for value in per_run.values())
    correct = sum(value["argmax_correct_ticks"] for value in per_run.values())
    p1 = sum(detected[key] for key in high)
    refuted = {
        "F1": bool(high) and p1 / len(high) < 0.75,
        "F2": any(detected[key] for key in low),
        "F3": background > 0 and background_alarm / background > 0.02,
        "F4": alarms > 0 and correct / alarms < 0.90,
        "F5": sum(value["incremental_ticks"] for value in per_run.values()) == 0,
        "F6": s2_combined_upper > s2_target,
    }
    if not any(refuted[key] for key in ("F1", "F2", "F3", "F5", "F6")):
        outcome = "F4_only" if refuted["F4"] else "all_pass"
    else:
        outcome = "any_of_F1_F2_F3_F5_F6"
    return {
        "refuted": refuted,
        "outcome": outcome,
        "counts": {
            "n_high": len(high),
            "n_high_detected": p1,
            "n_low": len(low),
            "n_low_detected": sum(detected[key] for key in low),
            "n_no_prediction_band": len(band),
            "background_ticks": background,
            "background_alarm_ticks": background_alarm,
            "alarm_ticks": alarms,
            "argmax_correct": correct,
        },
    }
