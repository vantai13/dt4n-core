#!/usr/bin/env python3
"""Synthetic tests for FSM, intervention log, and routing radius."""
from __future__ import annotations

import inspect

import pytest

from ml import campaign as C
from ml import fsm as F
from ml.blast_radius import Routing, entity_of, radius, radius_with_detour
from ml.fsm import DetectorFSM, FSMParams
from ml.intervention_log import MAX_OPEN_S, InMemoryInterventionLog, Intervention
from ml.serve import Reading

ROUTING = Routing.load(C.ROOT / "ditto/routing_table.json")


def rd(
    tick,
    status="scored",
    suspect=False,
    act=False,
    violating=(),
    cause=None,
    reason="x",
):
    return Reading(
        t_source=float(tick),
        tick=int(tick),
        status=status,
        reason=reason if (suspect or act or status != "scored") else "",
        judgeable=status == "scored",
        suspect=suspect,
        act=act,
        violating=tuple(violating),
        cause=cause,
    )


def run(fsm, readings):
    return [fsm.step(reading) for reading in readings]


def warmed(params=FSMParams(), log=None):
    fsm = DetectorFSM(params, log)
    fsm.step(rd(0, status="warming_up", cause="warmup"))
    return fsm


def test_release_must_exceed_act_debounce():
    with pytest.raises(ValueError):
        FSMParams(n_act=2, release_m=2)


def test_first_reading_is_warming_up_then_normal():
    fsm = DetectorFSM(FSMParams())
    assert fsm.step(rd(0, status="warming_up", cause="warmup")).state == "warming_up"
    assert fsm.step(rd(1)).state == "normal"


def test_suspect_enters_immediately_with_n_suspect_1():
    assert warmed().step(rd(1, suspect=True)).state == "suspect"


def test_act_needs_two_consecutive_act_readings():
    fsm = warmed()
    assert fsm.step(rd(1, suspect=True, act=True)).state == "suspect"
    assert fsm.step(rd(2, suspect=True, act=True)).state == "act"


def test_unknown_breaks_act_consecutiveness():
    fsm = warmed()
    fsm.step(rd(1, suspect=True, act=True))
    assert fsm.step(rd(2, status="unknown", cause="gap")).state == "unknown"
    assert fsm.step(rd(3, suspect=True, act=True)).state == "suspect"


def test_release_after_exactly_m_quiet_ticks():
    fsm = warmed()
    fsm.step(rd(1, suspect=True))
    assert [fsm.step(rd(tick)).state for tick in (2, 3, 4)] == [
        "suspect",
        "suspect",
        "normal",
    ]


def test_act_is_held_while_only_suspect_remains():
    fsm = warmed()
    run(fsm, [rd(1, suspect=True, act=True), rd(2, suspect=True, act=True)])
    assert [fsm.step(rd(tick, suspect=True)).state for tick in (3, 4, 5)] == ["act"] * 3
    assert [fsm.step(rd(tick)).state for tick in (6, 7, 8)] == ["act", "act", "normal"]


def test_flapping_signal_does_not_flap_state():
    fsm = warmed()
    output = run(
        fsm, [rd(tick, suspect=tick % 2 == 1) for tick in range(1, 41)]
    )
    assert sum(transition.changed for transition in output) == 1
    assert output[-1].state == "suspect"


def test_exit_from_unknown_never_restores_act():
    fsm = warmed()
    run(fsm, [rd(1, suspect=True, act=True), rd(2, suspect=True, act=True)])
    fsm.step(rd(3, status="unknown", cause="missing_data"))
    assert fsm.step(rd(4)).state == "normal"


def test_rejected_reading_does_not_move_fsm():
    fsm = warmed()
    fsm.step(rd(1, suspect=True))
    transition = fsm.step(rd(2, status="rejected", cause="rejected"))
    assert transition.state == "suspect" and not transition.changed
    assert fsm.state == "suspect"


def log_with(links=(), flows=(), tick=10.0, intervention_id="i1"):
    log = InMemoryInterventionLog()
    targets = {"links": list(links), "flows": [list(flow) for flow in flows]}
    log.append(
        Intervention(
            intervention_id,
            tick,
            "controller",
            "set_bw",
            targets,
            radius(ROUTING, targets),
            ROUTING.sha256,
        )
    )
    return log


