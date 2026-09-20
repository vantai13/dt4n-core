#!/usr/bin/env python3
"""C12 - ke toan THOI GIAN MU tu audit cua controller (HAM THUAN).

Mu = co can thiep dang mo, HOAC dang trong cooldown_s sau revert. Doc tu chinh
cap inject/revert (pair_key) - cung nguon ma ml/fsm.py dung de quyet dinh uc che,
nen con so nay la ke toan lai cua CO CHE, khong phai mot uoc luong moi.

Ba con so, khong phai mot: ty le tren TONG thoi gian van hanh nghe nhe nhang gia
tao; ty le tren thoi gian CO SU CO nghe tham hoa gia tao. Cap doi moi la su that.
"""
from __future__ import annotations

COOLDOWN_S = 8.0          # detector-release-1.0.0.json::fsm_params
MAX_OPEN_S = 120.0        # ml/intervention_log.py


def pair_key(intervention_id: str) -> str:
    return intervention_id.rsplit(":", 1)[0]


def intervals(rows, cooldown_s=COOLDOWN_S, max_open_s=MAX_OPEN_S, now=None):
    """[(t_start, t_end)] cho moi can thiep, ke ca cai chua dong (lease).

    `rows` la cac dong audit kind in {inject, revert} co t_wall va
    actions[0].intervention_id. Mot inject KHONG co revert ket thuc dung o
    max_open_s: do la lease, va do cung la cach InterventionLog.active() tinh.
    """
    injects, reverts = {}, {}
    for row in rows:
        if row.get("kind") not in ("inject", "revert"):
            continue
        actions = row.get("actions") or []
        if not actions:
            continue
        key = pair_key(actions[0]["intervention_id"])
        (injects if row["kind"] == "inject" else reverts)[key] = row["t_wall"]
    out = []
    for key, t_start in injects.items():
        closed = reverts.get(key)
        end = (closed + cooldown_s) if closed is not None else (t_start + max_open_s)
        out.append((t_start, end))
    return sorted(out)


def merge(spans):
    """Gop khoang CHONG LAN. Quen buoc nay -> dem trung -> ty le > 100%."""
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def total(spans) -> float:
    return sum(end - start for start, end in merge(spans))


def longest(spans) -> float:
    merged = merge(spans)
    return max((end - start for start, end in merged), default=0.0)


def clip(spans, t0, t1):
    out = []
    for start, end in spans:
        lo, hi = max(start, t0), min(end, t1)
        if hi > lo:
            out.append((lo, hi))
    return out


def summarise(rows, t_start, t_end, incident_spans=(), **kwargs):
    """Ba con so C12.

    incident_spans: cac khoang CO SU CO (vi du flood dang chay), de tinh mau so
    thu hai. Rong -> C12-b khong tinh duoc.
    """
    spans = clip(intervals(rows, **kwargs), t_start, t_end)
    window = max(t_end - t_start, 1e-9)
    blind_s = total(spans)
    incident = merge(clip(list(incident_spans), t_start, t_end))
    incident_s = total(incident)
    blind_in_incident = 0.0
    for lo, hi in merge(spans):
        for a, b in incident:
            blind_in_incident += max(0.0, min(hi, b) - max(lo, a))
    return {
        "window_s": round(window, 3),
        "blind_s": round(blind_s, 3),
        # C12-a: mau so = TONG thoi gian van hanh
        "c12a_fraction_of_uptime": round(blind_s / window, 4),
        # C12-b: mau so = thoi gian CO SU CO
        "c12b_fraction_of_incident": (round(blind_in_incident / incident_s, 4)
                                      if incident_s else None),
        # C12-c: cua so mu dai nhat lien tuc
        "c12c_longest_blind_s": round(longest(spans), 3),
        "incident_s": round(incident_s, 3),
        "n_spans": len(merge(spans)),
    }
