"""Known-answer test cho thong ke A/B 8.6. Ham thuan -> kiem bang liet ke."""
import math

import pytest

from measurements.ab_stats import (
    block_diffs, bootstrap_ci, randomization_test, summarise,
)


def trials(values_a, values_b, key="primary"):
    rows = []
    for block, (a, b) in enumerate(zip(values_a, values_b)):
        rows.append({"block": block, "arm": "A", key: a})
        rows.append({"block": block, "arm": "B", key: b})
    return rows


def test_hieu_theo_khoi():
    rows = trials([2.0, 3.0, 4.0], [1.0, 1.0, 1.0])
    assert block_diffs(rows) == [1.0, 2.0, 3.0]


def test_khoi_thieu_mot_nhanh_bi_bo():
    rows = trials([2.0, 3.0], [1.0, 1.0])
    rows.append({"block": 9, "arm": "A", "primary": 5.0})     # khoi khong du cap
    assert len(block_diffs(rows)) == 2


def test_tick_none_khong_lam_hong_trung_binh():
    rows = [{"block": 0, "arm": "A", "primary": 2.0},
            {"block": 0, "arm": "A", "primary": None},
            {"block": 0, "arm": "B", "primary": 1.0}]
    assert block_diffs(rows) == [1.0]


def test_bootstrap_hang_so_thi_CI_bang_chinh_no():
    mean, lo, hi = bootstrap_ci([1.5] * 6)
    assert mean == lo == hi == 1.5


def test_bootstrap_tat_dinh_theo_seed():
    diffs = [0.4, 1.9, 1.2, 2.4, 0.8, 1.1, 1.7, 1.4]
    assert bootstrap_ci(diffs, seed=7) == bootstrap_ci(diffs, seed=7)
    assert bootstrap_ci(diffs, seed=7) != bootstrap_ci(diffs, seed=8)


def test_bootstrap_bao_quanh_trung_binh():
    diffs = [1.0, 1.2, 0.9, 1.4, 1.1, 1.3, 1.0, 1.2]
    mean, lo, hi = bootstrap_ci(diffs)
    assert lo < mean < hi
    assert lo > 0                       # hieu ung ro -> CI hoan toan tren 0


def test_randomization_chinh_xac_khi_it_khoi():
    """3 khoi -> 2^3 = 8 to hop, liet ke DU nen p la boi so cua 1/8."""
    result = randomization_test([1.0, 2.0, 3.0])
    assert result["exact"] is True and result["n_perm"] == 8
    assert math.isclose(result["p_two_sided"], 2 / 8)     # chi +++ va --- dat


def test_randomization_khong_hieu_ung_thi_p_lon():
    result = randomization_test([0.1, -0.2, 0.15, -0.05, 0.02, -0.11, 0.03, -0.01])
    assert result["p_two_sided"] > 0.2


def test_randomization_hieu_ung_ro_thi_p_nho():
    result = randomization_test([1.7, 1.9, 1.6, 1.8, 1.5, 2.0, 1.7, 1.6])
    assert result["p_two_sided"] <= 2 / 2 ** 8            # chi mot to hop dat


def test_summarise_canh_bao_khi_it_khoi():
    few = summarise(trials([2.0] * 5, [1.0] * 5))
    assert few["n_blocks"] == 5 and few["caveat"]
    many = summarise(trials([2.0] * 8, [1.0] * 8))
    assert many["caveat"] is None
    assert many["ci95_excludes_zero"] is True
    assert many["block_diffs"] == [1.0] * 8               # LUON in hieu tho


def test_summarise_khong_hieu_ung():
    rows = trials([1.0, 1.1, 0.9, 1.2, 1.0, 1.1, 0.95, 1.05],
                  [1.05, 1.0, 1.0, 1.1, 1.1, 1.0, 1.0, 1.0])
    result = summarise(rows)
    assert result["ci95_excludes_zero"] is False
    assert result["randomization_test"]["p_two_sided"] > 0.05


def test_ham_thuan():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1]
              / "measurements/ab_stats.py").read_text(encoding="utf-8")
    for forbidden in ("import time", "open(", "requests", "datetime"):
        assert forbidden not in source
