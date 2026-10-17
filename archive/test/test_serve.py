#!/usr/bin/env python3
"""OnlineScorer delivery, unknown, freezing, and equivalence tests."""
from __future__ import annotations

import copy
import inspect
import json

import pytest

from ml import campaign as C
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer, OnlineScorer, _State
from ml.serve_fast import FastOnlineScorer
from scripts import build_phase6r_equivalence as EQ

ART = C.ROOT / "models/envelope-1.0.0.json"
AMEND = C.ROOT / "results/report/phase6r_amendment_1.json"
RAW = C.ROOT / "data/phase5/raw/N-load2M-s1003-r1.jsonl"
RECEIPT = C.ROOT / "results/report/phase6r_equivalence.json"
CV = "v3-qdisc-ratevalid"


@pytest.fixture(scope="module")
def model():
    return EnvelopeModel.load(ART)


@pytest.fixture(scope="module")
def cons():
    return ConservationLayer.load(AMEND)


@pytest.fixture(scope="module")
def snaps():
    return [
        json.loads(line)
        for line in RAW.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def fresh(model, cons=None, mode="off"):
    return OnlineScorer(
        model,
        expected_collector_version=CV,
        conservation=cons,
        conservation_mode=mode,
    )


def primed(model, snaps, cons=None, mode="off"):
    scorer = fresh(model, cons, mode)
    assert scorer.observe(snaps[0]).status == "warming_up"
    return scorer


def test_first_snapshot_is_warming_up_not_silent(model, snaps):
    reading = fresh(model).observe(snaps[0])
    assert reading.status == "warming_up" and reading.reason
    assert not reading.suspect and not reading.act


def test_second_snapshot_of_normal_run_is_scored_normal(model, snaps):
    reading = primed(model, snaps).observe(snaps[1])
    assert reading.status == "scored" and reading.judgeable
    assert not reading.suspect and not reading.act and reading.reason == ""


def test_gap_makes_unknown_not_normal(model, snaps):
    scorer = primed(model, snaps)
    reading = scorer.observe(copy.deepcopy(snaps[3]))
    assert reading.status == "unknown" and "khoang" in reading.reason
    assert not reading.suspect and not reading.judgeable
    assert scorer.observe(snaps[4]).status == "scored"


def test_too_short_interval_is_unknown(model, snaps):
    scorer = primed(model, snaps)
    early = copy.deepcopy(snaps[1])
    early["t_source"] = snaps[0]["t_source"] + 0.2
    assert scorer.observe(early).status == "unknown"


def test_out_of_order_rejected_and_state_unchanged(model, snaps):
    scorer = primed(model, snaps)
    scorer.observe(snaps[2])
    before = copy.copy(scorer._s.__dict__)
    reading = scorer.observe(snaps[1])
    assert reading.status == "rejected" and "sai thu tu" in reading.reason
    after = scorer._s.__dict__
    keys = ("n_accepted", "last_t", "last_digest")
    assert {key: after[key] for key in keys} == {key: before[key] for key in keys}
    assert after["n_rejected"] == before["n_rejected"] + 1


def test_duplicate_is_idempotent(model, snaps):
    scorer = primed(model, snaps)
    first = scorer.observe(snaps[1])
    accepted = scorer._s.n_accepted
    again = scorer.observe(copy.deepcopy(snaps[1]))
    assert again == first and scorer._s.n_accepted == accepted


def test_same_time_different_content_is_rejected(model, snaps):
    scorer = primed(model, snaps)
    scorer.observe(snaps[1])
    forged = copy.deepcopy(snaps[1])
    forged["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] = 1.0
    assert scorer.observe(forged).status == "rejected"


def test_missing_t_source_is_rejected(model, snaps):
    bad = copy.deepcopy(snaps[1])
    del bad["t_source"]
    assert fresh(model).observe(bad).status == "rejected"


def test_invalid_qdisc_gives_unknown(model, snaps):
    scorer = primed(model, snaps)
    snapshot = copy.deepcopy(snaps[1])
    traffic = snapshot["things"]["link-s2-s3"]["features"]["traffic"]
    traffic["qdiscValid"], traffic["lossPct"] = False, None
    reading = scorer.observe(snapshot)
    assert reading.status == "unknown" and not reading.judgeable
    assert not reading.suspect and reading.reason


def test_invalid_rate_flag_masks_fabricated_rate(model, snaps):
    """Synthetic branch absent from the 1062 historical replay rows."""
    scorer = primed(model, snaps)
    snapshot = copy.deepcopy(snaps[1])
    traffic = snapshot["things"]["link-h2-s1"]["features"]["traffic"]
    traffic["rateValid"], traffic["rxRate"], traffic["txRate"] = False, 0.0, 0.0
    reading = scorer.observe(snapshot)
    assert reading.status == "unknown" and not reading.judgeable


def test_absent_thing_gives_unknown_without_crash(model, snaps):
    scorer = primed(model, snaps)
    snapshot = copy.deepcopy(snaps[1])
    del snapshot["things"]["host-srv2"]
    reading = scorer.observe(snapshot)
    assert reading.status == "unknown" and reading.n_missing_columns == 3
    assert "vang mat" in reading.reason


def test_collector_version_mismatch_is_unknown(model, snaps):
    scorer = primed(model, snaps)
    snapshot = copy.deepcopy(snaps[1])
    snapshot["run"]["collector_version"] = "v4-with-backlog"
    reading = scorer.observe(snapshot)
    assert reading.status == "unknown" and "collector_version" in reading.reason


def test_link_down_triggers_act_with_reason(model, snaps):
    scorer = primed(model, snaps)
    snapshot = copy.deepcopy(snaps[1])
    snapshot["things"]["link-s1-s2"]["features"]["status"]["state"] = "down"
    reading = scorer.observe(snapshot)
    assert reading.status == "scored" and reading.act and "act" in reading.reason


def test_link_stats_come_only_from_artifact(model, snaps):
    stats = copy.deepcopy(model.link_stats)
    scorer = primed(model, snaps)
    for index, snapshot in enumerate(snaps[1:40]):
        boosted = copy.deepcopy(snapshot)
        boosted["things"]["link-h1-s1"]["features"]["traffic"]["txRate"] = 1e9 * (index + 1)
        scorer.observe(boosted)
    assert model.link_stats == stats
    frame = scorer.frame_of(snaps[5])
    column = "link-h1-s1.traffic.txRate"
    z_score = abs(frame[column].iloc[0] - stats[column]["mean"]) / stats[column]["std"]
    assert frame["agg.rate_absz_max"].iloc[0] >= z_score


def test_scorer_state_is_constant_size_no_window(model, snaps):
    scorer = primed(model, snaps)
    for snapshot in snaps[1:]:
        scorer.observe(snapshot)
    assert set(vars(scorer._s)) == set(vars(_State()))
    assert all(
        not isinstance(value, (list, dict))
        for value in vars(scorer._s).values()
        if value is not None and not hasattr(value, "status")
    )


def test_model_declares_no_delta(model):
    spec = model._c["feature_spec"]
    assert spec["uses_delta"] is False and spec["uses_rolling"] is False


def test_shared_scorer_across_runs_breaks_equivalence(model):
    scorer = fresh(model)
    first_run = [json.loads(line) for line in RAW.read_text().splitlines()]
    other_path = C.ROOT / "data/phase5/raw/N-load2M-s1004-r2.jsonl"
    second_run = [json.loads(line) for line in other_path.read_text().splitlines()]
    first, second = (
        (first_run, second_run)
        if first_run[0]["t_source"] < second_run[0]["t_source"]
        else (second_run, first_run)
    )
    for snapshot in first:
        scorer.observe(snapshot)
    assert scorer.observe(second[0]).status != "warming_up"


def test_conservation_shadow_never_changes_suspect(model, cons, snaps):
    snapshot = copy.deepcopy(snaps[1])
    snapshot["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] *= 0.7
    shadow = primed(model, snaps, cons, "shadow").observe(snapshot)
    active = primed(model, snaps, cons, "active").observe(snapshot)
    assert shadow.cons_alarm and active.cons_alarm and shadow.cons_switch == "s1"
    assert shadow.suspect == shadow.envelope_suspect
    assert active.suspect and "residual active" in active.reason


def test_equivalence_functions_never_touch_labels():
    forbidden = {"y_test", "eval_primary", "eval_sensitivity", "is_fault", "y"}
    for function in (EQ.batch_reference, EQ.online_replay, EQ.compare):
        names = set(function.__code__.co_names) | set(function.__code__.co_varnames)
        assert not names & forbidden, function.__name__
        assert "y" not in inspect.signature(function).parameters


def test_fast_policy_matches_reference_on_synthetic_branches(model, cons, snaps):
    variants = [copy.deepcopy(snaps[1]) for _ in range(4)]
    variants[1]["things"]["link-s2-s3"]["features"]["traffic"].update(
        {"qdiscValid": False, "lossPct": None}
    )
    variants[2]["things"]["link-h2-s1"]["features"]["traffic"].update(
        {"rateValid": False, "rxRate": 0.0, "txRate": 0.0}
    )
    del variants[3]["things"]["host-srv2"]
    # Use fresh scorers because variants intentionally reuse the same base tick.
    for snapshot in variants:
        ref = primed(model, snaps, cons, "shadow").observe(snapshot)
        candidate = FastOnlineScorer(
            model,
            expected_collector_version=CV,
            conservation=cons,
            conservation_mode="shadow",
        )
        candidate.observe(snaps[0])
        got = candidate.observe(snapshot)
        assert got == ref


@pytest.mark.skipif(not RECEIPT.exists(), reason="chua chay build_phase6r_equivalence")
def test_receipt_is_complete_and_bit_exact():
    document = json.loads(RECEIPT.read_text(encoding="utf-8"))
    content = document["content"]
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(content).encode("utf-8")
    )
    equivalence = content["equivalence"]
    assert equivalence["n_rows"] == equivalence["n_match"] == 1062
    assert all(value == 1062 for value in equivalence["per_field_match"].values())
    assert len(equivalence["by_run"]) == 18
    assert all(row["match"] == row["rows"] == 59 for row in equivalence["by_run"].values())
    assert content["timing"]["statuses"] == {
        "warming_up": 18,
        "scored": 1054,
        "unknown": 8,
    }
    assert content["labels_read"] is False
    assert content["artifact_sha256"] == EnvelopeModel.load(ART).content_sha256
    for relative, digest in content["code_sha256"].items():
        assert C.sha256_file(C.ROOT / relative) == digest, (
            "code da doi sau receipt: " + relative
        )
    fast = content["fast_equivalence"]
    assert fast["n_rows"] == fast["n_match"] == 1062
    assert all(value == 1062 for value in fast["per_field_match"].values())
