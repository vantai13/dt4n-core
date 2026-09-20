"""Known-answer test cho ke toan thoi gian mu (C12)."""
from measurements.blind_time import (
    COOLDOWN_S, MAX_OPEN_S, intervals, longest, merge, summarise, total,
)


def row(kind, t_wall, iid):
    return {"kind": kind, "t_wall": t_wall,
            "actions": [{"intervention_id": iid}]}


def test_gop_khoang_chong_lan():
    """Quen gop -> dem trung -> ty le co the > 100%."""
    assert merge([(0, 10), (5, 15), (20, 25)]) == [(0, 15), (20, 25)]
    assert total([(0, 10), (5, 15)]) == 15.0
    assert longest([(0, 10), (5, 15), (20, 40)]) == 20.0


def test_cap_dong_ket_thuc_sau_cooldown():
    rows = [row("inject", 100.0, "x:inject"), row("revert", 110.0, "x:revert")]
    assert intervals(rows) == [(100.0, 110.0 + COOLDOWN_S)]


def test_can_thiep_chua_dong_ket_thuc_o_lease():
    """Lease: mot controller chet KHONG duoc bit mat detector mai mai."""
    rows = [row("inject", 100.0, "x:inject")]
    assert intervals(rows) == [(100.0, 100.0 + MAX_OPEN_S)]


def test_ba_con_so_c12():
    rows = [row("inject", 10.0, "a:inject"), row("revert", 30.0, "a:revert"),
            row("inject", 60.0, "b:inject"), row("revert", 70.0, "b:revert")]
    # mu: [10, 38] va [60, 78] = 28 + 18 = 46 s tren cua so 100 s
    result = summarise(rows, 0.0, 100.0, incident_spans=[(10.0, 70.0)])
    assert result["blind_s"] == 46.0
    assert result["c12a_fraction_of_uptime"] == 0.46
    # trong khoang su co [10,70]: mu = [10,38] + [60,70] = 28 + 10 = 38 / 60
    assert result["c12b_fraction_of_incident"] == round(38 / 60, 4)
    assert result["c12c_longest_blind_s"] == 28.0
    assert result["n_spans"] == 2


def test_khong_co_su_co_thi_c12b_la_none():
    rows = [row("inject", 10.0, "a:inject"), row("revert", 20.0, "a:revert")]
    assert summarise(rows, 0.0, 100.0)["c12b_fraction_of_incident"] is None


def test_cat_theo_cua_so():
    rows = [row("inject", -50.0, "a:inject"), row("revert", 10.0, "a:revert")]
    result = summarise(rows, 0.0, 100.0)
    assert result["blind_s"] == 18.0            # [0, 10+8]


def test_bo_qua_dong_khong_phai_can_thiep():
    rows = [{"kind": "decision", "t_wall": 1.0},
            {"kind": "reassert", "t_wall": 2.0, "actions": []},
            row("inject", 10.0, "a:inject")]
    assert len(intervals(rows)) == 1


def test_ham_thuan():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1]
              / "measurements/blind_time.py").read_text(encoding="utf-8")
    for forbidden in ("import time", "open(", "requests", "random"):
        assert forbidden not in source
