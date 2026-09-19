from __future__ import annotations

import pytest

from measurements.e2e_budget import aggregate, decompose, plot


def tick(seq, t, published="normal", env=False):
    return {
        "bootId": "b", "seq": seq, "t_in": t, "t1": t + 0.002,
        "t2": t + 0.0021, "published": published, "envelope": env,
        "conservation": False, "act_rule": False,
    }


def test_known_answer():
    trial = {"i": 1, "tA": 10.3, "tB": 10.64}
    timeline = [
        tick(0, 10.0), tick(1, 11.0, env=True),
        tick(2, 12.0, "suspect", env=True), tick(3, 13.0, "act", env=True),
    ]
    writes = [{
        "bootId": "b", "seq": 2, "t2": 12.0021, "t3": 12.0221,
        "ok": True, "published": "suspect",
    }]
    perf = [{
        "bootId": "b", "seq": 2, "state": "suspect", "source": "sse",
        "t4": 12.0151, "tDom": 12.0161, "t5": 12.0401,
    }]
    result = decompose(trial, timeline, writes, perf)
    layers, budgets = result["layers_ms"], result["budget_ms"]
    assert layers["phys_obs"] == pytest.approx(360.0)
    assert layers["detect"] == pytest.approx(1002.0)
    assert layers["write_2xx"] == pytest.approx(20.0)
    assert layers["fanout_sse"] == pytest.approx(13.0)
    assert budgets["twin_ui"] == pytest.approx(38.1)
    assert budgets["e2e_from_event"] == pytest.approx(1400.1)
    assert budgets["inject_cmd"] == pytest.approx(340.0)
    assert result["inject_phase"] == pytest.approx(0.3)
    assert result["conflated"] is False


def test_conflation_and_censoring():
    trial = {"i": 2, "tA": 10.3, "tB": 10.64}
    timeline = [
        tick(0, 10.0), tick(1, 11.0, "suspect", env=True),
        tick(2, 12.0, "act", env=True),
    ]
    writes = [{
        "bootId": "b", "seq": 2, "t2": 12.0, "t3": 12.02,
        "ok": True, "published": "act",
    }]
    result = decompose(trial, timeline, writes, [])
    assert result["conflated"] is True
    assert result["budget_ms"]["twin_ui"] is None
    assert decompose(trial, [tick(0, 10.0), tick(1, 11.0)], [], [])["detected"] is False


def test_marks_before_event_are_ignored():
    trial = {"i": 3, "tA": 10.3, "tB": 10.64}
    timeline = [tick(0, 10.0, "suspect", env=True), tick(1, 11.0, "act", env=True)]
    assert decompose(trial, timeline, [], [])["seq_alarm"] == 1


def test_aggregate_and_plot_on_synthetic_run(tmp_path):
    import random

    rng, rows, timeline, writes, perf, start, seq = random.Random(1), [], [], [], [], 100.0, 0
    for index in range(8):
        t_a = start + rng.uniform(0.0, 1.0)
        for offset in range(4):
            published = "normal" if offset < 2 else "suspect"
            timeline.append(dict(tick(seq, start + offset, published, env=offset >= 1)))
            if published == "suspect":
                writes.append({
                    "bootId": "b", "seq": seq, "t2": start + offset,
                    "t3": start + offset + 0.02, "ok": True, "published": published,
                })
                perf.append({
                    "bootId": "b", "seq": seq, "state": published, "source": "sse",
                    "t4": start + offset + 0.015, "tDom": start + offset + 0.016,
                    "t5": start + offset + 0.04,
                })
            seq += 1
        rows.append(decompose(
            {"i": index, "warmup": index == 0, "tA": t_a, "tB": t_a + 0.34},
            timeline, writes, perf,
        ))
        start += 10
    summary = aggregate(rows)
    assert summary["n_trials"] == 7 and summary["warmup_excluded"] == [0]
    assert set(summary["verdict_p95"]) == {
        "s4_like_from_cmd", "twin_ui", "e2e_from_event",
    }
    assert sum(summary["randomization"]["quartile_counts"]) == 7
    assert plot(rows, tmp_path / "p.png")
    assert (tmp_path / "p.png").stat().st_size > 1000
