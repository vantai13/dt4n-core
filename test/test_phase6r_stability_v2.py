import json

from ml import campaign as C


REPORT = C.ROOT / "results/report"


def load_sealed(name):
    document = json.loads((REPORT / name).read_text())
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    )
    return document


def test_v2_preserves_and_pins_v1_history():
    v2 = load_sealed("phase6r_stability_v2.json")["content"]
    v1 = load_sealed("phase6r_stability.json")
    link = v2["supersedes_for_release_decisions"]
    assert link["content_sha256"] == v1["content_sha256"]
    assert link["file_sha256"] == C.sha256_file(REPORT / "phase6r_stability.json")
    assert link["history_preserved"] is True


def test_s11_requires_zero_act_and_positive_mechanism_evidence():
    receipt = load_sealed("phase6r_replay_o3_v2.json")["content"]
    assert receipt["verdict"] == "PASS"
    assert receipt["measurement_number"] == 2
    assert receipt["thresholds_changed"] is False
    assert receipt["extra_runs_collected"] is False
    for result in receipt["runs"].values():
        assert result["n_act_entries_in_suppression_window"] == 0
        assert result["n_suppressed_ticks"] > 0
        assert result["passed"] is True


def test_latency_v2_corrects_only_cold_semantics():
    latency = load_sealed("phase6r_latency_v2.json")["content"]
    assert latency["S5_verdict_changed"] is False
    assert latency["verdict"] == {"OnlineScorer": "FAIL", "FastOnlineScorer": "PASS"}
    for result in latency["per_implementation"].values():
        assert "first scored tick" in result["cold_start_definition"]
        assert result["max_ms"] >= result["p99_ms"] >= result["p95_ms"] >= result["p50_ms"]


def test_v2_integrity_and_release_gate():
    content = load_sealed("phase6r_stability_v2.json")["content"]
    for name, expected in content["implementation_sha256"].items():
        assert C.sha256_file(C.ROOT / name) == expected
    for name, expected in content["evidence_file_sha256"].items():
        assert C.sha256_file(REPORT / name) == expected
    assert content["closed_here"]["S11"]["verdict"] == "PASS"
    assert content["release_gates"]["phase8_release_blocked"] is True
    assert content["labels_opened"] is False
    assert content["r_set_acceptance_opened"] is False
