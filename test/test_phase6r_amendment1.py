#!/usr/bin/env python3
"""Integrity and derivation tests for Phase 6R amendment 1."""
from __future__ import annotations

import inspect
import json

import numpy as np
import pandas as pd
import pytest

from ml import campaign as C
from ml import conservation as K
from scripts import build_phase6r_amendment1 as B
from twin.link_direction import UPSTREAM_OF_CORE


DOC = C.ROOT / "results/report/phase6r_amendment_1.json"
SWITCHES = ["s1", "s2", "s3"]


def balanced_frame(n=3, scale=1.0):
    upstream = {
        "h1-s1": 268e3,
        "h2-s1": 268e3,
        "h3-s1": 268e3,
        "s1-s2": 536e3,
        "s1-s3": 268e3,
        "s2-s3": 270e3,
        "s2-srv1": 536e3,
        "s3-srv2": 538e3,
    }
    downstream = {
        "h1-s1": 6e3,
        "h2-s1": 6e3,
        "h3-s1": 6e3,
        "s1-s2": 12e3,
        "s1-s3": 6e3,
        "s2-s3": 0.0,
        "s2-srv1": 282e3,
        "s3-srv2": 6e3,
    }
    row = {}
    for key in UPSTREAM_OF_CORE:
        row[K.link_column(key, "txRate")] = upstream[key] * scale
        row[K.link_column(key, "rxRate")] = downstream[key] * scale
    return pd.DataFrame([row] * n)


@pytest.fixture(scope="module")
def inc():
    return K.incidence(UPSTREAM_OF_CORE, SWITCHES)


def test_balanced_network_has_zero_residual(inc):
    result = K.residuals(balanced_frame(), inc)
    assert result["judgeable"].all()
    assert np.allclose(
        result[["r.s1", "r.s2", "r.s3"]].to_numpy(), 0.0, atol=1e-12
    )


def test_residual_is_load_invariant(inc):
    low = K.residuals(balanced_frame(scale=1.0), inc)
    high = K.residuals(balanced_frame(scale=4.0), inc)
    assert np.allclose(
        low[["r.s1", "r.s2", "r.s3"]], high[["r.s1", "r.s2", "r.s3"]], atol=1e-12
    )


def test_drop_on_s1_s2_egress_localizes_to_s1(inc):
    frame = balanced_frame()
    frame[K.link_column("s1-s2", "txRate")] -= 120e3
    result = K.residuals(frame, inc)
    assert (result["argmax_switch"] == "s1").all()
    assert result["r.s1"].iloc[0] == pytest.approx(
        120e3 / (804e3 + 12e3 + 6e3)
    )
    assert K.alarm(result, 0.0797).all()


def test_nan_is_unknown_never_normal(inc):
    frame = balanced_frame()
    frame.loc[1, K.link_column("s2-s3", "rxRate")] = np.nan
    result = K.residuals(frame, inc)
    assert result["judgeable"].tolist() == [True, False, True]
    assert not K.alarm(result, -1.0)[1]


def test_missing_column_is_rejected_not_filled(inc):
    frame = balanced_frame().drop(columns=[K.link_column("s1-s3", "txRate")])
    with pytest.raises(ValueError):
        K.residuals(frame, inc)


def test_negative_residual_alone_never_alarms(inc):
    frame = balanced_frame()
    for key in ("h1-s1", "h2-s1", "h3-s1"):
        frame[K.link_column(key, "txRate")] *= 0.5
    result = K.residuals(frame, inc)
    assert (result["r.s1"] < 0).all()
    assert not K.alarm(result, 0.0797).any()


def test_single_counter_error_gives_paired_signature(inc):
    frame = balanced_frame()
    frame[K.link_column("s1-s2", "txRate")] += 300e3
    result = K.residuals(frame, inc)
    assert (result["r.s1"] < 0).all() and (result["r.s2"] > 0).all()
    assert (result["argmax_switch"] == "s2").all()
    assert K.alarm(result, 0.0797).all()


def test_floor_prevents_blowup_on_idle_switch(inc):
    frame = balanced_frame(scale=0.0)
    frame[K.link_column("s1-s2", "rxRate")] = 5.0
    result = K.residuals(frame, inc)
    assert result["r_max"].abs().max() <= 5.0 / K.RATE_FLOOR_BPS


