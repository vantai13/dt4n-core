from scripts.measure_phase6r_latency_v2 import FIRST_SCORED, summary


def test_cold_start_uses_first_scored_sample_not_warmup_fast_exit():
    assert FIRST_SCORED == 1
    samples = [[0.1, 52.0] + [float(value) for value in range(2, 30)]]
    result = summary(samples)
    assert result["cold_start_ms"] == 52.0
    assert "first scored tick" in result["cold_start_definition"]


def test_latency_summary_enforces_ordered_percentiles():
    samples = [[0.1, 40.0] + [float(value) for value in range(2, 30)]]
    result = summary(samples)
    assert result["max_ms"] >= result["p99_ms"] >= result["p95_ms"] >= result["p50_ms"]
