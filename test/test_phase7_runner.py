#!/usr/bin/env python3
"""Phase 7.3: async runner, conflation, drop accounting and supervision."""
from __future__ import annotations

import copy
import json
import re
import threading
import time

import pytest
import requests

from bridge import detector_contract as D
from bridge import detector_runner as R
from ml import campaign as C
from ml.release import DetectorRelease


RELEASE = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
PREREG = json.loads((C.ROOT / "results/report/phase7_prereg.json").read_text())
GOLDEN = C.read_snapshots(C.ROOT / "test/fixtures/phase7_live_snapshots.jsonl")


def snaps(run_id):
    return C.read_snapshots(C.ROOT / "data/phase5/raw" / (run_id + ".jsonl"))


class Recorder:
    def __init__(self, delay=0.0, ok=True):
        self.delay = delay
        self.ok = ok
        self.docs = []
        self.threads = set()

    def __call__(self, thing_id, body):
        self.threads.add(threading.current_thread().name)
        time.sleep(self.delay)
        self.docs.append(body)
        return self.ok, "204" if self.ok else "503"


def runner(transport=None, **kwargs):
    kwargs.setdefault("timeline_samples", R.TIMELINE_SAMPLES)
    return R.DetectorRunner(RELEASE, PREREG, transport or Recorder(), **kwargs)


def feed(detector_runner, rows):
    for index, snapshot in enumerate(rows):
        detector_runner.on_tick(index, snapshot, float(index))


def freshness(document):
    return document["features"]["freshness"]["properties"]


def decision(document):
    return document["features"]["decision"]["properties"]


