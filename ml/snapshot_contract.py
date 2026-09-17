#!/usr/bin/env python3
"""Snapshot type contract at the scorer trust boundary.

Uncertain values become unmeasured values.  Every repair is returned to the
caller for audit, and the caller's object is never mutated.
"""
from __future__ import annotations

import copy
import math


BOOL_FLAGS = ("rateValid", "qdiscValid")
NUMERIC_PROPS = (
    "rxRate",
    "txRate",
    "lossPct",
    "qdiscDropDelta",
    "qdiscSentDelta",
    "interfaceLossPct",
    "bwMbps",
)
STATES = ("up", "down", "unknown")


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def sanitize(snapshot: dict) -> tuple[dict, list[str]]:
    """Return a deep-copied clean snapshot and all contract violations."""
    clean = copy.deepcopy(snapshot)
    violations: list[str] = []
    for thing_id, thing in (clean.get("things") or {}).items():
        features = (thing or {}).get("features") or {}
        for feature_name, feature_value in features.items():
            if not isinstance(feature_value, dict):
                continue
            properties = feature_value.get("properties", feature_value)
            if not isinstance(properties, dict):
                continue
            for flag in BOOL_FLAGS:
                if flag in properties and not isinstance(properties[flag], bool):
                    violations.append(
                        "%s.%s.%s=%r"
                        % (thing_id, feature_name, flag, properties[flag])
                    )
                    properties[flag] = False
            for prop in NUMERIC_PROPS:
                if (
                    prop in properties
                    and properties[prop] is not None
                    and not _finite_number(properties[prop])
                ):
                    violations.append(
                        "%s.%s.%s=%r"
                        % (thing_id, feature_name, prop, properties[prop])
                    )
                    properties[prop] = None
            if "state" in properties and properties["state"] not in STATES:
                violations.append(
                    "%s.%s.state=%r"
                    % (thing_id, feature_name, properties["state"])
                )
                properties["state"] = "unknown"
            if (
                properties.get("qdiscValid") is False
                and properties.get("lossPct") is not None
            ):
                violations.append(
                    "%s.%s.lossPct co so khi qdiscValid=False"
                    % (thing_id, feature_name)
                )
                properties["lossPct"] = None
    return clean, violations
