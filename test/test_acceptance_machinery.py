"""Khoa co che nghiem thu 6R.7 bang fixture, khong mo R-set."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from ml import campaign as C
from ml.acceptance_guard import GuardError, SnapshotReader, count_invocations, log_invocation
from ml.acceptance_stats import (
    DosePoint,
    bootstrap_ed50,
    dose_bracket,
    false_alarm_rate_upper,
    logistic_fit,
    poisson_upper_one_sided,
)


@pytest.mark.parametrize("k, expected", [(0, 2.995732), (1, 4.743865), (3, 7.753657)])
def test_poisson_upper_matches_one_sided_table(k, expected):
    assert poisson_upper_one_sided(k) == pytest.approx(expected, abs=1e-5)


def test_zero_events_is_rule_of_three_on_measured_exposure():
    out = false_alarm_rate_upper(0, at_risk_ticks=3 * 3598)
    assert out["rate_upper_per_hour"] == pytest.approx(
        2.995732 / (3 * 3598 / 3600), rel=1e-6
    )


def test_zero_exposure_refuses():
    with pytest.raises(ValueError):
        false_alarm_rate_upper(0, 0)


def _pts(pairs):
    return [DosePoint(str(i), separation, detected) for i, (separation, detected) in enumerate(pairs)]


def test_bracket_is_geometric_midpoint_when_monotone():
    out = dose_bracket(_pts([(4, False), (9, False), (16, True), (50, True)]))
    assert out["bracket"] == [9, 16]
    assert out["ed50"] == pytest.approx(math.sqrt(9 * 16))


def test_overlap_reports_no_ed50():
    out = dose_bracket(_pts([(4, False), (20, False), (15, True), (50, True)]))
    assert out["kind"] == "overlap"
    assert out["ed50"] is None
    assert out["n_inversions"] == 1


def test_zero_separation_is_floored_and_counted():
    assert dose_bracket(_pts([(0.0, False), (9, False), (16, True)]))["n_floored"] == 1


def test_complete_separation_is_not_a_converged_fit():
    assert logistic_fit([0.5, 0.9, 1.2, 1.7], [0, 0, 1, 1])["converged"] is False


def test_complete_separation_falls_back_to_interpolation():
    out = bootstrap_ed50(
        _pts([(4, False), (9, False), (16, True), (50, True)]), n_boot=200
    )
    assert out["method"] == "interpolation_fallback"
    assert out["ci95"] is None


def test_bootstrap_is_deterministic_under_registered_seed():
    points = _pts(
        [(3, False), (5, False), (8, True), (15, True), (20, False), (30, False), (40, True), (100, True)]
    )
    assert bootstrap_ed50(points, n_boot=300) == bootstrap_ed50(points, n_boot=300)


def test_reader_refuses_second_read_and_bad_sha(tmp_path: Path):
    snapshot = tmp_path / "x.jsonl"
    snapshot.write_bytes(b'{"tick": 0}\n')
    reader = SnapshotReader({"x": C.sha256_bytes(snapshot.read_bytes())})
    assert reader.read_once("x", snapshot) == [{"tick": 0}]
    with pytest.raises(GuardError, match="lan hai"):
        reader.read_once("x", snapshot)
    with pytest.raises(GuardError, match="SHA"):
        SnapshotReader({"x": "0" * 64}).read_once("x", snapshot)


def test_reader_counts_a_crashed_read_as_read(tmp_path: Path):
    snapshot = tmp_path / "x.jsonl"
    snapshot.write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    reader = SnapshotReader({"x": "0" * 64})
    with pytest.raises(GuardError, match="LFS"):
        reader.read_once("x", snapshot)
    assert reader.n_files_read == 1


def test_invocation_log_is_append_only_count(tmp_path: Path):
    log = tmp_path / "runs.log"
    for _ in range(3):
        log_invocation({"mode": "rehearsal", "head": "abc"}, log)
    log_invocation({"mode": "acceptance", "head": "abc"}, log)
    assert count_invocations("rehearsal", log) == 3
    assert count_invocations("acceptance", log) == 1


def test_machinery_sources_never_name_the_r_set():
    for name in ("ml/acceptance_stats.py", "ml/acceptance_pass.py"):
        assert "data/phase6r" not in (C.ROOT / name).read_text(encoding="utf-8")
