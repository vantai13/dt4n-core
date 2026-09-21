#!/usr/bin/env python3
"""Cac bat bien khoa o Lesson 8.8 (soat lai 8.7 + nghiem thu).

Bon nhom, moi nhom mot bai hoc phai tra gia moi co:
  1. sim phai mo hinh hoa TAT EM  -> can C6-a dung la 14, va no TIEN DOAN duoc
  2. MOT dinh nghia `gap` duy nhat -> hai receipt phai tinh lai ra dung so cu
  3. ban ghi vo chu phai duoc DONG -> neu khong, N15 tat controller vinh vien
  4. quy ket S11 bang t_source    -> khong con hang so tru tay nao
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.audit import read_rows  # noqa: E402
from controller.sim import SimParams, always, run  # noqa: E402
from measurements import attribution, blind_time  # noqa: E402


# ------------------------------------------- 0. C11 dung cua so da dang ky


def test_c11_soak_loai_300_giay_warmup_truoc_cua_so_30_phut():
    """Phase 7 S6 v2 đo [300, 2100], không phải [0, 1800].

    Lỗi harness 8.8 ban đầu tự nhận ``comparable_to_phase7`` nhưng lại chấm
    ngay từ t=0. Test này khóa đúng đại lượng đã đăng ký, không đổi ngưỡng.
    """
    from scripts.run_phase8_soak import measurement_window

    series = [(0.0, 100), (299.9, 900), (300.0, 1000),
              (1800.0, 1300), (2100.0, 1500), (2100.1, 9999)]
    assert measurement_window(series, 300.0, 1800.0) == [
        (300.0, 1000), (1800.0, 1300), (2100.0, 1500)]


def test_readiness_production_khong_phu_thuoc_timeline():
    """Timeline tắt là cấu hình production, không phải detector chưa sẵn sàng."""
    from collections import deque
    from scripts.phase7_live_common import Live

    class Runner:
        timeline = deque(maxlen=0)
        published = "normal"

    live = object.__new__(Live)
    live.runner = Runner()
    assert live.wait_published("normal", calm_ticks=2, timeout_s=1.0)


# ------------------------------------------------------- 1. can C6-a = 13 + 1

SEALED_SIM = ROOT / "results/report/phase8_sim_predictions.json"


def test_sim_khong_tat_em_tai_lap_dung_con_so_da_niem_phong():
    """Rao #3 cua PASS-with-model-correction: ban va phai TAI LAP duoc ban cu.

    Neu tat `graceful_shutdown_revert` ma khong ra dung 13, thi thay doi cua
    8.8 da dong cham vao thu khac ngoai tat em -> ban sua khong con la mot
    dinh chinh don le nua.
    """
    sealed = json.loads(SEALED_SIM.read_text(encoding="utf-8"))["content"]
    result = run(always, 600.0, sim_params=SimParams(graceful_shutdown_revert=False))
    assert result.n_actions == sealed["modes"]["continuous_flood_600s"]["n_actions"] == 13
    assert result.n_mitigations == 7 and result.n_reverts == 6


def test_sim_co_tat_em_du_doan_dung_14_khong_phai_lon_hon_13():
    """KNOWN-ANSWER TEST cho chinh ban va (rao #3).

    Tieu chi phai la DUNG 14, khong duoc la ">= 13": mot can noi long thi
    khong con tien doan gi ca, va do la dung cai ma rao #2 cam.
    """
    result = run(always, 600.0)
    assert result.n_actions == 14
    assert result.n_shutdown_reverts == 1
    assert result.n_mitigations == 7 and result.n_reverts == 7


def test_can_moi_bang_can_cu_cong_dung_mot():
    old = run(always, 600.0, sim_params=SimParams(graceful_shutdown_revert=False))
    assert run(always, 600.0).n_actions == old.n_actions + 1


def test_quiet_khong_sinh_them_hanh_dong_nao():
    """Tat em chi phat revert khi CON can thiep mo. Quiet van phai la 0."""
    from controller.sim import never

    assert run(never, 600.0).n_actions == 0


# ------------------------------------------------------- 2. mot dinh nghia gap

AB_AUDIT = "logs/phase8_ab/*/ab_A_b*_i*.jsonl"
STAB_AUDIT = "logs/phase8_stability/flood_*/run_00.jsonl"


def _rows(pattern):
    paths = sorted(glob.glob(str(ROOT / pattern)))
    if not paths:
        pytest.skip("khong co audit %s trong cay lam viec nay" % pattern)
    return paths


def test_gap_cua_stability_tinh_lai_bang_ham_chung_ra_dung_receipt():
    receipt = json.loads(
        (ROOT / "results/report/phase8_stability_flood.json").read_text("utf-8")
    )["content"]["runs"][0]
    rows = read_rows(_rows(STAB_AUDIT)[0])
    paired = blind_time.pairs(rows)
    assert [round(g, 2) for g in blind_time.gaps(paired)] == receipt["gaps_s"]
    assert [round(h, 1) for h in blind_time.holds(paired)] == receipt["holds_s"]


def test_gap_cua_ab_tinh_lai_bang_ham_chung_ra_dung_receipt():
    receipt = json.loads(
        (ROOT / "results/report/phase8_ab_addendum.json").read_text("utf-8")
    )["content"]["question_2_protection"]["gap_revert_to_next_inject_s"]
    values = []
    for path in _rows(AB_AUDIT):
        values += blind_time.gaps(blind_time.pairs(read_rows(path)))
    assert round(statistics.fmean(values), 2) == receipt["mean"]
    assert round(min(values), 2) == receipt["min"]
    assert round(max(values), 2) == receipt["max"]


def test_hai_receipt_dung_CHUNG_mot_ham_nen_chenh_lech_la_VAT_LY():
    """Chot lai ket luan: 2.31 s vs 11.0 s khong phai loi dinh nghia.

    Test nay ton tai de khong ai "giai thich lai" bang gia thuyet dinh nghia
    mot lan nua: ca hai da di qua dung mot ham roi.
    """
    stab = blind_time.gaps(blind_time.pairs(read_rows(_rows(STAB_AUDIT)[0])))
    ab = [g for p in _rows(AB_AUDIT)
          for g in blind_time.gaps(blind_time.pairs(read_rows(p)))]
    assert set(round(g, 2) for g in stab) == {11.0}
    assert max(ab) <= 5.0


def test_gap_bo_qua_cap_chua_dong():
    paired = [
        {"key": "a", "t_inject": 0.0, "t_revert": None, "hold_s": None},
        {"key": "b", "t_inject": 100.0, "t_revert": 110.0, "hold_s": 10.0},
    ]
    assert blind_time.gaps(paired) == []


# ------------------------------------ 3. ban ghi vo chu -> N15 tat vinh vien

from ml.blast_radius import Routing  # noqa: E402
from ml.intervention_log import InMemoryInterventionLog, Intervention  # noqa: E402


class _Twin:
    def __init__(self, bw):
        self._bw = bw

    def observed_bw(self):
        return dict(self._bw)

    def roles(self):
        return {"h1": "client", "h2": "client", "h3": "client",
                "srv1": "server", "srv2": "server"}

    def detector_view_fields(self):
        return {"state": "normal", "cause": "", "affected": (), "fresh": True,
                "boot_id": "b", "seq": 1, "release_sha256": ""}


def _runner(bw, log, tmp_path):
    from controller.locked_log import LockedInterventionLog
    from controller.runner import ControlRunner

    return ControlRunner(
        _Twin(bw), LockedInterventionLog(log),
        Routing.load(ROOT / "ditto/routing_table.json"),
        send_command=lambda command, cid=None: {"cid": cid, "http_status": 202},
        audit_path=str(tmp_path / "audit.jsonl"),
    )


def _orphan(routing):
    from ml.blast_radius import radius

    return Intervention(
        id="ctl-DEADBEEF-e1-k0:inject", t_start=time.time() - 300.0,
        actor="controller", action="inject:rate_limit",
        targets={"links": ["h1-s1"], "flows": []},
        blast_radius=frozenset(radius(routing, {"links": ["h1-s1"], "flows": []})),
        routing_sha256=routing.sha256,
    )


def test_revert_first_phai_dong_ca_so_sach(tmp_path):
    """Sua bw ma khong dong so sach = N15 tat VINH VIEN controller.

    Day la loi #2 cua chaos 8.7 - im lang, vinh vien, va do CHINH mot co che
    an toan gay ra. Mot co che fail-safe phai co duong thoat.
    """
    routing = Routing.load(ROOT / "ditto/routing_table.json")
    log = InMemoryInterventionLog()
    log.append(_orphan(routing))
    assert log.stale_open(time.time()), "tien de sai: chua co ban ghi vo chu"

    runner = _runner({"h1-s1": 7.0, "h2-s1": 20.0, "h3-s1": 20.0}, log, tmp_path)
    runner.bootstrap_safe_state()

    assert log.stale_open(time.time()) == [], "con ban ghi vo chu MO sau bootstrap"
    assert runner.cstate.mode == "IDLE"
    assert runner.stats["orphan_log_closed"] == 1


def test_khong_dong_ban_ghi_cua_CHINH_MINH(tmp_path):
    """Duong thoat khong duoc bien thanh cai gay ra dung van de no chua."""
    routing = Routing.load(ROOT / "ditto/routing_table.json")
    log = InMemoryInterventionLog()
    runner = _runner({"h1-s1": 20.0, "h2-s1": 20.0, "h3-s1": 20.0}, log, tmp_path)
    from ml.blast_radius import radius

    log.append(Intervention(
        id="ctl-x-%s-e1-k0:inject" % runner.boot_id, t_start=time.time(),
        actor="controller", action="inject:rate_limit",
        targets={"links": ["h1-s1"], "flows": []},
        blast_radius=frozenset(radius(routing, {"links": ["h1-s1"], "flows": []})),
        routing_sha256=routing.sha256))
    runner._close_orphan_interventions()
    assert runner.stats["orphan_log_closed"] == 0


def test_stale_intervention_keo_dai_phai_KEU(tmp_path, caplog):
    """Im lang la dac diem te nhat cua loi nay, nen toi thieu phai co tieng."""
    import logging

    from controller.policy import DetectorView
    from controller.runner import STALE_INTERVENTION_STREAK_ALERT

    runner = _runner({"h1-s1": 20.0}, InMemoryInterventionLog(), tmp_path)
    view = DetectorView(state="unknown", cause="stale_intervention", affected=(),
                        roles=(), fresh=True, boot_id="b", seq=1)
    with caplog.at_level(logging.ERROR):
        for _ in range(STALE_INTERVENTION_STREAK_ALERT):
            runner._watch_stale_intervention(view)
    assert any("TAT VINH VIEN" in r.getMessage() for r in caplog.records)
    assert runner.stats["stale_intervention_max_streak"] == \
        STALE_INTERVENTION_STREAK_ALERT

    runner._watch_stale_intervention(
        DetectorView(state="normal", cause="", affected=(), roles=(), fresh=True,
                     boot_id="b", seq=2))
    assert runner._stale_intervention_streak == 0


# --------------------------------------------- 4. quy ket S11 bang t_source


def test_vi_tu_t_source_loai_bo_tick_nhan_qua_di_truoc():
    """Tick co t_source < t_start KHONG the do can thiep gay ra."""
    assert not attribution.in_intervention_window(99.0, 100.0, 120.0)
    assert attribution.in_intervention_window(100.0, 100.0, 120.0)
    assert attribution.in_intervention_window(127.9, 100.0, 120.0)
    assert not attribution.in_intervention_window(128.1, 100.0, 120.0)


def test_vi_tu_dung_lease_khi_chua_dong():
    assert attribution.in_intervention_window(219.0, 100.0, None)
    assert not attribution.in_intervention_window(221.0, 100.0, None)


def test_classify_xep_tick_som_vao_unattributed_khong_phai_loai_I():
    zone = {"org.dt4n:host-h1", "org.dt4n:link-h1-s1"}
    paired = [{"key": "k0", "t_inject": 100.0, "t_revert": 120.0, "hold_s": 20.0}]
    rows = [
        # t_source 99.4 < t_start 100.0 -> nhan qua di truoc
        {"kind": "decision", "t_wall": 101.0,
         "input": {"state": "act", "bootId": "b", "seq": 5,
                   "affected": ["org.dt4n:host-h1"]}},
        # t_source 105 trong cua so, moi entity trong vung -> Loai I THAT
        {"kind": "decision", "t_wall": 106.0,
         "input": {"state": "act", "bootId": "b", "seq": 11,
                   "affected": ["org.dt4n:host-h1"]}},
    ]
    tmap = {("b", 5): 99.4, ("b", 11): 105.0}
    type_i, type_ii, unattributed = attribution.classify(rows, paired, zone, tmap)
    assert len(unattributed) == 1 and unattributed[0]["seq"] == 5
    assert unattributed[0]["t_source_minus_t_start"] == -0.6
    assert len(type_i) == 1 and type_i[0]["seq"] == 11
    assert type_ii == []


def test_classify_entity_ngoai_vung_la_loai_II():
    zone = {"org.dt4n:host-h1", "org.dt4n:link-h1-s1"}
    paired = [{"key": "k0", "t_inject": 100.0, "t_revert": 120.0, "hold_s": 20.0}]
    rows = [{"kind": "decision", "t_wall": 106.0,
             "input": {"state": "act", "bootId": "b", "seq": 11,
                       "affected": ["org.dt4n:host-h1", "org.dt4n:link-s2-s3"]}}]
    type_i, type_ii, _ = attribution.classify(rows, paired, zone, {("b", 11): 105.0})
    assert type_i == [] and len(type_ii) == 1