def test_suppression_only_when_all_local_evidence_in_radius():
    fsm = warmed(log=log_with(links=["s2-s3"]))
    inside = fsm.step(
        rd(
            11,
            suspect=True,
            violating=["link-s2-s3.traffic.txRate", "agg.rate_absz_max"],
        )
    )
    assert inside.state == "unknown"
    assert inside.cause == "suppressed_intervention"
    assert inside.suppressed_by == ("i1",)
    outside = fsm.step(
        rd(
            12,
            suspect=True,
            violating=["link-s2-s3.traffic.txRate", "host-h1.traffic.txRate"],
        )
    )
    assert outside.state == "suspect"


def test_agg_only_evidence_is_never_suppressed():
    fsm = warmed(log=log_with(links=["s2-s3"]))
    assert fsm.step(rd(11, suspect=True, violating=["agg.rate_absz_max"])).state == "suspect"


def test_suppression_expires_without_anyone_calling():
    fsm = warmed(log=log_with(links=["s2-s3"], tick=10.0))
    evidence = ["link-s2-s3.traffic.txRate"]
    assert fsm.step(rd(17.9, suspect=True, violating=evidence)).cause == "suppressed_intervention"
    assert fsm.step(rd(18.0, suspect=True, violating=evidence)).state == "suspect"


def test_suppression_leaves_audit_reason():
    fsm = warmed(log=log_with(links=["s1-s2"], intervention_id="ctl-42"))
    transition = fsm.step(
        rd(11, act=True, suspect=True, violating=["link-s1-s2.traffic.txRate"])
    )
    assert "ctl-42" in transition.reason
    assert transition.suppressed_by == ("ctl-42",)


def test_non_alarming_ticks_are_not_suppressed_during_cooldown():
    assert warmed(log=log_with(links=["s1-s2"])).step(rd(11)).state == "normal"


def test_log_is_append_only_and_has_no_disable_api():
    log = log_with(links=["s1-s2"])
    with pytest.raises(ValueError):
        log.append(
            Intervention(
                "i1",
                20.0,
                "controller",
                "x",
                {"links": ["s1-s3"]},
                radius(ROUTING, {"links": ["s1-s3"]}),
                ROUTING.sha256,
            )
        )
    assert not any(
        hasattr(log, name)
        for name in ("remove", "clear", "disable", "delete", "set_suppressed")
    )


def test_radius_is_second_order_and_can_cover_whole_network():
    small = radius(ROUTING, {"links": ["s2-s3"]})
    assert "host-h1" not in small and "link-s2-srv1" in small
    assert len(radius(ROUTING, {"flows": [["h1", "srv1"]]})) == 16


def test_admin_down_radius_adds_only_the_alternate_switch_corridor():
    original = radius(ROUTING, {"links": ["s1-s2"]})
    amended = radius_with_detour(ROUTING, {"links": ["s1-s2"]})
    assert amended - original == {"switch-s3", "link-s1-s3", "link-s2-s3"}
    assert "host-srv2" not in amended and "link-s3-srv2" not in amended


def test_stale_lease_is_exposed_while_alarm_flow_resumes():
    log = InMemoryInterventionLog()
    log.append(
        Intervention(
            "run:inject",
            10.0,
            "controller",
            "inject:admin_down",
            {"links": ["s1-s2"]},
            frozenset({"link-s1-s2"}),
            "x" * 64,
        )
    )
    fsm = warmed(log=log)
    transition = fsm.step(
        rd(
            10.0 + MAX_OPEN_S,
            suspect=True,
            violating=["link-s1-s2.traffic.txRate"],
        )
    )
    assert transition.state == "suspect"
    assert transition.cause == "stale_intervention"
    assert "ngung uc che" in transition.reason


def test_stale_lease_is_exposed_on_unknown_reading():
    log = InMemoryInterventionLog()
    log.append(
        Intervention(
            "run:inject",
            10.0,
            "controller",
            "inject:admin_down",
            {"links": ["s1-s2"]},
            frozenset({"link-s1-s2"}),
            "x" * 64,
        )
    )
    transition = warmed(log=log).step(
        rd(10.0 + MAX_OPEN_S, status="unknown", cause="missing_data")
    )
    assert transition.state == "unknown"
    assert transition.cause == "stale_intervention"


def test_entity_of_agg_is_none():
    assert entity_of("agg.loss_max") is None
    assert entity_of("switch-s1.status.state_up") == "switch-s1"


def test_fsm_never_touches_labels_or_raw_features():
    source = inspect.getsource(F)
    for forbidden in (
        "labels",
        "is_fault",
        "y_test",
        "flatten",
        "load_split",
        "excess >",
    ):
        assert forbidden not in source, forbidden