def test_on_tick_never_touches_network(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("gọi mạng trong luồng collector")

    monkeypatch.setattr(requests.Session, "request", boom)
    monkeypatch.setattr(requests, "patch", boom)
    detector_runner = runner()
    feed(detector_runner, snaps("F-flood-h1_to_srv1-s3005-r1"))
    assert detector_runner.exceptions == 0 and detector_runner.seq == 60


def test_transport_runs_only_on_writer_thread():
    recorder = Recorder()
    detector_runner = runner(recorder)
    detector_runner.start_writer()
    feed(detector_runner, GOLDEN)
    time.sleep(0.5)
    detector_runner.stop()
    assert recorder.threads == {"detector-writer"}


def test_mailbox_conflates_and_counts():
    mailbox = R.Mailbox()
    for index in range(3):
        mailbox.put(index)
    assert mailbox.take(0) == 2
    assert mailbox.overwritten == 2
    assert mailbox.take(0) is None


def test_slow_ditto_never_replays_old_state():
    recorder = Recorder(delay=0.15)
    detector_runner = runner(recorder)
    detector_runner.start_writer()
    for index, snapshot in enumerate(snaps("F-flood-h1_to_srv1-s3005-r1")[:30]):
        detector_runner.on_tick(index, snapshot, float(index))
        time.sleep(0.02)
    time.sleep(0.5)
    detector_runner.stop()
    sequences = [freshness(document)["seq"] for document in recorder.docs]
    assert sequences == sorted(set(sequences))
    assert sequences[-1] == 29
    assert detector_runner.mailbox.overwritten > 0
    assert detector_runner.stats()["on_tick_p95_ms"] < 50


def test_dropped_counts_failures_and_is_published():
    recorder = Recorder(ok=False)
    detector_runner = runner(recorder)
    detector_runner.start_writer()
    for index, snapshot in enumerate(GOLDEN[:6]):
        detector_runner.on_tick(index, snapshot, float(index))
        time.sleep(0.05)
    time.sleep(0.3)
    detector_runner.stop()
    assert (
        detector_runner.dropped
        == detector_runner.failed + detector_runner.mailbox.overwritten
        >= 5
    )
    assert freshness(recorder.docs[-1])["dropped"] >= 4


def test_first_document_has_detected_at():
    detector_runner = runner()
    detector_runner.on_tick(0, GOLDEN[0], 0.0)
    document = detector_runner.mailbox.take(0)[0]
    assert decision(document)["state"] == "warming_up"
    assert decision(document)["detectedAt"]
    assert detector_runner.exceptions == 0


def test_exception_gives_new_incarnation_without_stopping_collector(monkeypatch):
    detector_runner = runner()
    feed(detector_runner, GOLDEN[:5])
    old_boot = detector_runner.boot_id
    old_log = detector_runner.intervention_log
    monkeypatch.setattr(detector_runner.scorer, "observe", lambda _snapshot: 1 / 0)
    detector_runner.on_tick(5, GOLDEN[5], 5.0)
    assert detector_runner.exceptions == 1
    assert detector_runner.restarts == 1
    assert detector_runner.boot_id != old_boot
    assert detector_runner.seq == 0
    assert detector_runner.intervention_log is old_log
    detector_runner.on_tick(6, GOLDEN[6], 6.0)
    document = detector_runner.mailbox.take(0)[0]
    assert (decision(document)["state"], freshness(document)["bootId"]) == (
        "warming_up",
        detector_runner.boot_id,
    )


def test_deterministic_bug_becomes_crash_loop_not_silent_reset(monkeypatch):
    detector_runner = runner()
    monkeypatch.setattr(R.D, "build_document", lambda *_args, **_kwargs: 1 / 0)
    with pytest.raises(R.CrashLoop):
        for index, snapshot in enumerate(GOLDEN):
            detector_runner.on_tick(index, snapshot, float(index))
    assert detector_runner.exceptions == R.CRASH_LOOP[0] + 1


def test_restart_is_fresh_but_silence_is_stale():
    class Clock:
        t = 0.0

        def __call__(self):
            return self.t

    clock = Clock()
    tracker = D.FreshnessTracker(clock)
    tracker.observe({"bootId": "a", "seq": 7})
    tracker.observe({"bootId": "a", "seq": 8})
    clock.t = 2.0
    tracker.observe({"bootId": "b", "seq": 0})
    assert not tracker.is_stale({"ttlTicks": 3, "tickIntervalMs": 1000})
    clock.t = 5.5
    assert tracker.is_stale({"ttlTicks": 3, "tickIntervalMs": 1000})


def test_guard_publishes_unknown_and_keeps_evidence():
    rows = copy.deepcopy(snaps("C-load2M-s2001-r1")[:10])
    for snapshot in rows:
        for thing in snapshot["things"].values():
            if thing.get("attributes", {}).get("role") == "client":
                thing["features"]["traffic"]["txRate"] *= 4
    detector_runner = runner()
    feed(detector_runner, rows)
    document = detector_runner.mailbox.take(0)[0]
    assert (decision(document)["state"], decision(document)["cause"]) == (
        "unknown",
        D.GUARD_CAUSE,
    )
    assert "envelope" in document["features"]["evidence"]["properties"]


def test_unknown_topology_fails_closed():
    snapshot = copy.deepcopy(GOLDEN[3])
    snapshot["things"]["host-h9"] = snapshot["things"]["host-h1"]
    with pytest.raises(R.FatalContract):
        runner().on_tick(0, snapshot, 0.0)


def test_stop_exits_collector_loop():
    detector_runner = runner()
    detector_runner.stop_event.set()
    with pytest.raises(R.StopRunner):
        detector_runner.on_tick(0, GOLDEN[0], 0.0)


def test_run_forever_survives_collector_crash():
    class Flaky:
        calls = 0

        def run(self, duration, on_tick):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("mininet cmd lỗi")
            for index, snapshot in enumerate(GOLDEN):
                on_tick(index, snapshot, float(index))
            detector_runner.stop_event.set()
            on_tick(99, GOLDEN[-1], 99.0)

    detector_runner = runner()
    detector_runner.stop_event.wait = lambda _timeout: None
    assert detector_runner.run_forever(Flaky()) == "stopped"
    assert detector_runner.restarts == 1


def test_golden_live_replay_through_runner():
    detector_runner = runner()
    feed(detector_runner, GOLDEN)
    assert detector_runner.exceptions == 0
    assert detector_runner.seq == len(GOLDEN)
    assert decision(detector_runner.mailbox.take(0)[0])["state"] == "normal"


def test_scorer_only_built_through_release():
    source = (C.ROOT / "bridge/detector_runner.py").read_text()
    assert not re.search(r"(FastOnlineScorer|OnlineScorer|DetectorFSM)\(", source)
    assert "release.build(" in source


def test_write_timeout_below_ttl():
    assert R.WRITE_TIMEOUT_S < D.TTL_TICKS * D.TICK_INTERVAL_MS / 1000.0


def test_audit_rotates(tmp_path):
    audit = R.RotatingJsonl(str(tmp_path / "a.jsonl"), max_bytes=200, backups=2)
    for index in range(50):
        audit.write({"i": index, "pad": "x" * 20})
    audit.close()
    assert (tmp_path / "a.jsonl.1").exists()
    assert not (tmp_path / "a.jsonl.3").exists()


def test_timeline_marks_are_monotonic_and_joinable():
    rec = Recorder()
    detector_runner = runner(rec)
    detector_runner.start_writer()
    feed(detector_runner, GOLDEN[:6])
    time.sleep(0.4)
    detector_runner.stop()
    timeline, writes = list(detector_runner.timeline), list(detector_runner.writes)
    assert [entry["seq"] for entry in timeline] == list(range(6))
    assert all(entry["t_in"] <= entry["t1"] <= entry["t2"] for entry in timeline)
    assert all(
        0 <= entry["score_ms"] <= (entry["t1"] - entry["t_in"]) * 1000
        for entry in timeline
    )
    assert all("cause" in entry and "cycle_scan_ms" in entry for entry in timeline)
    by_seq = {entry["seq"]: entry for entry in timeline}
    for write in writes:
        assert write["bootId"] == by_seq[write["seq"]]["bootId"]
        assert write["t3"] >= write["t2"]
    assert len(timeline) <= R.TIMELINE_SAMPLES


def test_production_default_keeps_no_timeline():
    detector_runner = R.DetectorRunner(RELEASE, PREREG, Recorder())
    feed(detector_runner, GOLDEN)
    assert detector_runner.timeline.maxlen == 0
    assert len(detector_runner.timeline) == 0 and len(detector_runner.writes) == 0
    stats = detector_runner.stats()
    assert stats["timeline_samples"] == 0 and stats["score_p95_ms"] is not None
    assert stats["tick_gaps"] == 0 and stats["max_tick_dt_ms"] >= 0


def _retimed(n, t0=1.9e9):
    rows = []
    for index in range(n):
        snapshot = copy.deepcopy(GOLDEN[1 + index % (len(GOLDEN) - 1)])
        snapshot["t_source"], snapshot["tick"] = t0 + index, index
        rows.append(snapshot)
    return rows


def _growth_kib(timeline_samples, n=1500):
    import logging
    import tracemalloc

    detector_runner = R.DetectorRunner(
        RELEASE, PREREG, Recorder(), timeline_samples=timeline_samples
    )
    rows = _retimed(n + 100)
    logging.disable(logging.WARNING)
    try:
        feed(detector_runner, rows[:100])
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]
        for index, snapshot in enumerate(rows[100:], start=100):
            detector_runner.on_tick(index, snapshot, float(index))
        grown = tracemalloc.get_traced_memory()[0] - baseline
        tracemalloc.stop()
    finally:
        logging.disable(logging.NOTSET)
    assert detector_runner.exceptions == 0 and detector_runner.published == "normal"
    return grown / 1024


def test_production_memory_is_bounded_and_test_can_see_a_leak():
    production = _growth_kib(0)
    research = _growth_kib(R.TIMELINE_SAMPLES)
    assert production < 200, "production grew %.0f KiB / 1500 ticks" % production
    assert research > 5 * production, (
        "test must detect the timeline buffer (%.0f KiB)" % research
    )
