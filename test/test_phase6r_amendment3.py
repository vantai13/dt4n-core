#!/usr/bin/env python3
"""Integrity and history-preservation checks for amendment 3."""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from ml.oscillation import s7_v1_violations

A3 = C.ROOT / "results/report/phase6r_amendment_3.json"


@pytest.fixture(scope="module")
def a3():
    if not A3.exists():
        pytest.skip("chua dang ky amendment 3")
    return json.loads(A3.read_text(encoding="utf-8"))


def test_hash_and_pins(a3):
    content = a3["content"]
    assert a3["content_sha256"] == C.sha256_bytes(
        C.canonical_json(content).encode("utf-8")
    )
    for relative, digest in {
        **content["artifacts_sha256"],
        **content["code_sha256"],
    }.items():
        assert C.sha256_file(C.ROOT / relative) == digest, relative


def test_old_p4_result_is_never_rewritten(a3):
    fsm = json.loads(
        (C.ROOT / "results/report/phase6r_fsm.json").read_text()
    )
    assert fsm["content"]["prediction_checks"]["P4_s7_violations"] is False
    assert a3["content"]["amends"]["fsm_receipt_sha256"] == fsm["content_sha256"]


def test_v1_definition_still_reproduces_recorded_failure():
    runs = json.loads(
        (C.ROOT / "results/report/phase6r_fsm.json").read_text()
    )["content"]["results"]["runs"]
    shift = [run_id for run_id in runs if run_id.startswith("F-shift")]
    assert all(
        s7_v1_violations(runs[run_id]["no_log"]["state_sequence_window"])
        == 1
        for run_id in shift
    )


def test_release_gates_cover_both_findings(a3):
    gates = a3["content"]["phase8_release_gates"]
    assert {"G1", "G2", "G3", "G4"} <= set(gates)
    assert "R-O" in gates["G1"] and "R-C" in gates["G2"]
    assert a3["content"]["timing_and_knowledge"]["r_campaign_collected"] is False


def test_variants_closed_before_collection(a3):
    variants = a3["content"]["variants_closed"]
    assert len(variants["registered"]) == 1
    assert "V1" in " ".join(variants["not_registered_and_not_evaluated_in_6R"])
