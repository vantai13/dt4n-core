#!/usr/bin/env python3
"""Append-only intervention log: the FSM's only suppression source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


MAX_OPEN_S = 120.0


@dataclass(frozen=True)
class Intervention:
    id: str
    t_start: float
    actor: str
    action: str
    targets: dict
    blast_radius: frozenset
    routing_sha256: str

    @property
    def kind(self) -> str:
        """Return inject/revert for interval events; other actions are transient."""
        return self.action.split(":", 1)[0]

    @property
    def pair_key(self) -> str:
        """An inject and revert from one action share the id prefix."""
        return self.id.rsplit(":", 1)[0]

    def active_at(self, source_time: float, cooldown_s: float) -> bool:
        return self.t_start <= source_time < self.t_start + cooldown_s


class InterventionLog(Protocol):
    def append(self, item: Intervention) -> None: ...

    def active(self, source_time: float, cooldown_s: float) -> list[Intervention]: ...

    def stale_open(self, source_time: float, max_open_s: float = MAX_OPEN_S) -> list[Intervention]: ...


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

    def active(
        self,
        source_time: float,
        cooldown_s: float,
        max_open_s: float = MAX_OPEN_S,
    ):
        """Return transient events and live inject→revert intervals.

        A closed interval remains active through the post-revert cooldown.  An
        unclosed interval is a lease: it stops exactly at ``max_open_s`` so a
        dead controller cannot blind the detector forever.
        """
        closes = {
            item.pair_key: item.t_start
            for item in self._items
            if item.kind == "revert"
        }
        active = []
        for item in self._items:
            if item.kind == "inject":
                closed_at = closes.get(item.pair_key)
                end = closed_at + cooldown_s if closed_at is not None else item.t_start + max_open_s
                if item.t_start <= source_time < end:
                    active.append(item)
            elif item.active_at(source_time, cooldown_s):
                active.append(item)
        return active

    def stale_open(self, source_time: float, max_open_s: float = MAX_OPEN_S):
        """Expose inject leases which expired without a matching revert."""
        closes = {item.pair_key for item in self._items if item.kind == "revert"}
        return [
            item
            for item in self._items
            if item.kind == "inject"
            and item.pair_key not in closes
            and source_time >= item.t_start + max_open_s
        ]

    def __len__(self):
        return len(self._items)
