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
