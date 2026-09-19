from __future__ import annotations

import random

from measurements.clock_bridge import estimate_offset, to_mono


class FakeWorld:
    TRUE_OFFSET = 12345.678

    def __init__(self, seed=1):
        self.t = 20000.0
        self.rng = random.Random(seed)

    def mono(self):
        self.t += self.rng.uniform(0.0001, 0.003)
        return self.t

    def browser_ms(self):
        self.t += self.rng.uniform(0.0001, 0.003)
        perf = (self.t - self.TRUE_OFFSET) * 1000.0
        self.t += self.rng.uniform(0.0001, 0.003)
        return perf


def test_offset_error_within_reported_bound():
    for seed in range(20):
        world = FakeWorld(seed)
        bridge = estimate_offset(world.browser_ms, n=31, clock=world.mono)
        error_ms = abs(bridge["offset_s"] - FakeWorld.TRUE_OFFSET) * 1000
        assert error_ms <= bridge["error_bound_ms"] + 1e-6


def test_to_mono_roundtrip_and_none():
    bridge = {"offset_s": 100.0}
    assert to_mono(2500.0, bridge) == 102.5
    assert to_mono(None, bridge) is None
