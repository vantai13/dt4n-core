"""Test policy 8.2. An toan nam trong BANG CHUYEN nen test duoc bang liet ke."""
import itertools
from pathlib import Path

import pytest

from controller.policy import (
    ACT,
    LABELS,
    LEASE_MAX_OPEN_S,
    OUT_OF_RANGE,
    QUIET,
    STALE,
    STALE_INTERVENTION,
    SUPPRESSED,
    Action,
    ControllerState,
    DetectorView,
    PolicyParams,
    classify,
    decide,
    desired_bw,
    hold_seconds,
    link_of,
)

ROOT = Path(__file__).resolve().parents[1]
ROLES = (("h1", "client"), ("h2", "client"), ("h3", "client"),
         ("srv1", "server"), ("srv2", "server"))
H1 = "org.dt4n:host-h1"
H2 = "org.dt4n:host-h2"

STATES = ("warming_up", "normal", "suspect", "act", "unknown")
CAUSES = ("", "warmup", "missing_data", "suppressed_intervention",
          "stale_intervention", "out_of_operating_range", "gap", "contract")
MODES = ("IDLE", "MITIGATING", "PROBING", "HOLD")


def view(state="act", cause="", fresh=True, affected=(H1,), seq=1):
    return DetectorView(state, cause, tuple(affected), ROLES, fresh, "b", seq)


def cstate_for(mode, target="h1"):
    return ControllerState(
        mode=mode,
        target=None if mode == "IDLE" else target,
        open_id="x" if mode in ("MITIGATING", "HOLD") else None,
        deadline_mono=1e9 if mode in ("MITIGATING", "HOLD") else None,
        window_end_mono=1e9 if mode == "PROBING" else None,
    )


# ------------------------------------------------------------------ tinh thuan


def test_policy_thuan():
    source = (ROOT / "controller/policy.py").read_text(encoding="utf-8")
    for forbidden in ("import time", "import random", "import requests",
                      "datetime", "uuid", "open(", "Path("):
        assert forbidden not in source, "policy phai THUAN, thay: %s" % forbidden


def test_policy_khong_cham_actuator_topology():
    """Cascade control: doi duong la viec cua vong trong (Ryu), khong phai twin."""
    source = (ROOT / "controller/policy.py").read_text(encoding="utf-8")
    for forbidden in ("disableLink", "enableLink", "disableSwitch",
                      "enableSwitch", "disableHost", "enableHost"):
        assert forbidden not in source, "policy cham actuator topology: %s" % forbidden


def test_id_tat_dinh():
    """C10: goi hai lan cung input -> cung intervention_id."""
    a1, s1 = decide(view(), ControllerState(), 0.0, PolicyParams())
    a2, s2 = decide(view(), ControllerState(), 0.0, PolicyParams())
    assert a1 == a2 and s1 == s2
    assert a1[0].intervention_id == "ctl-b-e1-k0:inject"


def test_state_bat_bien():
    _, s = decide(view(), ControllerState(), 0.0, PolicyParams())
    with pytest.raises(Exception):
        s.mode = "IDLE"


# ------------------------------------------------------------------ tham so


def test_tmax_nho_hon_lease():
    from ml.intervention_log import MAX_OPEN_S

    assert LEASE_MAX_OPEN_S == MAX_OPEN_S
    assert PolicyParams().t_max_s < MAX_OPEN_S - 5.0


def test_tu_choi_tham_so_nguy_hiem():
    with pytest.raises(ValueError):
        PolicyParams(t_max_s=119.0)          # cham lease 120 s
    with pytest.raises(ValueError):
        PolicyParams(probe_w_s=5.0)          # ngan hon tre chet 11.433 s
    with pytest.raises(ValueError):
        PolicyParams(t0_s=0.0)
    with pytest.raises(ValueError):
        PolicyParams(growth=0.5)


def test_lich_backoff():
    params = PolicyParams()
    assert [hold_seconds(params, k) for k in range(6)] == [15, 30, 60, 110, 110, 110]


# ------------------------------------------------------------------ classify


@pytest.mark.parametrize("state,cause", list(itertools.product(STATES, CAUSES)))
def test_freshness_thang_moi_thu(state, cause):
    """THU TU: freshness kiem TRUOC state. Ban tin act het TTL van la ban tin chet."""
    assert classify(view(state, cause, fresh=False)) == STALE


@pytest.mark.parametrize("state,cause", list(itertools.product(STATES, CAUSES)))
def test_classify_luon_tra_nhan_hop_le(state, cause):
    assert classify(view(state, cause)) in LABELS


def test_suspect_gop_vao_quiet():
    """N10 khong the quen: khong co nhan SUSPECT nen khong co duong toi hanh dong."""
    assert classify(view("suspect", "")) == QUIET
    assert classify(view("normal", "")) == QUIET
    assert "SUSPECT" not in LABELS


def test_cause_thang_state():
    assert classify(view("act", "out_of_operating_range")) == OUT_OF_RANGE
    assert classify(view("act", "stale_intervention")) == STALE_INTERVENTION
    assert classify(view("unknown", "suppressed_intervention")) == SUPPRESSED
    assert classify(view("act", "")) == ACT


# ------------------------------------------------------------------ C7 liet ke


