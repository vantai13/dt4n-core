from __future__ import annotations

import pytest

from bridge.live_controller import LiveController
from measurements.stability import classify, rss_slope, tick_health, window_counts
from ml.intervention_log import InMemoryInterventionLog


def entry(t, fsm="normal", published=None, env=False, cons=False, act=False, cause=""):
    return {
        "seq": int(t), "t_source": 1000.0 + t, "t_in": 50.0 + t,
        "fsm": fsm, "published": published or fsm, "envelope": env,
        "conservation": cons, "act_rule": act, "cause": cause,
    }


def test_classify_all_kinds():
    assert classify(entry(0, "act", "unknown", env=True, cause="suppressed_intervention")) == "suppressed"
    assert classify(entry(0, "suspect", env=True)) == "env_alarm"
    assert classify(entry(0, "suspect", cons=True)) == "residual_only"
    assert classify(entry(0, "suspect")) == "held"
    assert classify(entry(0)) == "normal"


def test_window_counts_entries_only_inside_window():
    timeline = [
        entry(0), entry(1, "suspect", env=True), entry(2, "act", act=True),
        entry(3, "act", act=True), entry(4, "suspect", cons=True), entry(5),
        entry(6, "act", act=True),
    ]
    counts = window_counts(timeline, 1000.5, 1005.5)
    assert counts["act_entries"] == 1 and counts["alarm_entries"] == 1
    assert counts["residual_only"] == 1 and counts["env_alarm"] == 3
    assert counts["ticks"] == 5


def test_tick_health_detects_overrun_and_gap():
    health = tick_health([{"t_in": t} for t in (0.0, 1.0, 2.0, 3.3, 5.0)])
    assert health["overruns_gt_1050ms"] == 2
    assert health["gaps_gt_1500ms"] == 1


def test_rss_slope_flat_and_leak():
    flat = [(i * 30.0, 579712) for i in range(60)]
    assert rss_slope(flat)["second_half_slope_kib_per_min"] == pytest.approx(0.0)
    leak = [(i * 30.0, 579712 + 10 * i) for i in range(60)]
    assert rss_slope(leak)["second_half_slope_kib_per_min"] == pytest.approx(20.0)


class FakeRunner:
    def __init__(self):
        self.seq, self.timeline = 10, []


def test_controller_log_first_appends_before_command():
    log, order = InMemoryInterventionLog(), []
    controller = LiveController(
        log,
        lambda command: order.append(("post", len(log))) or {"http_status": 202},
        FakeRunner(),
        clock=lambda: 1000.0,
    )
    record = controller.act("inject", "s1-s2", "p1", "log_first")
    assert order == [("post", 1)]
    assert record["t_log_wall"] <= record["t_post_wall"]
    item = log.active(1000.5, 8.0)[0]
    assert "link-s1-s2" in item.blast_radius
    assert "switch-s3" in item.blast_radius


def test_controller_log_late_waits_for_scored_consequence():
    log, runner = InMemoryInterventionLog(), FakeRunner()
    runner.timeline = [dict(entry(11, "suspect", env=True), seq=11)]
    controller = LiveController(
        log,
        lambda command: len(log) == 0 and {"http_status": 202},
        runner,
        clock=lambda: 1000.0,
    )
    record = controller.act("inject", "s1-s2", "p2", "log_late", late_timeout_s=1.0)
    assert record["late_after_seq"] == 11 and len(log) == 1


def test_controller_no_log():
    log = InMemoryInterventionLog()
    LiveController(log, lambda command: {}, FakeRunner()).act(
        "inject", "s1-s2", "p3", "no_log"
    )
    assert len(log) == 0


def test_controller_log_late_counts_first_tick_scored_after_decision():
    """Hoi quy 7.6 live: runner.seq la seq SAP gan, nen tick seq == seq_before da la hau qua.
    Bo qua no lam log tre 2 tick (du n_act=2 de vao act) thay vi 1."""
    log, runner = InMemoryInterventionLog(), FakeRunner()
    runner.timeline = [dict(entry(10, "suspect", env=True), seq=10)]
    controller = LiveController(log, lambda command: {}, runner, clock=lambda: 1000.0)
    record = controller.act("inject", "s1-s2", "p4", "log_late", late_timeout_s=0.5)
    assert record["late_after_seq"] == 10
