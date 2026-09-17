#!/usr/bin/env python3
"""NumPy scalar fast path guarded by equivalence against ``ml.serve``.

``OnlineScorer`` remains the readable reference.  This implementation keeps
its delivery state machine but avoids constructing several one-row pandas
frames.  It may be used only while the replay receipt remains bit-exact.
"""
from __future__ import annotations

import math

import numpy as np

from ml.flatten import flatten_snapshot
from ml.serve import MAX_INTERVAL_S, MIN_INTERVAL_S, OnlineScorer, Reading


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return np.nan
    return result if math.isfinite(result) else np.nan


class FastOnlineScorer(OnlineScorer):
    """Reference-compatible scorer using precomputed NumPy vectors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loss_inputs = [
            column for column in self._link_inputs if column.endswith(".traffic.lossPct")
        ]
        self._state_inputs = [
            column for column in self._link_inputs if column.endswith(".status.state_up")
        ]
        self._rate_inputs = sorted(self.model.link_stats)
        self._columns = list(self.model.columns)
        self._column_index = {column: index for index, column in enumerate(self._columns)}
        self._family_indices = {
            name: np.array([self._column_index[column] for column in columns], dtype=int)
            for name, columns in self.model.families.items()
        }
        self._incidence = {}
        if self.conservation is not None:
            self._incidence = {
                switch: [(column, side) for column, side in rows]
                for switch, rows in self.conservation.incidence.items()
            }

    def _values(self, snapshot):
        row = flatten_snapshot(snapshot)
        present = set(row) | set(self._link_inputs) | set(self._cons_inputs)

        for valid_column in [column for column in row if column.endswith(".rateValid")]:
            if row.get(valid_column) is not True:
                stem = valid_column[: -len(".rateValid")]
                for side in ("rxRate", "txRate"):
                    rate_column = stem + "." + side
                    if rate_column in present:
                        row[rate_column] = np.nan

        for valid_column in [column for column in row if column.endswith(".qdiscValid")]:
            if row.get(valid_column) is False:
                loss_column = valid_column.replace("qdiscValid", "lossPct")
                if loss_column in row and not math.isnan(_number(row[loss_column])):
                    raise AssertionError(
                        "%s co gia tri o noi %s la False -> da bi bia so"
                        % (loss_column, valid_column)
                    )

        loss = np.array([_number(row.get(column)) for column in self._loss_inputs])
        state = np.array([_number(row.get(column)) for column in self._state_inputs])
        rates = np.array([_number(row.get(column)) for column in self._rate_inputs])
        if np.isfinite(loss).any():
            row["agg.loss_max"] = float(np.nanmax(loss))
        else:
            row["agg.loss_max"] = np.nan
        row["agg.loss_n_above_alert"] = int(np.sum(loss > 1.0))
        row["agg.links_down"] = int(np.sum(state == 0))
        z_scores = np.array(
            [
                abs((value - self.model.link_stats[column]["mean"]) / self.model.link_stats[column]["std"])
                if math.isfinite(value)
                else np.nan
                for column, value in zip(self._rate_inputs, rates)
            ]
        )
        row["agg.rate_absz_max"] = (
            float(np.nanmax(z_scores)) if np.isfinite(z_scores).any() else np.nan
        )
        row["agg.rate_absz_n_above_3"] = int(np.sum(z_scores > 3.0))
        present.update(
            {
                "agg.loss_max",
                "agg.loss_n_above_alert",
                "agg.links_down",
                "agg.rate_absz_max",
                "agg.rate_absz_n_above_3",
            }
        )
        values = np.array([_number(row.get(column)) for column in self._columns])
        missing = [column for column in self._columns if column not in present]
        return row, values, missing

    def _family(self, values, name):
        indices = self._family_indices[name]
        family_values = values[indices]
        low, high, scale = self.model._vec[name]
        with np.errstate(invalid="ignore"):
            violations = (family_values < low) | (family_values > high)
            amounts = np.maximum.reduce(
                [low - family_values, family_values - high, np.zeros_like(family_values)]
            ) / scale
        return int(violations.sum()), float(np.nansum(amounts)), bool(np.isfinite(family_values).all())

    def _conservation(self, row):
        residuals = {}
        judgeable = True
        for switch, incidence in self._incidence.items():
            inflow = np.zeros(1)
            outflow = np.zeros(1)
            for column, side in incidence:
                value = np.array([_number(row.get(column))])
                if side == "in":
                    inflow = inflow + value
                else:
                    outflow = outflow + value
            residual = ((inflow - outflow) / np.maximum(inflow, self.conservation.floor))[0]
            residuals[switch] = float(residual)
            judgeable &= bool(np.isfinite(residual))
        if not judgeable:
            return False, None, None, False
        switch = max(residuals, key=residuals.get)
        maximum = residuals[switch]
        return True, maximum, switch, maximum > self.conservation.threshold

    def _score(self, snapshot, source_time, tick, interval):
        base = {"t_source": source_time, "tick": tick, "interval_s": interval}
        if self._s.n_accepted < self.warmup_ticks:
            return Reading(
                **base,
                status="warming_up",
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
                reason="collector_version %r != %r: dai luong khac, khong cham"
                % (collector_version, self.expected_collector_version),
            )
        if interval is not None and not (MIN_INTERVAL_S <= interval <= MAX_INTERVAL_S):
            return Reading(
                **base,
                status="unknown",
                reason="khoang snapshot %.3f s ngoai [%.1f, %.1f]: qdisc*Delta phu thuoc khoang do"
                % (interval, MIN_INTERVAL_S, MAX_INTERVAL_S),
            )

        row, values, missing = self._values(snapshot)
        k, excess, judgeable = self._family(values, "primary")
        k_indicator, _, _ = self._family(values, "indicator")
        k_rate, _, _ = self._family(values, "rate_shared")
        envelope_suspect = judgeable and excess > float(self.model.thresholds["primary"]["E"])
        act = judgeable and (
            k_indicator > int(self.model.thresholds["indicator"]["K"])
            or k_rate > int(self.model.thresholds["rate_shared"]["K"])
        )
        cons_fields = {}
        if self.conservation is not None:
            cons_judgeable, cons_r_max, cons_switch, cons_alarm = self._conservation(row)
            cons_fields = {
                "cons_judgeable": cons_judgeable,
                "cons_r_max": cons_r_max,
                "cons_switch": cons_switch,
                "cons_alarm": cons_alarm,
            }
        suspect = envelope_suspect or (
            self.conservation_mode == "active" and cons_fields.get("cons_alarm", False)
        )
        fields = {
            **base,
            "judgeable": judgeable,
            "k": k,
            "k_indicator": k_indicator,
            "k_rate": k_rate,
            "excess": excess,
            "suspect": suspect,
            "act": act,
            "envelope_suspect": envelope_suspect,
            "n_missing_columns": len(missing),
            **cons_fields,
        }
        if not judgeable:
            suffix = " (%d cot vang mat)" % len(missing) if missing else ""
            return Reading(
                **fields,
                status="unknown",
                reason="%d/%d cot khong huu han%s -> unknown, khong bao gio normal"
                % (int(np.isnan(values).sum()), len(values), suffix),
            )
        reasons = []
        if act:
            reasons.append(
                "act: k_ind %d > %s hoac k_rate %d > %s"
                % (
                    k_indicator,
                    self.model.thresholds["indicator"]["K"],
                    k_rate,
                    self.model.thresholds["rate_shared"]["K"],
                )
            )
        if envelope_suspect:
            reasons.append(
                "suspect: excess %.6g > E %.6g (%d cot ngoai bien)"
                % (excess, self.model.thresholds["primary"]["E"], k)
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
