"""Freshness phía consumer — Phase 7 amendment 1.

Giữ nguyên tracker 7.2 đã niêm phong. Consumer mới dùng lớp này để chỉ chấp
nhận heartbeat tiến về phía trước, đo TTL bằng đồng hồ cục bộ và mặc định
STALE cho tới khi quan sát được một thay đổi hợp lệ sau lần ARM đầu tiên.
"""
from __future__ import annotations

import time
from collections.abc import Callable


class MonotonicFreshness:
    """Cổng monotonic-read cho document detector."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._boot = None
        self._seq = None
        self._retired: set = set()
        self._confirmed_at = None

    def observe(self, freshness: dict) -> bool:
        """Trả True khi cả bản tin được phép hiển thị; False nghĩa là bỏ."""
        boot, seq = freshness.get("bootId"), freshness.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            return False
        if self._boot is None:
            self._boot, self._seq = boot, seq
            return True
        if boot == self._boot:
            if seq <= self._seq:
                return False
        elif boot in self._retired:
            return False
        else:
            self._retired.add(self._boot)
        self._boot, self._seq = boot, seq
        self._confirmed_at = self._clock()
        return True

    def is_stale(self, freshness: dict) -> bool:
        if self._confirmed_at is None:
            return True
        ttl_s = (
            freshness.get("ttlTicks", 3)
            * freshness.get("tickIntervalMs", 1000)
            / 1000.0
        )
        return (self._clock() - self._confirmed_at) > ttl_s

    def last_confirmed_age_s(self):
        if self._confirmed_at is None:
            return None
        return self._clock() - self._confirmed_at
