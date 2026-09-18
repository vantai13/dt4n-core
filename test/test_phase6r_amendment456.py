#!/usr/bin/env python3
"""Test noi dung cho amendment 4, 5, 6 -- ba amendment truoc day khong co test.

Sổ trôi lệch (test_amendment_pin_ledger) da phu phan PIN cua chung. File nay
phu phan NOI DUNG: chuoi hash lien ket, luat gate outcome-independent, luat
rerun, va hop dong tuong lua boolean cua R-O.
"""
from __future__ import annotations

import json

import pytest

from ml import campaign as C

REPORT = C.ROOT / "results/report"


def _load(name):
    document = json.loads((REPORT / name).read_text())
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    ), "%s: content_sha256 khong khop noi dung" % name
    return document


@pytest.mark.parametrize("number", [4, 5, 6])
def test_content_sha256_is_self_consistent(number):
    document = _load("phase6r_amendment_%d.json" % number)
    assert document["content"]["amendment_id"] == "DT4N-P6R-AMENDMENT-%d" % number


def test_amendment_chain_is_linked_by_hash():
    """Moi amendment ghim hash NOI DUNG cua amendment truoc -> chuoi khong the
    chen hay sua hoi to mot mat khau nao."""
    for earlier, later, key in (
        (3, 4, "amendment_3_sha256"),
        (4, 5, "amendment_4_sha256"),
        (5, 6, "amendment_5_sha256"),
    ):
        previous = _load("phase6r_amendment_%d.json" % earlier)
        current = _load("phase6r_amendment_%d.json" % later)
        assert current["content"]["amends"][key] == previous["content_sha256"], (
            "a%d khong ghim dung content_sha256 cua a%d" % (later, earlier)
        )


# ---------------------------------------------------------------- amendment 4

def test_amendment_4_gates_are_outcome_independent():
    gates = _load("phase6r_amendment_4.json")["content"]["run_acceptance_gates"]
    assert "khong bao gio kiem KET CUC DANG DO" in gates["principle"]
    assert gates["R-D"].startswith("signal_present KHONG la gate")
    assert gates["implementation"] == "ml.rcampaign.verify_rrun"


def test_amendment_4_rerun_policy_forbids_outcome_driven_reruns():
    policy = _load("phase6r_amendment_4.json")["content"]["rerun_policy"]
    assert policy["max_attempts_per_cell"] == 2
    assert "ket cuc detector" in policy["forbidden"]
    assert "THIET BI" in policy["allowed_when"]


def test_amendment_4_defers_s12_and_blocks_release():
    split = _load("phase6r_amendment_4.json")["content"]["r_o_split"]
    assert split["R-O4_kill_detector_S12"]["mode"] == "DOI SANG PHASE 7"
    status = split["gate_status_in_6R"]
    assert status["G4_S12"] == "KHONG DONG DUOC TRONG 6R"
    assert "FSM khong the phat hanh cho Phase 8" in status["consequence"]


def test_amendment_4_r_n_is_reported_in_two_columns():
    classification = _load("phase6r_amendment_4.json")["content"]["r_n_classification"]
    assert "hai cot" in classification["report"]
    assert "cot thu hai" in classification["report"]
    basis = classification["physically_justified_tick"]
    for token in ("qdiscDropDelta", "lossPct", "r_max"):
        assert token in basis


# ---------------------------------------------------------------- amendment 5

def test_amendment_5_keeps_run_ids_inside_the_hashed_contract():
    clarification = _load("phase6r_amendment_5.json")["content"][
        "clarification_1_rerun_identity"
    ]
    assert "GIU run_id trong hop dong" in clarification["implemented"]
    assert "NGOAI hop dong" in clarification["why"]
    contract = C.load_contract(REPORT / "experiment_matrix.json")
    run_ids = [record["run_id"] for record in contract["runs"]]
    assert len(run_ids) == len(set(run_ids))
    assert not any(run_id.endswith("-r0") for run_id in run_ids)


def test_amendment_5_intervention_t_start_precedes_apply():
    clarification = _load("phase6r_amendment_5.json")["content"][
        "clarification_2_intervention_t_start"
    ]
    assert "NGAY TRUOC khi apply" in clarification["r_campaign_runtime"]
    assert "append-before-act" in clarification["why"]
    assert "sidecar.interventions" in clarification["analysis_rule"]
    assert "KHONG dung events" in clarification["analysis_rule"]


def test_amendment_5_was_registered_before_collection():
    timing = _load("phase6r_amendment_5.json")["content"]["timing_and_knowledge"]
    assert timing["r_campaign_collected"] is False
    assert timing["outcome_information_used"] == "khong"


# ---------------------------------------------------------------- amendment 6

def test_amendment_6_pins_the_collection_receipt():
    amendment = _load("phase6r_amendment_6.json")["content"]
    pinned = amendment["pinned_receipt_sha256"]
    relative, digest = next(iter(pinned.items()))
    assert C.sha256_file(C.ROOT / relative) == digest, (
        "receipt thu thap da doi sau khi a6 ghim no"
    )
    timing = amendment["timing_and_knowledge"]
    assert timing["r_campaign_collected"] is True
    assert timing["labels_opened"] is False
    assert timing["raw_snapshot_lines_read_for_this_decision"] is False
    assert timing["detector_or_fsm_output_read_for_this_decision"] is False


@pytest.mark.parametrize(
    "receipt,contract_key",
    [
        ("phase6r_replay_o1.json", "R_O1_restart_S9_boolean_fields_only"),
        ("phase6r_replay_o2.json", "R_O2_gap_S8_boolean_fields_only"),
    ],
)
def test_amendment_6_boolean_firewall_holds_in_the_receipts(receipt, contract_key):
    """Tuong lua: receipt R-O chi duoc chua DUNG cac truong bool da dang ky.

    Bat ky truong them (count, tick index, ten entity) deu la mot ro ri tu
    R-S sang phan tich S2/S3 sau nay.
    """
    allowed = _load("phase6r_amendment_6.json")["content"][
        "public_output_contract"
    ][contract_key]
    content = _load(receipt)["content"]
    assert sorted(content) == sorted(allowed), (
        "%s lech khoi hop dong tuong lua: %s" % (receipt, sorted(content))
    )
    assert all(isinstance(value, bool) for value in content.values())
    assert content["passed"] is all(
        value for key, value in content.items() if key != "passed"
    )


def test_amendment_6_firewall_survives_the_amendment_7_repair():
    """Amendment 7 khong duoc chay lai hay sua hai receipt boolean nay."""
    unchanged = _load("phase6r_amendment_7.json")["content"]["unchanged"]
    blob = json.dumps(unchanged)
    assert "R-O1" in blob and "R-O2" in blob and "not rerun" in blob
    for receipt in ("phase6r_replay_o1.json", "phase6r_replay_o2.json"):
        assert _load(receipt)["content"]["passed"] is True
