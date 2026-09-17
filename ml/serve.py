#!/usr/bin/env python3
"""Online scorer sharing the exact Phase 6 batch transformation path."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import dataclasses
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import conservation as K
from ml.features import add_aggregate_features
from ml.flatten import flatten_snapshot
from ml.missing import assert_no_fabricated_zero_in_loss, mask_invalid_rates
from ml.model import EnvelopeModel
from ml.snapshot_contract import sanitize

log = logging.getLogger("serve")
MAX_INTERVAL_S = 1.5
MIN_INTERVAL_S = 0.5


@dataclass(frozen=True)
class ConservationLayer:
    """Residual layer frozen in the signed amendment; shadow by default."""

    incidence: dict
    threshold: float
    floor: float
    amendment_sha256: str

    @classmethod
    def load(cls, path) -> "ConservationLayer":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        digest = C.sha256_bytes(C.canonical_json(doc["content"]).encode("utf-8"))
        if digest != doc["content_sha256"]:
            raise ValueError("amendment 1 bi sua: hash lech")
        detector = doc["content"]["detector"]
        incidence = {
            switch: [tuple(pair) for pair in rows]
            for switch, rows in detector["incidence"].items()
        }
        return cls(
            incidence=incidence,
            threshold=float(doc["content"]["calibration"]["R"]),
            floor=float(detector["floor_bps"]),
            amendment_sha256=digest,
        )


@dataclass(frozen=True)
class Reading:
    t_source: float | None
    tick: int | None
    status: str
    reason: str
    judgeable: bool = False
    k: int | None = None
    k_indicator: int | None = None
    k_rate: int | None = None
    excess: float | None = None
    suspect: bool = False
    act: bool = False
    envelope_suspect: bool = False
    cons_judgeable: bool = False
    cons_r_max: float | None = None
    cons_switch: str | None = None
    cons_alarm: bool = False
    interval_s: float | None = None
    n_missing_columns: int = 0
    n_contract_violations: int = 0
    cause: str | None = None
    violating: tuple = ()


@dataclass
class _State:
    n_accepted: int = 0
    last_t: float | None = None
    last_digest: str | None = None
    last_reading: Reading | None = None
    n_rejected: int = 0


class OnlineScorer:
    """One instance serves exactly one continuous snapshot stream."""

    def __init__(
        self,
        model: EnvelopeModel,
        *,
        expected_collector_version: str,
        warmup_ticks: int = 1,
        conservation: ConservationLayer | None = None,
        conservation_mode: str = "shadow",
    ):
        if conservation_mode not in ("shadow", "active", "off"):
            raise ValueError("conservation_mode phai shadow|active|off")
        if conservation_mode == "active" and conservation is None:
            raise ValueError("active can conservation layer")
        self.model = model
        self.expected_collector_version = expected_collector_version
        self.warmup_ticks = int(warmup_ticks)
        self.conservation = conservation if conservation_mode != "off" else None
        self.conservation_mode = conservation_mode
        self._s = _State()
        self._link_inputs = sorted(
            {
                column
                for column in model.columns
                if column.startswith("link-")
                and column.endswith((".traffic.lossPct", ".status.state_up"))
            }
            | set(model.link_stats)
        )
        self._cons_inputs = (
            K.required_columns(conservation.incidence) if self.conservation else []
        )

    @staticmethod
    def _digest(snapshot: dict) -> str:
        return hashlib.sha256(C.canonical_json(snapshot).encode("utf-8")).hexdigest()

    def observe(self, snapshot: dict) -> Reading:
        source_time, tick = snapshot.get("t_source"), snapshot.get("tick")
        if (
            isinstance(source_time, bool)
            or not isinstance(source_time, (int, float))
            or not math.isfinite(source_time)
        ):
            return self._reject(None, tick, "thieu t_source hop le: khong sap thu tu duoc")
        digest = self._digest(snapshot)
        state = self._s
        if state.last_t is not None:
            if source_time == state.last_t:
                if digest == state.last_digest:
                    return state.last_reading
                return self._reject(source_time, tick, "xung dot: cung t_source, noi dung khac")
            if source_time < state.last_t:
                return self._reject(
                    source_time,
                    tick,
                    "sai thu tu: t_source %.6f < da thay %.6f" % (source_time, state.last_t),
                )
        interval = None if state.last_t is None else source_time - state.last_t
        clean, violations = sanitize(snapshot)
        reading = self._score(clean, source_time, tick, interval)
        if violations:
            note = (
                "input contract: %d truong sai kieu -> coi la khong do duoc (%s)"
                % (len(violations), "; ".join(violations[:3]))
            )
            reading = dataclasses.replace(
                reading,
                cause="contract" if reading.cause == "missing_data" else reading.cause,
                n_contract_violations=len(violations),
                reason=note if not reading.reason else reading.reason + "; " + note,
            )
        state.n_accepted += 1
        state.last_t, state.last_digest, state.last_reading = source_time, digest, reading
        return reading

    def _reject(self, source_time, tick, reason) -> Reading:
        self._s.n_rejected += 1
        log.warning("REJECT t_source=%s tick=%s: %s", source_time, tick, reason)
        return Reading(
            t_source=source_time,
            tick=tick,
            status="rejected",
            reason=reason,
            cause="rejected",
        )

    def frame_of(self, snapshot: dict) -> pd.DataFrame:
        """Snapshot to one-row frame using the shared batch functions."""
        frame = pd.DataFrame([flatten_snapshot(snapshot)])
        inputs = sorted(set(frame.columns) | set(self._link_inputs) | set(self._cons_inputs))
        frame = frame.reindex(columns=inputs)
        frame, _ = mask_invalid_rates(frame)
        assert_no_fabricated_zero_in_loss(frame)
        frame, _ = add_aggregate_features(frame, link_stats=self.model.link_stats)
        return frame

    def _score(self, snapshot, source_time, tick, interval) -> Reading:
        base = {"t_source": source_time, "tick": tick, "interval_s": interval}
        if self._s.n_accepted < self.warmup_ticks:
            return Reading(
                **base,
                status="warming_up",
                cause="warmup",
                reason="warmup %d/%d: rate/qdisc cua collector chua co khoang so sanh"
                % (self._s.n_accepted + 1, self.warmup_ticks),
            )
        collector_version = (snapshot.get("run") or {}).get(
            "collector_version", snapshot.get("collector_version")
        )
        if collector_version != self.expected_collector_version:
            return Reading(
                **base,
                status="unknown",
                cause="collector_version",
                reason="collector_version %r != %r: dai luong khac, khong cham"
                % (collector_version, self.expected_collector_version),
            )
        if interval is not None and not (MIN_INTERVAL_S <= interval <= MAX_INTERVAL_S):
            return Reading(
                **base,
                status="unknown",
                cause="gap",
                reason="khoang snapshot %.3f s ngoai [%.1f, %.1f]: qdisc*Delta phu thuoc khoang do"
                % (interval, MIN_INTERVAL_S, MAX_INTERVAL_S),
            )

        frame = self.frame_of(snapshot)
        missing = [column for column in self.model.columns if column not in frame.columns]
        for column in missing:
            frame[column] = np.nan
        decision = self.model.score_batch(frame)
        low, high, _ = self.model._vec["primary"]
        values = self.model._matrix(frame, self.model.families["primary"])[0]
        with np.errstate(invalid="ignore"):
            outside = (values < low) | (values > high)
        violating = tuple(
            column
            for column, is_outside in zip(
                self.model.families["primary"], outside
            )
            if is_outside
        )
        judgeable = bool(decision.judgeable[0])
        envelope_suspect, act = bool(decision.suspect[0]), bool(decision.act[0])
        cons_fields = {}
        if self.conservation is not None:
            residual = K.residuals(frame, self.conservation.incidence, floor=self.conservation.floor)
            cons_judgeable = bool(residual["judgeable"].iloc[0])
            cons_fields = {
                "cons_judgeable": cons_judgeable,
                "cons_r_max": float(residual["r_max"].iloc[0]) if cons_judgeable else None,
                "cons_switch": residual["argmax_switch"].iloc[0] if cons_judgeable else None,
                "cons_alarm": bool(K.alarm(residual, self.conservation.threshold)[0]),
            }
        suspect = envelope_suspect or (
            self.conservation_mode == "active" and cons_fields.get("cons_alarm", False)
        )
        n_nan = int(
            frame[self.model.columns]
            .apply(pd.to_numeric, errors="coerce")
            .isna()
            .sum(axis=1)
            .iloc[0]
        )
        fields = {
            **base,
            "judgeable": judgeable,
            "k": int(decision.k[0]),
            "k_indicator": int(decision.k_indicator[0]),
            "k_rate": int(decision.k_rate[0]),
            "excess": float(decision.excess[0]),
            "suspect": suspect,
            "act": act,
            "envelope_suspect": envelope_suspect,
            "n_missing_columns": len(missing),
            "violating": violating,
            **cons_fields,
        }
        if not judgeable:
            suffix = " (%d cot vang mat)" % len(missing) if missing else ""
            return Reading(
                **fields,
                status="unknown",
                cause="missing_data",
                reason="%d/%d cot khong huu han%s -> unknown, khong bao gio normal"
                % (n_nan, len(self.model.columns), suffix),
            )
        reasons = []
        if act:
            reasons.append(
                "act: k_ind %d > %s hoac k_rate %d > %s"
                % (
                    decision.k_indicator[0],
                    self.model.thresholds["indicator"]["K"],
                    decision.k_rate[0],
                    self.model.thresholds["rate_shared"]["K"],
                )
            )
        if envelope_suspect:
            reasons.append(
                "suspect: excess %.6g > E %.6g (%d cot ngoai bien)"
                % (decision.excess[0], self.model.thresholds["primary"]["E"], decision.k[0])
            )
        if cons_fields.get("cons_alarm"):
            reasons.append(
                "residual %s: r(%s)=%.4f > R %.4f"
                % (
                    self.conservation_mode,
                    cons_fields["cons_switch"],
                    cons_fields["cons_r_max"],
                    self.conservation.threshold,
                )
            )
        return Reading(**fields, status="scored", reason="; ".join(reasons))
