"""Phan quyet 6R.7 phai suy duoc tu receipt niem phong, khong ai go tay."""
import json

from ml import campaign as C

REPORT = C.ROOT / "results/report"


def _load(name):
    doc = json.loads((REPORT / name).read_text(encoding="utf-8"))
    assert doc["content_sha256"] == C.sha256_bytes(
        C.canonical_json(doc["content"]).encode()
    )
    return doc


def test_verdicts_bound_to_sealed_receipts():
    verdicts = _load("phase6r_verdicts.json")["content"]["derived_from"]
    assert verdicts["slo_content_sha256"] == _load("phase6r_slo.json")["content_sha256"]
    assert verdicts["acceptance_content_sha256"] == _load("phase6r_acceptance.json")["content_sha256"]
    assert verdicts["stability_v2_content_sha256"] == _load("phase6r_stability_v2.json")["content_sha256"]


def test_s1_fail_is_recorded_on_the_registered_channel():
    s1 = _load("phase6r_verdicts.json")["content"]["slo"]["S1"]
    acc = _load("phase6r_acceptance.json")["content"]["S1_S4"]["envelope_only"]["summary"]
    assert s1["registered_channel"] == "envelope_only"
    assert s1["value"] == acc["detection_rate"]
    assert (s1["verdict"] == "PASS") == (acc["detection_rate"] >= 0.875)


def test_combined_s4_is_not_reported_as_pass():
    s4 = _load("phase6r_verdicts.json")["content"]["slo"]["S4"]
    assert s4["registered_channel"] == "envelope_only"
    assert s4["combined_meets_target"] is (s4["combined_value_ms"] <= 3000)
