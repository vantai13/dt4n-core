#!/usr/bin/env python3
"""Phase 7.1: tính toàn vẹn prereg, firewall và hành vi guard."""
from __future__ import annotations

import inspect
import json

import pytest

from ml import campaign as C
from ml import operating_range as O


PREREG = C.ROOT / "results/report/phase7_prereg.json"
TRAIN = [C.ROOT / O.TRAIN_DIR / (run_id + ".jsonl") for run_id in O.TRAIN_RUN_IDS]


def snap(*client_mbps, valid=True):
    things = {}
    for index, mbps in enumerate(client_mbps, 1):
        things["host-h%d" % index] = {
            "attributes": {"type": "host", "role": "client"},
            "features": {
                "traffic": {
                    "txRate": mbps * 1e6 / 8,
                    "rateValid": valid,
                }
            },
        }
    things["host-srv1"] = {
        "attributes": {"type": "host", "role": "server"},
        "features": {"traffic": {"txRate": 99e6, "rateValid": True}},
    }
    return {"things": things}


def test_g_is_min_of_clients_and_ignores_servers():
    assert O.g(snap(2, 8, 3)) == pytest.approx(2)


def test_single_source_flood_does_not_raise_g():
    assert O.g(snap(20, 2, 2)) == pytest.approx(2)


def test_invalid_rate_is_none_not_zero():
    assert O.g(snap(2, 2, 2, valid=False)) is None


def test_threshold_refuses_rset_path():
    bad = C.ROOT / "data/phase6r/raw/RN-load8M-s4013-r1.jsonl"
    with pytest.raises(O.FirewallError):
        O.threshold_from_train(TRAIN[:-1] + [bad])


def test_threshold_refuses_partial_train():
    with pytest.raises(O.FirewallError):
        O.threshold_from_train(TRAIN[:4])


def test_feasibility_cannot_return_a_threshold():
    assert list(inspect.signature(O.feasibility).parameters) == ["prereg_doc", "run_path"]
    fake = {
        "content": {"guard": {"threshold_mbps": 4.0}},
        "content_sha256": "0" * 64,
    }
    with pytest.raises(O.FirewallError):
        O.feasibility(fake, TRAIN[0])


def test_guard_enters_fast_exits_after_three_calm_ticks():
    guard = O.OperatingRangeGuard(4.0)
    sequence = [snap(5, 5, 5)] + [snap(2, 2, 2)] * 3
    assert [guard.update(item) for item in sequence] == [True, True, True, False]


def test_guard_keeps_state_when_unmeasurable():
    guard = O.OperatingRangeGuard(4.0)
    guard.update(snap(5, 5, 5))
    assert guard.update(snap(2, 2, 2, valid=False)) is True


pytestmark_prereg = pytest.mark.skipif(not PREREG.exists(), reason="7.1 chưa niêm phong")


@pytestmark_prereg
def test_prereg_hash_matches():
    document = json.loads(PREREG.read_text(encoding="utf-8"))
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode("utf-8")
    )
    assert "written_at_utc" not in document["content"]


@pytestmark_prereg
def test_prereg_threshold_recomputable_from_train_only():
    document = json.loads(PREREG.read_text(encoding="utf-8"))
    again = O.threshold_from_train(TRAIN)
    assert document["content"]["guard"]["threshold_mbps"] == again["threshold_mbps"]
    for name, digest in document["content"]["train_sha256"].items():
        assert C.sha256_file(C.ROOT / O.TRAIN_DIR / name) == digest


@pytestmark_prereg
def test_prereg_upstream_not_drifted():
    document = json.loads(PREREG.read_text(encoding="utf-8"))
    for relative, digest in document["content"]["upstream_sha256"].items():
        assert C.sha256_file(C.ROOT / relative) == digest, relative
