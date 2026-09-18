"""Goi phat hanh phai toan ven va tuong duong kenh combined da nghiem thu."""
import dataclasses
import json

import pytest

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.release import DetectorRelease, ReleaseError

REL = C.ROOT / "models/detector-release-1.0.0.json"


@pytest.fixture(scope="module")
def release():
    return DetectorRelease.load(REL)


def _runs():
    contract = C.load_contract(C.ROOT / "results/report/experiment_matrix.json")
    return [run["run_id"] for run in contract["runs"]]


def _snapshots(run_id):
    with C.run_paths(run_id, C.ROOT)["final"].open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_release_self_hash_and_tamper(tmp_path, release):
    doc = json.loads(REL.read_text())
    doc["content"]["fsm_params"]["cooldown_s"] = 30.0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc))
    with pytest.raises(ReleaseError):
        DetectorRelease.load(bad)


def test_release_pins_accepted_configuration(release):
    prereg = json.loads(
        (C.ROOT / "results/report/phase6r_acceptance_prereg.json").read_text()
    )
    assert release.content["fsm_params"] == prereg["content"]["frozen_configuration"]["fsm_params"]
    assert release.content["conservation_mode"] == "active"
    assert release.model.content_sha256 == prereg["content"]["frozen_configuration"]["artifact"]["content_sha256"]


@pytest.mark.parametrize("run_id", _runs())
def test_active_mode_equals_accepted_combined_channel(release, run_id):
    from ml.serve_fast import FastOnlineScorer

    scorer_active, fsm_active = release.build()
    scorer_shadow = FastOnlineScorer(
        release.model,
        expected_collector_version=release.content["collector_version"],
        warmup_ticks=int(release.content["warmup_ticks"]),
        conservation=release.conservation,
        conservation_mode="shadow",
    )
    fsm_shadow = DetectorFSM(FSMParams(**release.content["fsm_params"]))
    for snapshot in _snapshots(run_id):
        reading_active = scorer_active.observe(snapshot)
        reading_shadow = scorer_shadow.observe(snapshot)
        transition_active = fsm_active.step(reading_active)
        derived = reading_shadow.envelope_suspect or reading_shadow.cons_alarm
        transition_shadow = fsm_shadow.step(
            dataclasses.replace(reading_shadow, suspect=derived)
            if reading_shadow.status == "scored"
            else reading_shadow
        )
        assert (
            transition_active.state,
            transition_active.cause,
        ) == (
            transition_shadow.state,
            transition_shadow.cause,
        ), (run_id, snapshot.get("tick"))
        assert reading_active.act == reading_shadow.act


def test_payload_traceability_and_evidence(release):
    n_checked = 0
    for run_id in _runs():
        scorer, fsm = release.build()
        for snapshot in _snapshots(run_id):
            reading = scorer.observe(snapshot)
            transition = fsm.step(reading)
            if transition.state == "normal" or reading.status == "rejected":
                continue
            n_checked += 1
            body = release.payload(
                transition, reading, detected_at="2026-09-18T00:00:00Z"
            )
            for key in (
                "modelVersion",
                "artifactSha256",
                "releaseVersion",
                "releaseSha256",
                "conservationSha256",
                "evidence",
            ):
                assert body[key]
            assert body["state"] == transition.state
            if transition.prev == "normal" and transition.state == "suspect":
                assert body["evidence"]["envelope"] or body["evidence"]["conservation"]
    assert n_checked > 0


def test_payload_refuses_mismatched_tick(release):
    run_id = _runs()[0]
    scorer, fsm = release.build()
    snapshots = _snapshots(run_id)
    reading1 = scorer.observe(snapshots[0])
    transition1 = fsm.step(reading1)
    reading2 = scorer.observe(snapshots[1])
    fsm.step(reading2)
    with pytest.raises(ReleaseError):
        release.payload(transition1, reading2, detected_at="x")