def test_residual_is_row_local_so_loco_equals_in_sample(inc):
    frame = balanced_frame(n=6)
    frame[K.link_column("s1-s2", "txRate")] *= np.linspace(0.7, 1.0, 6)
    full = K.residuals(frame, inc)["r_max"]
    shuffled = K.residuals(
        frame.sample(frac=1.0, random_state=0), inc
    )["r_max"]
    subset = K.residuals(frame.iloc[2:4], inc)["r_max"]
    assert full.equals(shuffled.sort_index())
    assert full.iloc[2:4].equals(subset)


def test_flipped_direction_is_caught_by_median_guard():
    flipped = dict(UPSTREAM_OF_CORE)
    upstream, downstream = flipped["s1-s2"]
    flipped["s1-s2"] = (downstream, upstream)
    result = K.residuals(
        balanced_frame(), K.incidence(flipped, SWITCHES)
    )
    assert result["r.s1"].abs().median() > 0.005


def test_saturation_ratio_matches_linkdegrade_floor():
    assert K.saturation_ratio(125e3, 5.0, 0.95) == pytest.approx(1.0)
    assert K.saturation_ratio(537540.755, 20.0, 0.8275) == pytest.approx(
        1.246, abs=1e-3
    )


def test_builder_source_never_touches_test_split():
    source = inspect.getsource(B)
    for forbidden in (
        "X_test",
        "y_test",
        "test_row_keys",
        "split']['test'",
        "eval_primary]",
    ):
        assert forbidden not in source, forbidden


def test_sealed_r_d_design_has_duplicate_doses():
    collisions = B.sealed_design_collisions()
    assert collisions["s2-s3"]["n_distinct_doses"] == 3


pytestmark_doc = pytest.mark.skipif(
    not DOC.exists(), reason="amendment 1 chua build"
)


@pytest.fixture(scope="module")
def doc():
    return json.loads(DOC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def content(doc):
    return doc["content"]


@pytestmark_doc
def test_content_hash_matches(doc):
    assert doc["content_sha256"] == C.sha256_bytes(
        C.canonical_json(doc["content"]).encode("utf-8")
    )
    assert "written_at_utc" not in doc["content"]


@pytestmark_doc
def test_pinned_artifacts_have_not_drifted(content):
    for rel, sha in content["pinned_artifacts_sha256"].items():
        assert C.sha256_file(C.ROOT / rel) == sha, rel


@pytestmark_doc
def test_bound_to_sealed_slo(content):
    slo = json.loads(
        (C.ROOT / "results/report/phase6r_slo.json").read_text(encoding="utf-8")
    )
    assert content["amends"]["slo_content_sha256"] == slo["content_sha256"]


@pytestmark_doc
def test_threshold_recomputes_from_train_only(content):
    calibration = B.calibrate(B.train_frame_with_keys())
    assert calibration["R"] == content["calibration"]["R"]
    assert calibration["owner"] == content["calibration"]["owner"]


@pytestmark_doc
def test_disclosure_limits_confirmatory_scope(content):
    disclosure = content["knowledge_disclosure"]
    assert disclosure["r_campaign_collected"] is False
    assert "post-hoc" in disclosure["origin"]
    assert "degrade" in content["prediction"]["scope"]
    assert any("admin_down" in item for item in content["forbidden"])


@pytestmark_doc
def test_refutation_and_outcomes_are_complete(content):
    assert {
        "F1_sensitivity",
        "F2_specificity_mechanism",
        "F3_background",
        "F4_localization",
        "F5_incremental_value",
        "F6_slo",
    } <= set(content["refutation"])
    assert content["combination"]["act"].startswith("khong doi")


@pytestmark_doc
def test_prediction_bands_do_not_overlap_and_design_avoids_band(content):
    prediction = content["prediction"]
    assert prediction["rho_silent"] < prediction["rho_detect"]
    for row in prediction["illustrative_table_using_prior"]:
        assert row["expected_prior"] != "no_prediction"
        assert row["new_bw_mbps"] > B.BW_FLOOR_MBPS
