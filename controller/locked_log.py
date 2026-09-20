#!/usr/bin/env python3
"""Boc InterventionLog bang khoa (Phase 8.4).

Tu 8.4 co HAI luong dung chung log:
  - control thread GHI (write-ahead truoc khi gui lenh, M5)
  - collector thread DOC (fsm.step -> log.active() / log.stale_open())

`ml.intervention_log.InMemoryInterventionLog` khong co khoa. GIL lam xac suat
hong thap, nhung "xac suat thap" khong phai "dung": soak 30 phut o 8.7 co
~1800 lan giao nhau.

KHONG sua ml/intervention_log.py: no nam trong duong chay da do o Phase 6R/7.
Boc la cach duy nhat khong dung vao artifact da dong bang.
"""
from __future__ import annotations

import threading


class LockedInterventionLog:
    """Proxy an toan luong. Tra BAN SAO de ben doc khong cam tham chieu song."""

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Lock()

    def append(self, item) -> None:
        with self._lock:
            self._inner.append(item)

    def active(self, *args, **kwargs) -> list:
        with self._lock:
            return list(self._inner.active(*args, **kwargs))

    def stale_open(self, *args, **kwargs) -> list:
        with self._lock:
            return list(self._inner.stale_open(*args, **kwargs))

    def snapshot(self) -> list:
        with self._lock:
            return list(getattr(self._inner, "_items", ()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._inner)