@pytest.mark.parametrize(
    "state,cause,fresh,mode",
    list(itertools.product(STATES, CAUSES, (True, False), MODES)),
)
def test_khong_bao_gio_inject_tren_trigger_cam(state, cause, fresh, mode):
    """C7: 0 hanh dong MOI tren moi trigger bi cam - 5x8x2x4 = 320 to hop."""
    actions, _ = decide(view(state, cause, fresh), cstate_for(mode), 0.0, PolicyParams())
    forbidden = (
        (not fresh)
        or cause in ("out_of_operating_range", "stale_intervention")
        or state != "act"
    )
    if forbidden:
        assert not any(a.kind == "inject" for a in actions), (
            "inject tren trigger cam: %s/%s/%s/%s" % (state, cause, fresh, mode)
        )


@pytest.mark.parametrize(
    "state,cause,fresh,mode",
    list(itertools.product(STATES, CAUSES, (True, False), MODES)),
)
def test_moi_hanh_dong_deu_hop_le(state, cause, fresh, mode):
    """Moi Action phat ra phai la inject/revert tren link truy nhap, bw hop le."""
    actions, new = decide(view(state, cause, fresh), cstate_for(mode), 1e12,
                          PolicyParams())
    for action in actions:
        assert isinstance(action, Action)
        assert action.kind in ("inject", "revert")
        assert action.link.endswith("-s1")
        assert action.bw_mbps in (7.0, 20.0)
        assert action.intervention_id.startswith("ctl-")
    assert new.mode in MODES


# ------------------------------------------------------------------ vong doi


def test_vong_doi_day_du():
    params = PolicyParams()
    cs = ControllerState()

    # IDLE -> MITIGATING
    actions, cs = decide(view(), cs, 0.0, params)
    assert actions[0].kind == "inject" and cs.mode == "MITIGATING"
    assert cs.deadline_mono == 15.0 and cs.attempt == 0

    # giu: khong hanh dong du detector bao gi
    for label_view in (view("unknown", "suppressed_intervention"), view("normal")):
        actions, cs = decide(label_view, cs, 10.0, params)
        assert actions == () and cs.mode == "MITIGATING"

    # het gio -> revert -> PROBING
    actions, cs = decide(view("normal"), cs, 15.0, params)
    assert actions[0].kind == "revert" and actions[0].bw_mbps == 20.0
    assert cs.mode == "PROBING" and cs.window_end_mono == 29.0

    # probe that bai -> backoff
    actions, cs = decide(view(), cs, 20.0, params)
    assert actions[0].kind == "inject" and cs.attempt == 1
    assert cs.deadline_mono == 50.0          # 20 + 30

    # het gio lan hai -> PROBING, probe sach -> IDLE, reset k
    _, cs = decide(view("normal"), cs, 50.0, params)
    actions, cs = decide(view("normal"), cs, 64.0, params)
    assert actions == () and cs.mode == "IDLE" and cs.attempt == 0


def test_khong_go_vi_trong_co_ve_khoe():
    """Trai tim cua 8.2: `normal` trong luc dang giam thieu KHONG duoc go."""
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)
    for t in range(1, 15):
        actions, cs = decide(view("normal"), cs, float(t), params)
        assert actions == (), "go som tai t=%d chi vi detector bao normal" % t
    assert cs.mode == "MITIGATING"


def test_n15_revert_khong_tao_moi():
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)
    actions, cs = decide(view("unknown", "stale_intervention"), cs, 5.0, params)
    assert len(actions) == 1 and actions[0].kind == "revert"
    assert cs.mode == "PROBING"


def test_hold_giu_can_thiep_va_van_go_theo_lich():
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)

    actions, cs = decide(view("act", "", fresh=False), cs, 5.0, params)
    assert actions == () and cs.mode == "HOLD" and cs.open_id
    assert desired_bw(cs, params) == {"h1-s1": 7.0}     # van giu can thiep

    actions, cs = decide(view("act", "", fresh=False), cs, 10.0, params)
    assert actions == () and cs.mode == "HOLD"          # chua toi han

    actions, cs = decide(view("act", "", fresh=False), cs, 15.0, params)
    assert actions[0].kind == "revert"                  # lich VAN THANG
    assert cs.mode == "PROBING"


def test_hold_resume_khi_freshness_tro_lai():
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)
    _, cs = decide(view("act", "", fresh=False), cs, 5.0, params)
    actions, cs = decide(view("normal"), cs, 6.0, params)
    assert actions == () and cs.mode == "MITIGATING" and cs.deadline_mono == 15.0


def test_probe_doi_thu_pham_thi_fail_closed():
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)
    _, cs = decide(view("normal"), cs, 15.0, params)      # -> PROBING
    actions, cs = decide(view("act", affected=(H2,)), cs, 20.0, params)
    assert actions == () and cs.mode == "IDLE" and cs.attempt == 0


def test_probe_nhieu_ung_vien_thi_im_lang():
    params = PolicyParams()
    _, cs = decide(view(), ControllerState(), 0.0, params)
    _, cs = decide(view("normal"), cs, 15.0, params)
    actions, cs = decide(view("act", affected=(H1, H2)), cs, 20.0, params)
    assert actions == () and cs.mode == "PROBING"


def test_desired_bw_va_link():
    params = PolicyParams()
    assert desired_bw(ControllerState(), params) == {}
    _, cs = decide(view(), ControllerState(), 0.0, params)
    assert desired_bw(cs, params) == {"h1-s1": 7.0}
    assert link_of("h3") == "h3-s1"


def test_khong_giu_qua_lease():
    """Moi khoang giu deu phai ket thuc truoc MAX_OPEN_S, ke ca o attempt lon."""
    params = PolicyParams()
    assert hold_seconds(params, 99) + params.lease_margin_s <= LEASE_MAX_OPEN_S
