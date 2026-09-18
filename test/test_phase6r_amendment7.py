import json

from ml import campaign as C


REPORT = C.ROOT / "results/report"


def _load(name):
    document = json.loads((REPORT / name).read_text())
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    )
    return document


def test_amendment_7_pins_the_original_failure():
    amendment = _load("phase6r_amendment_7.json")["content"]
    failed = _load("phase6r_replay_o3.json")
    assert amendment["trigger"]["failed_receipt_content_sha256"] == failed["content_sha256"]
    assert amendment["trigger"]["failed_receipt_file_sha256"] == C.sha256_file(
        REPORT / "phase6r_replay_o3.json"
    )
    assert amendment["diagnosis"]["H1_unknown_before_suppression"]["confirmed"] is False
    assert amendment["diagnosis"]["H2_local_not_subset_of_zone"]["confirmed"] is True


def test_amendment_7_does_not_move_detector_thresholds():
    amendment = _load("phase6r_amendment_7.json")["content"]["unchanged"]
    params = _load("phase6r_amendment_2.json")["content"]["fsm"]["params"]
    assert amendment["S11_target"] == "0 act entries"
    assert amendment["cooldown_s"] == params["cooldown_s"] == 8.0
    assert amendment["n_suspect"] == params["n_suspect"] == 1
    assert amendment["n_act"] == params["n_act"] == 2
    assert amendment["release_m"] == params["release_m"] == 3


def test_amendment_7_preserves_protected_r_set():
    timing = _load("phase6r_amendment_7.json")["content"]["timing_and_knowledge"]
    assert timing["labels_opened"] is False
    assert timing["r_set_acceptance_opened"] is False
    assert timing["R_S_read_for_diagnosis"] is False
