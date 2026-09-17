#!/usr/bin/env python3
"""Loadable, self-verifying Phase 6 envelope model artifact.

The scoring layer consumes feature values.  The decision layer consumes only
the resulting counts/excess and is intentionally exposed separately so it can
be verified from the committed Phase 6 tick receipt without raw observations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml import campaign as C


SCHEMA_VERSION = "DT4N-ENV-ARTIFACT-1"
HASH_FIELD = "content_sha256"


class ArtifactError(ValueError):
    """The model artifact or its scoring input violates the declared schema."""


@dataclass(frozen=True)
class Decision:
    """Immutable batch scoring and decision result."""

    k: np.ndarray
    excess: np.ndarray
    judgeable: np.ndarray
    suspect: np.ndarray
    act: np.ndarray
    k_indicator: np.ndarray
    k_rate: np.ndarray


class EnvelopeModel:
    """Frozen envelope bounds, thresholds, feature families and link stats."""

    def __init__(self, content: dict):
        self._c = content
        self.columns = list(content["columns"])
        self.families = {
            name: list(columns) for name, columns in content["families"].items()
        }
        self.bounds = content["bounds"]
        self.thresholds = content["thresholds"]
        self.floors = content["floors"]
        self.link_stats = content["link_stats"]
        self.version = content["version"]
        self._vec = {
            name: self._vectors(columns)
            for name, columns in self.families.items()
        }

    @staticmethod
    def _check_content(content: dict) -> None:
        """Reject artifact drift instead of silently repairing it."""
        required = (
            "schema_version",
            "version",
            "columns",
            "families",
            "bounds",
            "thresholds",
            "floors",
            "link_stats",
            "feature_spec",
            "unknown_policy",
            "provenance",
        )
        missing_keys = [key for key in required if key not in content]
        if missing_keys:
            raise ArtifactError("artifact thieu khoa: %s" % missing_keys)

        if content["schema_version"] != SCHEMA_VERSION:
            raise ArtifactError(
                "schema_version la %r, can %r"
                % (content["schema_version"], SCHEMA_VERSION)
            )

        version_parts = str(content["version"]).split("-")[-1].split(".")
        if len(version_parts) != 3 or not all(
            part.isdigit() for part in version_parts
        ):
            raise ArtifactError(
                "version khong doc duoc (can semver): %r" % content["version"]
            )

        columns = content["columns"]
        if len(columns) != len(set(columns)):
            raise ArtifactError("columns co ten trung")
        bounds = content["bounds"]
        missing_bounds = [column for column in columns if column not in bounds]
        if missing_bounds:
            raise ArtifactError("thieu bounds cho: %s" % missing_bounds[:5])
        column_set = set(columns)
        extra_bounds = [column for column in bounds if column not in column_set]
        if extra_bounds:
            raise ArtifactError(
                "bounds co cot khong khai trong columns: %s" % extra_bounds[:5]
            )

        families = content["families"]
        for required_family in ("primary", "indicator", "rate_shared", "loss_only"):
            if required_family not in families:
                raise ArtifactError("thieu ho %s" % required_family)
        if list(families["primary"]) != list(columns):
            raise ArtifactError("ho primary khong khop columns")
        indicator = set(families["indicator"])
        rate_shared = set(families["rate_shared"])
        if indicator & rate_shared:
            raise ArtifactError("indicator va rate_shared giao nhau")
        if indicator | rate_shared != column_set:
            raise ArtifactError("indicator + rate_shared khong phu het columns")
        for name, family_columns in families.items():
            unknown = [column for column in family_columns if column not in column_set]
            if unknown:
                raise ArtifactError("ho %s co cot la: %s" % (name, unknown[:5]))
            if name not in content["thresholds"]:
                raise ArtifactError("ho %s khong co nguong" % name)

        for column in columns:
            bound = bounds[column]
            try:
                low, high = float(bound["min"]), float(bound["max"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ArtifactError("bounds khong hop le: " + column) from exc
            if not np.isfinite(low) or not np.isfinite(high) or low > high:
                raise ArtifactError("bounds khong hop le: " + column)

    def validate_schema(self, frame_columns) -> None:
        """Reject missing model inputs; harmless extra snapshot fields are allowed."""
        available = set(frame_columns)
        missing = [column for column in self.columns if column not in available]
        if missing:
            raise ArtifactError(
                "dau vao thieu %d cot, vi du: %s" % (len(missing), missing[:5])
            )

    @classmethod
    def load(cls, path) -> "EnvelopeModel":
        """Read and validate one artifact.  This function never fits values."""
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if HASH_FIELD not in doc or "content" not in doc:
            raise ArtifactError("file khong phai artifact (thieu content/hash)")
        content = doc["content"]
        digest = C.sha256_bytes(C.canonical_json(content).encode("utf-8"))
        if digest != doc[HASH_FIELD]:
            raise ArtifactError(
                "content_sha256 lech: file da bi sua\n"
                "  trong file: %s\n  tinh lai  : %s"
                % (doc[HASH_FIELD], digest)
            )
        cls._check_content(content)
        return cls(content)

    def save(self, path) -> str:
        """Write canonical content plus a sibling hash (never a self-hash)."""
        self._check_content(self._c)
        digest = self.content_sha256
        C.atomic_json(Path(path), {"content": self._c, HASH_FIELD: digest})
        return digest

    @property
    def content_sha256(self) -> str:
        return C.sha256_bytes(C.canonical_json(self._c).encode("utf-8"))

    def floor_for(self, column: str) -> float:
        for suffix, value in self.floors["by_suffix"].items():
            if column.endswith(suffix):
                return float(value)
        return float(self.floors["other"])

    def _vectors(self, columns):
        low = np.array([self.bounds[column]["min"] for column in columns], dtype=float)
        high = np.array(
            [self.bounds[column]["max"] for column in columns], dtype=float
        )
        scale = np.maximum(
            high - low, [self.floor_for(column) for column in columns]
        )
        return low, high, scale

    @staticmethod
    def _matrix(frame: pd.DataFrame, columns):
        """Select by artifact name/order, making input order irrelevant."""
        return (
            frame[columns]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .to_numpy(dtype=float)
        )

    def _score_family(self, frame: pd.DataFrame, name: str):
        columns = self.families[name]
        low, high, scale = self._vec[name]
        values = self._matrix(frame, columns)
        with np.errstate(invalid="ignore"):
            violations = (values < low) | (values > high)
            amount = np.maximum.reduce(
                [low - values, values - high, np.zeros_like(values)]
            ) / scale
        return (
            violations.sum(axis=1).astype("int32"),
            np.nansum(amount, axis=1),
            np.isfinite(values).all(axis=1),
        )

    def score_batch(self, frame: pd.DataFrame) -> Decision:
        self.validate_schema(frame.columns)
        k, excess, judgeable = self._score_family(frame, "primary")
        k_indicator, _, _ = self._score_family(frame, "indicator")
        k_rate, _, _ = self._score_family(frame, "rate_shared")
        return Decision(
            k=k,
            excess=excess,
            judgeable=judgeable,
            k_indicator=k_indicator,
            k_rate=k_rate,
            suspect=self.suspect_from(excess, judgeable),
            act=self.act_from(k_indicator, k_rate, judgeable),
        )

    def suspect_from(self, excess, judgeable) -> np.ndarray:
        """Decision rule uses strict ``excess > E`` and masks unknown rows."""
        threshold = float(self.thresholds["primary"]["E"])
        return np.asarray(judgeable, dtype=bool) & (
            np.asarray(excess, dtype=float) > threshold
        )

    def act_from(self, k_indicator, k_rate, judgeable) -> np.ndarray:
        """Dual action rule is OR across indicator and shared-rate families."""
        indicator_threshold = int(self.thresholds["indicator"]["K"])
        rate_threshold = int(self.thresholds["rate_shared"]["K"])
        return np.asarray(judgeable, dtype=bool) & (
            (np.asarray(k_indicator) > indicator_threshold)
            | (np.asarray(k_rate) > rate_threshold)
        )
