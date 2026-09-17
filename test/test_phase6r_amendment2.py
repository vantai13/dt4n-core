#!/usr/bin/env python3
"""Integrity tests for amendment 2 and the later FSM replay receipt."""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from ml.fsm import FSMParams
from scripts import build_phase6r_amendment2 as B

A2 = C.ROOT / "results/report/phase6r_amendment_2.json"
FSMR = C.ROOT / "results/report/phase6r_fsm.json"


@pytest.fixture(scope="module")
def a2():
    if not A2.exists():
        pytest.skip("chua dang ky amendment 2")
    return json.loads(A2.read_text(encoding="utf-8"))


def test_hash_and_artifacts(a2):
    content = a2["content"]
    assert a2["content_sha256"] == C.sha256_bytes(
        C.canonical_json(content).encode("utf-8")
    )
    for relative, digest in content["artifacts_sha256"].items():
        assert C.sha256_file(C.ROOT / relative) == digest, relative


def test_params_match_code_defaults_and_s4b(a2):
    params = a2["content"]["fsm"]["params"]
    assert FSMParams(**params) == FSMParams()
    assert (params["n_suspect"], params["n_act"]) == (1, 2)
    assert params["release_m"] > params["n_act"]
    assert params["cooldown_s"] >= 8


def test_predictions_derive_only_from_sealed_numbers(a2):
    predictions = a2["content"]["predictions"]
    baseline = json.loads(
        (C.ROOT / "results/report/phase6r_slo.json").read_text()
    )["content"]["measured_baseline"]
    assert predictions["P1_no_log_suspect_fp_events"]["value"] == 7
    assert baseline["n_fp_events_total"] == 7
    source = open(B.__file__, encoding="utf-8").read()
    for forbidden in (
        "phase6_envelope_ticks.csv",
        "replay_phase6r_fsm import",
        "labels_from_events",
        "y_test",
    ):
        assert forbidden not in source, forbidden


def test_inject_is_never_logged(a2):
    assert "inject" in a2["content"]["suppression"]["replay_interventions"]
    assert any("inject" in item for item in a2["content"]["forbidden"])


def test_whole_network_radius_is_disclosed(a2):
    full = a2["content"]["suppression"]["radius_covers_whole_network"]
    assert all("flood" in run_id or "shift" in run_id for run_id in full)
    assert len(full) == 4


def test_receipt_bound_to_amendment_and_reports_failures():
    if not FSMR.exists():
        pytest.skip("chua replay")
    document = json.loads(FSMR.read_text(encoding="utf-8"))
    content = document["content"]
    amendment = json.loads(A2.read_text(encoding="utf-8"))
    assert content["amendment_2_sha256"] == amendment["content_sha256"]
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(content).encode("utf-8")
    )
    assert set(content["prediction_checks"]) >= {
        "P1_no_log_suspect_fp_events",
        "P4_s7_violations",
    }
