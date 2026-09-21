"""Known-answer test cho mo phong 8.2.

Moi con so ky vong deu duoc dan ra bang phep tinh tay trong docstring; sim chi
duoc coi la dung khi no TAI TAO dung phep tinh do.
"""
from pathlib import Path

import pytest

from controller.policy import PolicyParams
from controller.sim import (
    SimParams,
    always,
    never,
    poisson_schedule,
    run,
    run_bangbang,
    window,
)

ROOT = Path(__file__).resolve().parents[1]


def test_sim_khop_tinh_tay_voi_flood_lien_tuc():
    """Flood lien tuc 600 s, T0=15, Tmax=110, W=14.

    Lich giu : 15, 30, 60, 110, 110, 110, ...
    Phat hien: d_obs 1.433 s + n_act 2 tick -> inject o t=3.
    Moi probe that bai ton ~9 s (cooldown 8 + d_obs + n_act) chu KHONG ton
    tron W=14, vi `act` quay lai TRUOC khi het cua so.
      inject 3 -> revert 18 -> inject 27 -> revert 57 -> inject 66 ->
      revert 126 -> inject 135 -> revert 245 -> inject 254 -> revert 364 ->
      inject 373 -> revert 483 -> inject 492   => 7 mitigation, 13 hanh dong
    Gay hai = 3 (truoc lan dau) + 6 probe x ~9 s ~= 58 s / 600 s ~= 9.7%

    DINH CHINH MO HINH o 8.8: can thiep thu 7 (inject o t=492) van CON MO luc
    het chan troi. Ban sim niem phong o 8.2 cat ngang no ma khong go, nen no
    dem 13. He THAT bat buoc phai go khi tat (ControlRunner.shutdown) - neu
    khong, mang ket o 7 Mbps voi mot ban ghi can thiep khong ai so huu. Vi vay
    can dung la 13 + 1 = 14, va do la dung con so do live o 8.7. Cai sai la
    SIM, khong phai he. Hai nhanh duoi day khoa ca hai phia cua ban sua.
    """
    res = run(always, 600.0, PolicyParams(t0_s=15, t_max_s=110, probe_w_s=14))
    assert res.n_mitigations == 7
    assert res.n_actions == 14, "phai co them revert cua tat em"
    assert res.n_shutdown_reverts == 1
    old = run(always, 600.0, PolicyParams(t0_s=15, t_max_s=110, probe_w_s=14),
              sim_params=SimParams(graceful_shutdown_revert=False))
    assert old.n_actions == 13, "phai tai lap duoc con so da niem phong o 8.2"
    assert res.harm_s == 58.0
    assert 0.05 < res.harm_fraction < 0.15
    assert res.max_open_s <= 110.0


def test_binh_thuong_khong_co_hanh_dong_nao():
    """C6 nhanh thu hai: 10 phut binh thuong -> 0 hanh dong, 0 mu."""
    res = run(never, 600.0)
    assert res.n_actions == 0
    assert res.blind_s == 0.0


def test_khong_bao_gio_giu_qua_lease():
    """Bat bien an toan: khong khoang giu nao cham MAX_OPEN_S = 120 s."""
    from ml.intervention_log import MAX_OPEN_S

    for horizon in (600.0, 1800.0):
        res = run(always, horizon)
        assert res.max_open_s < MAX_OPEN_S - 5.0


def test_circuit_breaker_tot_hon_bang_bang():
    """Doi chung tren CUNG mot mo hinh, khong so voi con so tuong tuong."""
    cb = run(always, 600.0)
    bb = run_bangbang(always, 600.0)
    assert bb.n_actions > 5 * cb.n_actions
    assert bb.harm_fraction > 4 * cb.harm_fraction


def test_flood_ngan_thi_mot_chu_ky_la_du():
    """Flood 20 s: mot lan giam thieu, sau do probe sach -> IDLE."""
    res = run(window(10.0, 30.0), 200.0)
    assert res.n_mitigations == 1
    assert res.n_reverts == 1
    assert res.timeline[-1][1] == "revert"


def test_tai_lap_duoc_theo_seed():
    schedule_a, spans_a = poisson_schedule(4242, 1800.0)
    schedule_b, spans_b = poisson_schedule(4242, 1800.0)
    assert spans_a == spans_b
    assert run(schedule_a, 1800.0).as_dict() == run(schedule_b, 1800.0).as_dict()


def test_ket_qua_khong_doi_theo_an_so_93():
    """An so 9.3: detector bao `normal` hay `suppressed` luc dang giam thieu.

    Thiet ke go THEO LICH nen ca hai kich ban phai cho cung so hanh dong.
    Day la ly do an so do khong can tra loi truoc khi viet runtime.
    """
    a = run(always, 600.0, sim_params=SimParams(suppressed_during_mitigation=True))
    b = run(always, 600.0, sim_params=SimParams(suppressed_during_mitigation=False))
    assert a.n_actions == b.n_actions
    assert a.harm_s == b.harm_s


def test_hysteresis_manh_hon_van_dao_dong():
    """Phan 3: tang release_m chi KEO DAI chu ky, khong cat duoc limit cycle."""
    base = run_bangbang(always, 600.0, SimParams(release_m=3))
    longer = run_bangbang(always, 600.0, SimParams(release_m=10))
    assert longer.n_actions < base.n_actions      # cham hon
    assert longer.n_actions > 20                  # nhung VAN dao dong nhieu


def test_sim_moi_hang_so_co_receipt():
    """Ky luat: khong bia so. Moi field cua SimParams phai co dong receipt."""
    source = (ROOT / "controller/sim.py").read_text(encoding="utf-8")
    for receipt in ("detector-release-1.0.0.json",
                    "phase7_e2e_latency.json",
                    "latency_command_randomized.json",
                    "TICK_INTERVAL_MS"):
        assert receipt in source, "thieu trich dan receipt: %s" % receipt


def test_sim_khong_random_trong_vong():
    """Ngau nhien chi duoc nam o ham SINH lich, khong nam trong run()."""
    source = (ROOT / "controller/sim.py").read_text(encoding="utf-8")
    body = source.split("def run(", 1)[1].split("def poisson_schedule", 1)[0]
    for forbidden in ("import random", "rng.", "random.", "time."):
        assert forbidden not in body, "run() khong duoc chua: %s" % forbidden
