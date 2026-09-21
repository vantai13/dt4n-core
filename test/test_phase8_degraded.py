#!/usr/bin/env python3
"""Bien ket cuc BEN voi hien tuong dem (no 8.6, tra o 8.8).

Bai test quan trong nhat la cai dau: no dung MOT chuoi tick co dung hinh dang
da lam hong phep do 8.6 - tut sau roi vot cao - va kiem rang TRUNG BINH bi lua
con DEM TICK thi khong.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from measurements import degraded  # noqa: E402


def tick(t, value, host="h3", valid=True):
    return {"t_wall": float(t), "host": host, "tx_mbps": float(value),
            "rx_mbps": 0.0, "rate_valid": valid}


def test_trung_binh_bi_lua_nhung_dem_tick_thi_khong():
    """Hinh dang da lam hong 8.6: 4 tick tut ve 0.2, roi 4 tick vot 4.1.

    Trung binh trong su co = (4*0.2 + 4*4.1)/8 = 2.15 = DUNG muc nen 2.15, nen
    mot phep do dua tren trung binh se ket luan "khong co thiet hai". Dem tick
    thay 4/8 tick nam duoi san.
    """
    rows = [tick(t, 2.15) for t in range(0, 10)]                 # nen
    rows += [tick(10 + i, 0.2) for i in range(4)]                # tut
    rows += [tick(14 + i, 4.1) for i in range(4)]                # vot
    rows += [tick(20 + t, 2.15) for t in range(10)]              # nen lai
    spans = [(10.0, 18.0)]

    result = degraded.fraction(rows, spans, "h3")
    mean_inside = result["mean_mbps_inside"]
    assert abs(mean_inside - 2.15) < 0.01, "tien de sai: trung binh phai bao hoa"
    assert result["baseline_mbps"] == 2.15
    assert result["floor_mbps"] == 1.075
    assert result["n_degraded"] == 4
    assert result["fraction"] == 0.5


def test_nen_lay_TRUNG_VI_nen_mot_burst_khong_keo_san_len():
    rows = [tick(t, 2.0) for t in range(0, 9)] + [tick(9, 90.0)]
    assert degraded.baseline(rows, [], "h3") == 2.0


def test_nen_lay_NGOAI_khoang_su_co():
    rows = [tick(t, 2.0) for t in range(0, 5)]
    rows += [tick(5 + t, 0.1) for t in range(5)]       # trong su co
    assert degraded.baseline(rows, [(5.0, 10.0)], "h3") == 2.0


def test_tick_khong_hop_le_bi_BO_khong_thay_bang_0():
    """rateValid == false sau khi doi bw (F8-6) - thay bang 0 se PHAT nhanh
    co controller, dung loi ma primary_definition cua 8.6 da chan."""
    rows = [tick(t, 2.0) for t in range(0, 10)]
    rows += [tick(10, 0.0, valid=False), tick(11, 2.0)]
    result = degraded.fraction(rows, [(10.0, 12.0)], "h3")
    assert result["n_invalid"] == 1
    assert result["n_valid"] == 1
    assert result["n_degraded"] == 0


def test_khong_co_tick_nao_trong_su_co_thi_tra_None_khong_tra_0():
    rows = [tick(t, 2.0) for t in range(0, 5)]
    result = degraded.fraction(rows, [(100.0, 200.0)], "h3")
    assert result["fraction"] is None


def test_ty_le_luon_kem_mau_so():
    rows = [tick(t, 2.0) for t in range(0, 10)] + [tick(10, 0.1)]
    result = degraded.fraction(rows, [(10.0, 11.0)], "h3")
    assert result["n_valid"] == 1 and result["fraction"] == 1.0
    assert result["baseline_mbps"] is not None and result["floor_mbps"] is not None
