#!/usr/bin/env python3
"""Append-only intervention log: the FSM's only suppression source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Intervention:
    id: str
    t_start: float
    actor: str
    action: str
    targets: dict
    blast_radius: frozenset
    routing_sha256: str

    def active_at(self, source_time: float, cooldown_s: float) -> bool:
        return self.t_start <= source_time < self.t_start + cooldown_s


class InterventionLog(Protocol):
    def append(self, item: Intervention) -> None: ...

    def active(self, source_time: float, cooldown_s: float) -> list[Intervention]: ...


class InMemoryInterventionLog:
    def __init__(self):
        self._items: list[Intervention] = []
        self._ids: set[str] = set()

    def append(self, item: Intervention) -> None:
        if item.id in self._ids:
            raise ValueError(
                "intervention id da ton tai (append-only): %s" % item.id
            )
        if not item.blast_radius:
            raise ValueError("intervention khong co vung anh huong: %s" % item.id)
        self._items.append(item)
        self._ids.add(item.id)

    def active(self, source_time: float, cooldown_s: float):
        return [
            item
            for item in self._items
            if item.active_at(source_time, cooldown_s)
        ]

    def __len__(self):
        return len(self._items)
