#!/usr/bin/env python3
"""Residual bảo toàn lưu lượng tại mỗi switch (tầng quan hệ detector).

Hướng được đọc từ ``twin.link_direction.UPSTREAM_OF_CORE``. Không fill NaN:
thiếu một counter làm residual không judgeable, không biến thành normal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


RATE_FLOOR_BPS = 1.0e4


def link_column(key: str, prop: str) -> str:
    return f"link-{key}.traffic.{prop}"


def incidence(
    direction: dict[str, tuple[str, str]], switches: list[str]
) -> dict[str, list[tuple[str, str]]]:
    """Return deterministic ``{switch: [(column, in|out)]}`` incidence."""
    unknown = set(switches) - {
        node for pair in direction.values() for node in pair
    }
    if unknown:
        raise ValueError(
            "switch khong co link nao trong ban do huong: %s" % sorted(unknown)
        )
    table: dict[str, list[tuple[str, str]]] = {}
    for key in sorted(direction):
        upstream, downstream = direction[key]
        for node in (upstream, downstream):
            if node not in switches:
                continue
            rows = table.setdefault(node, [])
            if node == upstream:
                rows.append((link_column(key, "txRate"), "out"))
                rows.append((link_column(key, "rxRate"), "in"))
            else:
                rows.append((link_column(key, "txRate"), "in"))
                rows.append((link_column(key, "rxRate"), "out"))
    return {switch: sorted(rows) for switch, rows in sorted(table.items())}


def required_columns(inc: dict) -> list[str]:
    return sorted({column for rows in inc.values() for column, _ in rows})


def residuals(
    frame: pd.DataFrame, inc: dict, floor: float = RATE_FLOOR_BPS
) -> pd.DataFrame:
    """Compute ``r(S)=(sum_in-sum_out)/max(sum_in,floor)`` per switch."""
    missing = [column for column in required_columns(inc) if column not in frame]
    if missing:
        raise ValueError("thieu cot conservation: %s" % missing[:4])
    output = {}
    for switch, rows in inc.items():
        inflow = np.zeros(len(frame))
        outflow = np.zeros(len(frame))
        for column, side in rows:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(
                dtype=float
            )
            values = np.where(np.isfinite(values), values, np.nan)
            if side == "in":
                inflow = inflow + values
            else:
                outflow = outflow + values
        output["r." + switch] = (inflow - outflow) / np.maximum(inflow, floor)

    result = pd.DataFrame(output, index=frame.index)
    matrix = result.to_numpy()
    result["judgeable"] = np.isfinite(matrix).all(axis=1)
    finite_or_low = np.where(np.isfinite(matrix), matrix, -np.inf)
    result["r_max"] = np.where(
        result["judgeable"], np.max(finite_or_low, axis=1), np.nan
    )
    names = np.array([column[2:] for column in output])
    result["argmax_switch"] = np.where(
        result["judgeable"], names[np.argmax(finite_or_low, axis=1)], None
    )
    return result


def alarm(residual_frame: pd.DataFrame, threshold: float) -> np.ndarray:
    """One-sided strict alarm. Negative residual alone never alarms."""
    with np.errstate(invalid="ignore"):
        return (
            residual_frame["judgeable"]
            & (residual_frame["r_max"] > threshold)
        ).to_numpy()


def saturation_ratio(
    offered_bps: float, baseline_mbps: float, factor: float
) -> float:
    """Return rho using LinkDegrade's 1 Mbps capacity floor."""
    new_bw_mbps = max(1.0, baseline_mbps * (1.0 - factor))
    return float(offered_bps) / (new_bw_mbps * 1e6 / 8.0)
