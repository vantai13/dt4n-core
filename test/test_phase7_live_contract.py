#!/usr/bin/env python3
"""Lesson 7.2: hợp đồng A (snapshot), B (Thing), C (freshness)."""
from __future__ import annotations

import copy
import json

import pytest

from bridge import collector_version as V
from bridge import detector_contract as D
from ml import campaign as C
from ml.intervention_log import InMemoryInterventionLog
from ml.release import DetectorRelease


RELEASE = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
ENTITIES = D.expected_entities(RELEASE.model)
EXPECTED = RELEASE.content["collector_version"]
GOLDEN = C.ROOT / "test/fixtures/phase7_live_snapshots.jsonl"
CONTRACT = C.ROOT / "results/report/phase7_contract.json"


def snaps(run_id):
    return C.read_snapshots(C.ROOT / "data/phase5/raw" / (run_id + ".jsonl"))


def replay(run_id, guard=lambda _index: False):
    scorer, fsm = RELEASE.build(InMemoryInterventionLog())
    for index, snapshot in enumerate(snaps(run_id)):
        reading = scorer.observe(snapshot)
        transition = fsm.step(reading)
        yield index, reading, transition, D.build_document(
            RELEASE,
            transition,
            reading,
            boot_id="b",
            seq=index,
            heartbeat_at="h",
            detected_at="d",
            dropped=0,
            guard_active=guard(index),
        )


def walk(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)
    else:
        yield obj


def test_measurement_sources_not_drifted():
    assert V.drifted_sources() == [], "đổi collector -> phải bump COLLECTOR_VERSION"


def test_producer_version_matches_what_release_expects():
    assert V.COLLECTOR_VERSION == EXPECTED


def test_live_meta_carries_producer_version():
    assert D.live_run_meta("abc")["collector_version"] == V.COLLECTOR_VERSION


def test_train_snapshot_satisfies_contract():
    for snapshot in snaps("N-load2M-s1003-r1"):
        assert D.check_live_snapshot(snapshot, ENTITIES, EXPECTED) == []


def test_f71_snapshot_without_run_is_caught():
    snapshot = copy.deepcopy(snaps("C-load2M-s2001-r1")[5])
    snapshot.pop("run")
    snapshot.pop("tick")
    problems = D.check_live_snapshot(snapshot, ENTITIES, EXPECTED)
    assert any(problem.startswith("A3") for problem in problems)


def test_unknown_topology_is_caught():
    snapshot = copy.deepcopy(snaps("C-load2M-s2001-r1")[5])
    snapshot["things"]["host-h4"] = snapshot["things"]["host-h1"]
    problems = D.check_live_snapshot(snapshot, ENTITIES, EXPECTED)
    assert any("topology lạ" in problem for problem in problems)


def test_release_payload_cannot_serve_normal_ticks():
    scorer, fsm = RELEASE.build(InMemoryInterventionLog())
    for snapshot in snaps("C-load2M-s2001-r1"):
        reading = scorer.observe(snapshot)
        transition = fsm.step(reading)
        if transition.state == "normal":
            with pytest.raises(ValueError):
                RELEASE.payload(transition, reading, detected_at="d")
            return
    pytest.fail("không gặp tick normal")


def test_document_every_tick_has_no_null_and_matches_oracle():
    states = set()
    for _, _, _, document in replay("F-flood-h1_to_srv1-s3005-r1"):
        assert None not in list(walk(document))
        states.add(document["features"]["decision"]["properties"]["state"])
    assert {"normal", "act"} <= states


def test_hysteresis_is_published_not_fixed():
    seen = False
    for _, _, transition, document in replay("F-degrade-s1-s2-s3003-r1"):
        evidence = document["features"]["evidence"]["properties"]
        if (
            transition.state == "suspect"
            and not evidence["envelope"]
            and not evidence["conservation"]
        ):
            assert document["features"]["decision"]["properties"]["state"] == "suspect"
            seen = True
    assert seen


def test_flood_affected_are_full_thing_ids():
    for _, _, transition, document in replay("F-flood-h1_to_srv1-s3005-r1"):
        if transition.state == "act":
            affected = document["features"]["evidence"]["properties"]["affected"]
            assert "org.dt4n:link-h1-s1" in affected
            assert all(item.startswith("org.dt4n:") for item in affected)
            return
    pytest.fail("không gặp tick act")


def test_guard_overrides_published_state_but_keeps_evidence():
    plain = list(replay("F-flood-h1_to_srv1-s3005-r1"))
    guarded = list(
        replay("F-flood-h1_to_srv1-s3005-r1", guard=lambda _index: True)
    )
    for (_, _, transition, first), (_, _, _, second) in zip(plain, guarded):
        decision = second["features"]["decision"]["properties"]
        if transition.state in D.GUARD_OVERRIDABLE:
            assert (decision["state"], decision["cause"]) == (
                "unknown",
                D.GUARD_CAUSE,
            )
        else:
            assert decision["state"] == transition.state
        assert first["features"]["evidence"] == second["features"]["evidence"]


def test_bootstrap_detector_is_never_normal():
    from bridge.bootstrap import entities_from_spec

    entities = entities_from_spec(str(C.ROOT / "ditto/topology_spec.json"))
    detector = [item for item in entities if item["thing_id"] == D.DETECTOR_THING_ID]
    assert len(detector) == 1
    properties = detector[0]["body"]["features"]["decision"]["properties"]
    assert properties["state"] != "normal"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def freshness(boot, seq):
    return {"bootId": boot, "seq": seq, "ttlTicks": 3, "tickIntervalMs": 1000}


def test_first_observation_only_arms():
    clock = Clock()
    tracker = D.FreshnessTracker(clock)
    tracker.observe(freshness("a", 41))
    assert tracker.is_stale(freshness("a", 41))


def test_stale_after_ttl_without_new_seq():
    clock = Clock()
    tracker = D.FreshnessTracker(clock)
    tracker.observe(freshness("a", 1))
    clock.t = 1.0
    tracker.observe(freshness("a", 2))
    clock.t = 3.9
    assert not tracker.is_stale(freshness("a", 2))
    clock.t = 4.1
    assert tracker.is_stale(freshness("a", 2))


def test_restart_new_boot_id_counts_as_heartbeat_even_if_seq_resets():
    clock = Clock()
    tracker = D.FreshnessTracker(clock)
    tracker.observe(freshness("a", 900))
    tracker.observe(freshness("a", 901))
    clock.t = 10.0
    tracker.observe(freshness("b", 0))
    assert not tracker.is_stale(freshness("b", 0))


@pytest.mark.skipif(not GOLDEN.exists(), reason="chưa ghi golden live (cần Mininet)")
def test_golden_live_snapshots_satisfy_contract():
    rows = C.read_snapshots(GOLDEN)
    assert len(rows) >= 10
    for snapshot in rows:
        assert snapshot["run"]["mode"] == "live"
        assert D.check_live_snapshot(snapshot, ENTITIES, EXPECTED) == []


@pytest.mark.skipif(not CONTRACT.exists(), reason="7.2 chưa niêm phong")
def test_contract_hash_and_upstream_pinned():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    )
    for relative, digest in document["content"]["upstream_sha256"].items():
        assert C.sha256_file(C.ROOT / relative) == digest, "đã đổi: " + relative
