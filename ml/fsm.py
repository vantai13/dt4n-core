#!/usr/bin/env python3
"""Five-state detector FSM over typed OnlineScorer readings."""
from __future__ import annotations

from dataclasses import dataclass

from ml.blast_radius import entity_of


STATES = ("warming_up", "normal", "suspect", "act", "unknown")
CAUSES = (
    "warmup",
    "collector_version",
    "gap",
    "missing_data",
    "contract",
    "suppressed_intervention",
)


@dataclass(frozen=True)
class FSMParams:
    n_suspect: int = 1
    n_act: int = 2
    release_m: int = 3
    cooldown_s: float = 8.0

    def __post_init__(self):
        if (
            min(self.n_suspect, self.n_act, self.release_m) < 1
            or self.cooldown_s <= 0
        ):
            raise ValueError("tham so FSM phai duong")
        if self.release_m <= self.n_act:
            raise ValueError("release_m phai > n_act de chong dao dong X->Y->X")


@dataclass(frozen=True)
class Transition:
    t_source: float | None
    tick: int | None
    state: str
    prev: str
    changed: bool
    cause: str | None
    reason: str
    suppressed_by: tuple = ()


class DetectorFSM:
    def __init__(self, params: FSMParams, log=None):
        self.p = params
        self.log = log
        self.state = "warming_up"
        self._cs = self._ca = self._quiet = 0

    def _reset(self):
        self._cs = self._ca = self._quiet = 0

    def _emit(self, reading, state, cause, reason, suppressed=()):
        previous, self.state = self.state, state
        return Transition(
            reading.t_source,
            reading.tick,
            state,
            previous,
            state != previous,
            cause,
            reason,
            suppressed,
        )

    def step(self, reading) -> Transition:
        if reading.status == "rejected":
            return Transition(
                reading.t_source,
                reading.tick,
                self.state,
                self.state,
                False,
                None,
                "bo qua snapshot bi tu choi: " + reading.reason,
            )
        if reading.status == "warming_up":
            self._reset()
            return self._emit(reading, "warming_up", "warmup", reading.reason)
        if reading.status == "unknown":
            self._reset()
            cause = reading.cause if reading.cause in CAUSES else "missing_data"
            return self._emit(reading, "unknown", cause, reading.reason)
        if reading.status != "scored":
            raise ValueError("Reading.status la: %r" % reading.status)

        alarming = reading.suspect or reading.act
        if alarming and self.log is not None:
            active = self.log.active(reading.t_source, self.p.cooldown_s)
            if active:
                zone = frozenset().union(
                    *(item.blast_radius for item in active)
                )
                local = {entity_of(column) for column in reading.violating} - {None}
                if local and local <= zone:
                    self._reset()
                    ids = tuple(item.id for item in active)
                    return self._emit(
                        reading,
                        "unknown",
                        "suppressed_intervention",
                        "suppressed: %d entity vi pham deu thuoc vung cua %s (con han %.0f s)"
                        % (len(local), ",".join(ids), self.p.cooldown_s),
                        ids,
                    )

        self._cs = self._cs + 1 if alarming else 0
        self._ca = self._ca + 1 if reading.act else 0
        self._quiet = 0 if alarming else self._quiet + 1
        base = "normal" if self.state in ("warming_up", "unknown") else self.state
        if self._ca >= self.p.n_act:
            new_state = "act"
            reason = "act %d tick lien tiep >= %d; %s" % (
                self._ca,
                self.p.n_act,
                reading.reason,
            )
        elif base == "act":
            new_state = "normal" if self._quiet >= self.p.release_m else "act"
            reason = (
                "ra act: %d tick khong bao" % self._quiet
                if new_state == "normal"
                else "giu act (hysteresis): khong bao %d/%d tick"
                % (self._quiet, self.p.release_m)
            )
        elif self._cs >= self.p.n_suspect:
            new_state, reason = "suspect", reading.reason or "suspect"
        elif base == "suspect":
            new_state = "normal" if self._quiet >= self.p.release_m else "suspect"
            reason = (
                "ra suspect: %d tick khong bao" % self._quiet
                if new_state == "normal"
                else "giu suspect (hysteresis): khong bao %d/%d tick"
                % (self._quiet, self.p.release_m)
            )
        else:
            new_state, reason = "normal", ""
        return self._emit(reading, new_state, None, reason)
