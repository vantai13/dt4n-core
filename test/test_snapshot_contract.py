#!/usr/bin/env python3
"""Input contract and differential fuzzing on malformed snapshots."""
from __future__ import annotations

import copy
import glob
import json
import math
import random

import pytest

from ml import campaign as C
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer, OnlineScorer
from ml.serve_fast import FastOnlineScorer
from ml.snapshot_contract import sanitize

CV = "v3-qdisc-ratevalid"
RAW = sorted(glob.glob(str(C.ROOT / "data/phase5/raw/*.jsonl")))
N_VARIANTS = 120


@pytest.fixture(scope="module")
def model():
    return EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")


@pytest.fixture(scope="module")
def cons():
    return ConservationLayer.load(
        C.ROOT / "results/report/phase6r_amendment_1.json"
    )


def _snapshots(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def base_snapshot():
    return _snapshots(RAW[0])[5]


@pytest.mark.parametrize(
    "prop,value",
    [
        ("rateValid", 1),
        ("rateValid", "true"),
        ("rateValid", None),
        ("qdiscValid", 0),
    ],
)
def test_non_bool_flag_becomes_false(prop, value):
    snapshot = base_snapshot()
    snapshot["things"]["link-s1-s2"]["features"]["traffic"][prop] = value
    clean, violations = sanitize(snapshot)
    assert clean["things"]["link-s1-s2"]["features"]["traffic"][prop] is False
    assert violations


@pytest.mark.parametrize(
    "value", ["1234.5", True, float("inf"), float("nan"), "abc", [1]]
)
def test_non_finite_or_non_number_measure_becomes_none(value):
    snapshot = base_snapshot()
    snapshot["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] = value
    clean, violations = sanitize(snapshot)
    assert clean["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] is None
    assert violations


def test_fabricated_loss_is_removed_not_crash():
    snapshot = base_snapshot()
    traffic = snapshot["things"]["link-s1-s2"]["features"]["traffic"]
    traffic["qdiscValid"], traffic["lossPct"] = False, 3.0
    clean, violations = sanitize(snapshot)
    assert clean["things"]["link-s1-s2"]["features"]["traffic"]["lossPct"] is None
    assert violations


def test_sanitize_never_mutates_input():
    snapshot = base_snapshot()
    snapshot["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] = "bad"
    before = copy.deepcopy(snapshot)
    sanitize(snapshot)
    assert snapshot == before


def test_collected_dataset_satisfies_contract():
    total = 0
    snapshots = 0
    for path in RAW:
        for snapshot in _snapshots(path):
            _, violations = sanitize(snapshot)
            total += len(violations)
            snapshots += 1
    assert snapshots == 1080
    assert total == 0


def test_violation_is_reported_in_reason(model):
    snapshots = _snapshots(RAW[0])
    scorer = OnlineScorer(
        model, expected_collector_version=CV, conservation_mode="off"
    )
    scorer.observe(snapshots[0])
    bad = copy.deepcopy(snapshots[1])
    bad["things"]["link-s1-s2"]["features"]["traffic"]["txRate"] = "oops"
    reading = scorer.observe(bad)
    assert reading.n_contract_violations == 1
    assert "input contract" in reading.reason
    assert reading.status == "unknown"


def mutate(rng, snapshot):
    output = copy.deepcopy(snapshot)
    for _ in range(rng.randint(1, 4)):
        thing_id = rng.choice(list(output["things"]))
        features = output["things"][thing_id]["features"]
        traffic = features.get("traffic", {})
        status = features.get("status", {})
        operation = rng.randrange(10)
        if operation == 0:
            del output["things"][thing_id]
        elif operation == 1 and traffic:
            traffic["rateValid"] = rng.choice([False, None, 0, 1, "true"])
        elif operation == 2 and traffic:
            traffic["qdiscValid"] = rng.choice([False, 0, None])
        elif operation == 3 and traffic:
            traffic["lossPct"] = rng.choice(
                [None, 0.0, 5.0, "3.5", float("nan")]
            )
        elif operation == 4 and status:
            status["state"] = rng.choice(["down", "up", "unknown", None, "UP"])
        elif operation == 5 and traffic:
            traffic["txRate"] = rng.choice(
                [None, "abc", 1e12, -5.0, "1234.5", True, float("inf")]
            )
        elif operation == 6 and traffic and isinstance(
            traffic.get("rxRate"), (int, float)
        ):
            traffic["rxRate"] = traffic["rxRate"] * rng.uniform(0, 3)
        elif operation == 7 and traffic:
            traffic["qdiscSentDelta"] = rng.choice([None, 10**7, 0, "7"])
        elif operation == 8 and traffic:
            traffic.pop("lossPct", None)
        elif operation == 9:
            features.pop("status", None)
    return output


def difference(left, right):
    for key, value in vars(left).items():
        other = getattr(right, key)
        if not (
            value == other
            or (
                isinstance(value, float)
                and isinstance(other, float)
                and math.isnan(value)
                and math.isnan(other)
            )
        ):
            return key
    return None


def test_fast_equals_reference_on_fuzzed_inputs(model, cons):
    rng = random.Random(20260917)
    for _ in range(N_VARIANTS):
        path = rng.choice(RAW)
        snapshots = _snapshots(path)
        index = rng.randrange(1, len(snapshots))
        variant = mutate(rng, snapshots[index])
        mode = rng.choice(["shadow", "active"])
        readings = []
        for scorer_class in (OnlineScorer, FastOnlineScorer):
            scorer = scorer_class(
                model,
                expected_collector_version=CV,
                conservation=cons,
                conservation_mode=mode,
            )
            scorer.observe(snapshots[index - 1])
            readings.append(scorer.observe(variant))
        diff = difference(*readings)
        assert diff is None, (
            "%s tick %d mode %s: truong %s ref=%r fast=%r"
            % (
                path[-30:],
                index,
                mode,
                diff,
                getattr(readings[0], diff),
                getattr(readings[1], diff),
            )
        )
