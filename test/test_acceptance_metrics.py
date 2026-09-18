"""Khoa metric nghiem thu tren fixture va Phase 5 truoc khi mo R-set."""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from ml.acceptance_metrics import inject_clock, s4_nearest_rank_p95, window

RD_LIKE = {
    "events": [
        {"kind": "inject", "tick": 20, "t_source": 1000.0, "apply_ms": 20.0},
        {"kind": "revert", "tick": 40, "t_source": 1020.0},
    ],
    "interventions": [{"id": "x:revert", "t_start": 1019.98, "tick": 40}],
}


def test_inject_clock_ignores_revert_only_interventions():
    assert inject_clock(RD_LIKE) == pytest.approx(999.98)
    assert window(RD_LIKE) == (21, 40)


def test_nearest_rank_p95_equals_max_for_small_n():
    assert s4_nearest_rank_p95([900.0, 1000.0, 2000.0]) == 2000.0
    assert s4_nearest_rank_p95([]) is None


def test_phase5_sidecar_shape_matches_what_metrics_read():
    meta = json.loads(
        (C.ROOT / "data/phase5/raw/F-degrade-s2-s3-s3004-r1.meta.json").read_text(
            encoding="utf-8"
        )
    )
    assert window(meta) == (21, 40)
    assert inject_clock(meta) < meta["events"][0]["t_source"]
