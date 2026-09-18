"""Boolean-only R-O1/R-O2 replay firewall required by amendment 6.

Never add counters, tick identifiers, states, entities, timestamps, scores or
debug persistence to these public results.  Debug failures only with synthetic
fixtures.
"""
from __future__ import annotations


R_O1_FIELDS = (
    "first_after_restart_is_warming_up",
    "no_act_before_n_scored",
    "no_normal_before_scored",
    "passed",
)
R_O2_FIELDS = (
    "first_after_gap_is_unknown_gap",
    "no_unjudgeable_tick_is_normal",
    "passed",
)


def _sealed(result: dict, fields: tuple) -> dict:
    """Enforce both the exact key set and the boolean-only value type."""
    extra = set(result) - set(fields)
    if extra:
        raise ValueError("vi pham tuong lua amendment 6, khoa la: %s" % sorted(extra))
    missing = set(fields) - set(result)
    if missing:
        raise ValueError("thieu truong hop dong: %s" % sorted(missing))
    if any(type(value) is not bool for value in result.values()):
        raise ValueError("moi truong phai la bool, khong duoc la so dem")
    return {key: result[key] for key in fields}


def replay_restart(scorer_factory, fsm_factory, snapshots, restart_ticks, *, n_act: int):
    """R-O1/S9: return one AND-aggregate across every checkpoint."""
    acc = dict.fromkeys(R_O1_FIELDS[:-1], True)
    for checkpoint in restart_ticks:
        scorer, fsm = scorer_factory(), fsm_factory()
        for offset, snapshot in enumerate(snapshots[checkpoint:]):
            transition = fsm.step(scorer.observe(snapshot))
            if offset == 0 and transition.state != "warming_up":
                acc["first_after_restart_is_warming_up"] = False
            if offset < n_act and transition.state == "act":
                acc["no_act_before_n_scored"] = False
            if offset == 0 and transition.state == "normal":
                acc["no_normal_before_scored"] = False
            if offset >= n_act + 2:
                break
    return _sealed({**acc, "passed": all(acc.values())}, R_O1_FIELDS)


def replay_gap(scorer_factory, fsm_factory, snapshots, gap_ticks, *, gap_len: int):
    """R-O2/S8: remove each registered span and return an AND-aggregate."""
    acc = dict.fromkeys(R_O2_FIELDS[:-1], True)
    for checkpoint in gap_ticks:
        scorer, fsm = scorer_factory(), fsm_factory()
        stream = list(snapshots[:checkpoint]) + list(snapshots[checkpoint + gap_len :])
        for index, snapshot in enumerate(stream):
            reading = scorer.observe(snapshot)
            transition = fsm.step(reading)
            if index == checkpoint and not (
                transition.state == "unknown" and transition.cause == "gap"
            ):
                acc["first_after_gap_is_unknown_gap"] = False
            if not reading.judgeable and transition.state == "normal":
                acc["no_unjudgeable_tick_is_normal"] = False
    return _sealed({**acc, "passed": all(acc.values())}, R_O2_FIELDS)
