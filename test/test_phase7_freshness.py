#!/usr/bin/env python3
"""Lesson 7.4: Python và JS chạy cùng đặc tả freshness đơn điệu."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from bridge import detector_contract as D
from bridge.freshness import MonotonicFreshness
from ml import campaign as C

VECTORS = json.loads(
    (C.ROOT / "test/fixtures/freshness_vectors.json").read_text()
)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["name"])
def test_python_tracker_matches_vectors(case):
    clock = Clock()
    tracker = MonotonicFreshness(clock)
    for step in case["steps"]:
        clock.t = step["at"] / 1000.0
        if "observe" in step:
            boot, seq = step["observe"]
            assert tracker.observe({"bootId": boot, "seq": seq}) is step["accepted"]
        else:
            assert tracker.is_stale(VECTORS["ttl"]) is step["stale"]


def test_sealed_tracker_is_fooled_by_regression():
    """Tracker 7.2 coi seq lùi là heartbeat mới; đây là lý do amendment."""
    clock = Clock()
    old = D.FreshnessTracker(clock)
    old.observe({"bootId": "a", "seq": 5})
    clock.t = 1.0
    old.observe({"bootId": "a", "seq": 6})
    clock.t = 3.5
    old.observe({"bootId": "a", "seq": 4})
    clock.t = 4.1
    assert old.is_stale(VECTORS["ttl"]) is False


@pytest.mark.skipif(shutil.which("node") is None, reason="không có node")
def test_js_twin_passes_same_vectors_and_map_rules():
    files = sorted(str(path) for path in (C.ROOT / "dashboard/test").glob("*.test.mjs"))
    result = subprocess.run(
        ["node", "--test", *files],
        capture_output=True,
        text=True,
        cwd=C.ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]


AMENDMENT = C.ROOT / "results/report/phase7_contract_amendment_1.json"


@pytest.mark.skipif(not AMENDMENT.exists(), reason="amendment 1 chưa niêm phong")
def test_amendment_1_sealed_and_pinned():
    document = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    )
    for relative, checksum in document["content"]["upstream_sha256"].items():
        assert C.sha256_file(C.ROOT / relative) == checksum, "đã đổi sau niêm phong: " + relative
