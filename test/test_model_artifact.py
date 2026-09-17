#!/usr/bin/env python3
"""Contract tests for models/envelope-1.0.0.json."""
from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from ml import campaign as C
from ml.model import ArtifactError, EnvelopeModel


ART = C.ROOT / "models/envelope-1.0.0.json"
TICKS = C.ROOT / "results/report/phase6_envelope_ticks.csv"
RAW = C.ROOT / "data/phase5/raw"

pytestmark = pytest.mark.skipif(
    not ART.exists(), reason="Lesson 6R.2 chua sinh artifact"
)


@pytest.fixture(scope="module")
def model():
    return EnvelopeModel.load(ART)


@pytest.fixture(scope="module")
def content():
    return json.loads(ART.read_text(encoding="utf-8"))["content"]


@pytest.fixture(scope="module")
def ticks():
    # The receipt was written with round-trip-safe float strings.  Pandas'
    # default fast parser rounds 28 excess values by up to 4.55e-13; request
    # the round-trip parser so Tier B checks the stored float bits, not parser
    # approximation.
    return pd.read_csv(TICKS, float_precision="round_trip")


def write_variant(content, tmp_path, *, rehash=True, original_hash=None):
    digest = (
        C.sha256_bytes(C.canonical_json(content).encode("utf-8"))
        if rehash
        else original_hash
    )
    path = tmp_path / "variant.json"
    path.write_text(
        json.dumps({"content": content, "content_sha256": digest}),
        encoding="utf-8",
    )
    return path


def test_load_needs_no_data_directory(model):
    assert len(model.columns) == 71
    assert model.version == "envelope-1.0.0"
    assert model.thresholds["primary"]["E"] == 8.968806422101116
    assert model.thresholds["primary"]["K"] == 31


def test_version_matches_filename(content):
    assert content["version"] == ART.stem


def test_feature_spec_declares_stateless(content):
    feature_spec = content["feature_spec"]
    assert feature_spec["uses_delta"] is False
    assert feature_spec["delta_columns"] == []
    assert feature_spec["warmup_ticks_required"] == 0
    assert feature_spec["link_stats_mode"] == "frozen"
    assert not any(column.startswith("d1.") for column in content["columns"])


def test_link_stats_present_and_complete(content):
    stats = content["link_stats"]
    assert len(stats) == 16
    for column, values in stats.items():
        assert column.startswith("link-")
        assert column.endswith((".traffic.rxRate", ".traffic.txRate"))
        assert np.isfinite(values["mean"]) and values["std"] > 0


def test_families_partition_the_columns(content):
    families = content["families"]
    columns = set(content["columns"])
    assert len(families["indicator"]) == 35
    assert len(families["rate_shared"]) == 36
    assert not set(families["indicator"]) & set(families["rate_shared"])
    assert set(families["indicator"]) | set(families["rate_shared"]) == columns
    assert len(families["loss_only"]) == 8
    assert all(
        column.endswith(".traffic.lossPct") for column in families["loss_only"]
    )


def test_provenance_points_at_live_artifacts(content):
    provenance = content["provenance"]
    report = C.ROOT / "results/report"
    assert provenance["manifest_sha256"] == C.sha256_file(
        report / "ml_dataset_split_manifest.json"
    )
    assert provenance["phase6_ticks_csv_sha256"] == C.sha256_file(
        report / "phase6_envelope_ticks.csv"
    )
    for name, key in (
        ("phase6_envelope_cv.json", "cv_content_sha256"),
        ("phase6_envelope.json", "phase6_envelope_content_sha256"),
        ("phase6r_slo.json", "slo_content_sha256"),
    ):
        doc = json.loads((report / name).read_text(encoding="utf-8"))
        assert provenance[key] == doc["content_sha256"], name


def test_tier_a_suspect_bit_exact(model, ticks):
    got = model.suspect_from(
        ticks.excess.to_numpy(), ticks.judgeable71.to_numpy(dtype=bool)
    )
    want = ticks.alarm_secondary_excess.to_numpy(dtype=bool)
    bad = np.flatnonzero(got != want)
    assert len(bad) == 0, "lech tai %s" % ticks.iloc[bad[:5]][
        ["run_id", "tick"]
    ].to_dict("records")
    assert len(got) == 590


def test_tier_a_act_bit_exact(model, ticks):
    got = model.act_from(
        ticks.k_ind.to_numpy(),
        ticks.k_rate.to_numpy(),
        ticks.judgeable71.to_numpy(dtype=bool),
    )
    want = ticks.alarm_secondary_dual.to_numpy(dtype=bool)
    assert (got == want).all() and len(got) == 590


def test_threshold_comparison_is_strictly_greater(model):
    threshold = model.thresholds["primary"]["E"]
    assert not model.suspect_from(np.array([threshold]), np.array([True]))[0]
    assert model.suspect_from(
        np.array([np.nextafter(threshold, np.inf)]), np.array([True])
    )[0]


def test_unknown_never_alarms(model, ticks):
    unknown = ~ticks.judgeable71.to_numpy(dtype=bool)
    assert unknown.sum() == 8
    got = model.suspect_from(
        ticks.excess.to_numpy(), ticks.judgeable71.to_numpy(dtype=bool)
    )
    assert not got[unknown].any()


