import json

from ml import campaign as C
from ml.replay_guard import R_O1_FIELDS, R_O2_FIELDS


REPORT = C.ROOT / "results/report"


def _load(name):
    document = json.loads((REPORT / name).read_text())
    digest = C.sha256_bytes(C.canonical_json(document["content"]).encode())
    assert digest == document["content_sha256"]
    return document


def test_boolean_receipts_have_no_leakage_fields():
    restart = _load("phase6r_replay_o1.json")["content"]
    gap = _load("phase6r_replay_o2.json")["content"]
    assert tuple(restart) == R_O1_FIELDS
    assert tuple(gap) == R_O2_FIELDS
    assert all(type(value) is bool for value in restart.values())
    assert all(type(value) is bool for value in gap.values())


def test_stability_receipt_pins_prereg_and_evidence():
    stability = _load("phase6r_stability.json")["content"]
    prereg = _load("phase6r_stability_prereg.json")
    assert stability["prereg_content_sha256"] == prereg["content_sha256"]
    for name, expected in stability["evidence_file_sha256"].items():
        assert C.sha256_file(REPORT / name) == expected
    for name, expected in stability["implementation_sha256"].items():
        assert C.sha256_file(C.ROOT / name) == expected
    assert C.sha256_file(REPORT / stability["plot"]["file"]) == stability["plot"]["file_sha256"]
    assert stability["labels_opened"] is False
    assert stability["r_set_acceptance_opened"] is False


def test_closed_verdicts_are_derived_from_evidence():
    stability = _load("phase6r_stability.json")["content"]["closed_here"]
    latency = _load("phase6r_latency.json")["content"]
    soak = _load("phase6r_soak.json")["content"]
    restart = _load("phase6r_replay_o1.json")["content"]
    gap = _load("phase6r_replay_o2.json")["content"]
    controller = _load("phase6r_replay_o3.json")["content"]
    assert stability["S5"]["verdict"] == latency["verdict"]["FastOnlineScorer"]
    assert stability["S6"]["verdict"] == soak["verdict"]
    assert stability["S8"]["verdict"] == ("PASS" if gap["passed"] else "FAIL")
    assert stability["S9"]["verdict"] == ("PASS" if restart["passed"] else "FAIL")
    assert stability["S11"]["verdict"] == controller["verdict"]
