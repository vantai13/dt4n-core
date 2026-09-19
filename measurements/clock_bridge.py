#!/usr/bin/env python3
"""Map browser performance.now() to Python's monotonic clock."""
from __future__ import annotations

import time


def estimate_offset(browser_now_ms, n: int = 31, clock=time.monotonic) -> dict:
    best = None
    rtts = []
    for _ in range(n):
        a = clock()
        perf = float(browser_now_ms())
        b = clock()
        rtt = b - a
        rtts.append(rtt)
        if best is None or rtt < best[0]:
            best = (rtt, (a + b) / 2.0 - perf / 1000.0)
    rtts.sort()
    return {
        "offset_s": best[1],
        "error_bound_ms": best[0] / 2.0 * 1000.0,
        "rtt_min_ms": rtts[0] * 1000.0,
        "rtt_median_ms": rtts[len(rtts) // 2] * 1000.0,
        "n": n,
    }


def to_mono(perf_ms, bridge: dict):
    return None if perf_ms is None else bridge["offset_s"] + perf_ms / 1000.0