def test_one_byte_change_is_detected(content, tmp_path):
    original_hash = json.loads(ART.read_text(encoding="utf-8"))["content_sha256"]
    bad = copy.deepcopy(content)
    bad["bounds"][content["columns"][0]]["max"] = 1e9
    with pytest.raises(ArtifactError, match="content_sha256 lech"):
        EnvelopeModel.load(
            write_variant(
                bad, tmp_path, rehash=False, original_hash=original_hash
            )
        )


def test_column_reorder_is_detected(content, tmp_path):
    original_hash = json.loads(ART.read_text(encoding="utf-8"))["content_sha256"]
    bad = copy.deepcopy(content)
    bad["columns"] = list(reversed(bad["columns"]))
    bad["families"]["primary"] = bad["columns"]
    with pytest.raises(ArtifactError, match="content_sha256 lech"):
        EnvelopeModel.load(
            write_variant(
                bad, tmp_path, rehash=False, original_hash=original_hash
            )
        )


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("thieu khoa", lambda content: content.pop("link_stats")),
        (
            "schema version la",
            lambda content: content.__setitem__(
                "schema_version", "DT4N-ENV-ARTIFACT-0"
            ),
        ),
        (
            "version khong semver",
            lambda content: content.__setitem__("version", "envelope-v1"),
        ),
        (
            "thieu bounds",
            lambda content: content["bounds"].pop(content["columns"][0]),
        ),
        (
            "thua bounds",
            lambda content: content["bounds"].__setitem__(
                "fake.column", {"min": 0.0, "max": 1.0}
            ),
        ),
        (
            "bounds nghich",
            lambda content: content["bounds"].__setitem__(
                content["columns"][3], {"min": 9.0, "max": 1.0}
            ),
        ),
        (
            "ho giao nhau",
            lambda content: content["families"]["rate_shared"].append(
                content["families"]["indicator"][0]
            ),
        ),
        (
            "primary khong khop columns",
            lambda content: content["families"].__setitem__(
                "primary", content["columns"][:-1]
            ),
        ),
        (
            "ho thieu nguong",
            lambda content: content["thresholds"].pop("indicator"),
        ),
    ],
)
def test_schema_guard_rejects(content, tmp_path, name, mutate):
    bad = copy.deepcopy(content)
    mutate(bad)
    with pytest.raises(ArtifactError):
        EnvelopeModel.load(write_variant(bad, tmp_path))


def test_not_an_artifact_is_rejected(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"E": 8.9688}', encoding="utf-8")
    with pytest.raises(ArtifactError, match="khong phai artifact"):
        EnvelopeModel.load(path)


def test_input_missing_column_is_rejected(model):
    frame = pd.DataFrame(np.zeros((3, 71)), columns=model.columns)
    with pytest.raises(ArtifactError, match="dau vao thieu"):
        model.score_batch(frame.drop(columns=[model.columns[0]]))


def test_input_extra_columns_are_ignored_not_rejected(model):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame(rng.normal(size=(5, 71)), columns=model.columns)
    extended = frame.assign(run_id="r", tick=range(5), some_string="abc")
    assert np.array_equal(model.score_batch(frame).k, model.score_batch(extended).k)


def test_input_column_order_does_not_change_result(model):
    rng = np.random.default_rng(11)
    frame = pd.DataFrame(rng.normal(size=(20, 71)), columns=model.columns)
    shuffled = list(model.columns)
    rng.shuffle(shuffled)
    original = model.score_batch(frame)
    reordered = model.score_batch(frame[shuffled])
    assert np.array_equal(original.k, reordered.k)
    assert np.array_equal(original.excess, reordered.excess)
    assert np.array_equal(original.judgeable, reordered.judgeable)


def test_nan_row_is_unknown_and_silent(model):
    frame = pd.DataFrame(np.zeros((2, 71)), columns=model.columns)
    frame.iloc[1, 5] = np.nan
    decision = model.score_batch(frame)
    assert decision.judgeable[0] and not decision.judgeable[1]
    assert not decision.suspect[1] and not decision.act[1]


def test_load_does_not_refit(model, content):
    assert model.bounds == content["bounds"]
    assert model.content_sha256 == json.loads(ART.read_text(encoding="utf-8"))[
        "content_sha256"
    ]


raw_ok = len(list(RAW.glob("*.jsonl"))) == 18


@pytest.mark.skipif(
    not raw_ok,
    reason="thieu 18 raw JSONL; scoring-layer equivalence khong kiem duoc",
)
def test_tier_b_scoring_layer_bit_exact(model, ticks):
    from ml.dataset import load_split

    decision = model.score_batch(load_split().X_test_envelope)
    assert (decision.k == ticks.k.to_numpy()).all()
    assert (decision.k_indicator == ticks.k_ind.to_numpy()).all()
    assert (decision.k_rate == ticks.k_rate.to_numpy()).all()
    assert (
        decision.judgeable == ticks.judgeable71.to_numpy(dtype=bool)
    ).all()
    assert float(
        np.max(np.abs(decision.excess - ticks.excess.to_numpy()))
    ) == 0.0
