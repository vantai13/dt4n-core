#!/usr/bin/env python3
"""Bien ket cuc BEN voi hien tuong dem (no 8.6 -> 8.8).

Van de da do o 8.6: trung binh txRate cua nan nhan BAO HOA o toc do chao cua
luong TCP. Phan tut trong luc bi nghen duoc bu lai bang recovery burst ngay
sau do, nen TRUNG BINH CUA SO hoi ve gan nhu dung muc khong bi dong toi:
nhanh A do 2.1462 Mbps voi CV 0.0466%, gan nhu trung voi h2 chua bi dong
(2.1352). Bien do KHONG phan biet duoc 93% bao ve voi 100%.

Trung binh bu duoc vi no la mot TICH PHAN. Mot vi tu DEM THEO TICK thi khong:
mot tick da tut roi thi khong co burst nao lam no het tut. Vi vay:

    degraded_tick_fraction = #tick DUOI SAN / #tick hop le, trong khoang su co

San duoc lay tu CHINH run do (trung vi cua cac tick NGOAI moi khoang su co),
khong phai mot hang so bia: neu tai nen troi giua cac run thi san troi theo.
"""
from __future__ import annotations

import statistics

FLOOR_RATIO = 0.5    # tut qua mot nua muc nen = suy giam. Khoa TRUOC khi chay.


def baseline(rows, spans, host, field="tx_mbps"):
    """Trung vi cua cac tick hop le NGOAI moi khoang su co. Trung vi, khong
    trung binh: mot burst duy nhat khong duoc phep keo san len."""
    values = [r[field] for r in rows
              if r["host"] == host and r.get("rate_valid")
              and not any(lo <= r["t_wall"] < hi for lo, hi in spans)]
    return statistics.median(values) if values else None


def fraction(rows, spans, host, field="tx_mbps", floor_ratio=FLOOR_RATIO,
             floor=None):
    """Ty le tick suy giam TRONG cac khoang su co.

    Tra ca mau so va san de nguoi doc tu kiem - mot ty le khong co mau so la
    mot con so khong kiem duoc.
    """
    base = floor if floor is not None else baseline(rows, spans, host, field)
    inside = [r for r in rows
              if r["host"] == host and r.get("rate_valid")
              and any(lo <= r["t_wall"] < hi for lo, hi in spans)]
    invalid = sum(1 for r in rows
                  if r["host"] == host and not r.get("rate_valid")
                  and any(lo <= r["t_wall"] < hi for lo, hi in spans))
    if base is None or not inside:
        return {"baseline_mbps": base, "n_valid": len(inside),
                "n_invalid": invalid, "n_degraded": None, "fraction": None,
                "floor_mbps": None, "floor_ratio": floor_ratio}
    threshold = base * floor_ratio
    degraded = sum(1 for r in inside if r[field] < threshold)
    return {
        "baseline_mbps": round(base, 4),
        "floor_mbps": round(threshold, 4),
        "floor_ratio": floor_ratio,
        "n_valid": len(inside),
        "n_invalid": invalid,          # rateValid == false: BO, khong thay bang 0
        "n_degraded": degraded,
        "fraction": round(degraded / len(inside), 4),
        "mean_mbps_inside": round(statistics.fmean(r[field] for r in inside), 4),
    }
