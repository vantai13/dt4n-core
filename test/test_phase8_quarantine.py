"""Hoi quy: sau probe_target_changed, controller KHONG duoc nham nan nhan.

Lo hong (tim ra khi dong Phase 8): prereg 8.1 quy dinh LATCH muc tieu cho
ca episode, nhung policy cu chi fail-closed dung MOT tick roi quay ve IDLE;
tick act ke tiep co ung vien duy nhat (nan nhan dang recovery burst) ->
inject vao nan nhan.
"""
from controller.policy import ControllerState, DetectorView, PolicyParams, decide

ROLES = (
    ("h1", "client"),
    ("h2", "client"),
    ("h3", "client"),
    ("srv1", "server"),
    ("srv2", "server"),
)
P = PolicyParams()


def view(state, hosts=(), cause="", seq=1):
    affected = tuple("org.dt4n:host-" + h for h in hosts)
    return DetectorView(state, cause, affected, ROLES, True, "b", seq)


def probing_on_h1(now):
    """Dua controller toi PROBING voi muc tieu h1 (di dung duong that)."""
    cs = ControllerState()
    _, cs = decide(view("act", ["h1"]), cs, now, P)
    _, cs = decide(view("normal"), cs, now + P.t0_s, P)  # het gio -> revert
    assert cs.mode == "PROBING" and cs.target == "h1"
    return cs, now + P.t0_s


def test_burst_nan_nhan_khong_bi_gioi_han():
    cs, t = probing_on_h1(0.0)
    injected = []
    # recovery burst cua h3: 3 tick act lien tiep, chi h3 trong affected
    for k in range(1, 4):
        actions, cs = decide(view("act", ["h3"], seq=k), cs, t + k, P)
        injected += [a.link for a in actions if a.kind == "inject"]
    assert injected == [], "nham nan nhan: %s" % injected
    assert cs.mode == "IDLE" and cs.reason == "idle_quarantine"


def test_cach_ly_het_han_thi_hanh_dong_binh_thuong():
    cs, t = probing_on_h1(0.0)
    _, cs = decide(view("act", ["h3"]), cs, t + 1, P)  # doi muc tieu
    end = cs.window_end_mono
    assert end == t + 1 + P.probe_w_s
    actions, cs = decide(view("act", ["h3"]), cs, end - 0.001, P)
    assert actions == ()
    actions, cs = decide(view("act", ["h3"]), cs, end, P)  # het cach ly
    assert [a.link for a in actions] == ["h3-s1"]


def test_cach_ly_bi_xoa_khi_quiet_qua_han():
    cs, t = probing_on_h1(0.0)
    _, cs = decide(view("act", ["h3"]), cs, t + 1, P)
    _, cs = decide(view("normal"), cs, t + 1 + P.probe_w_s + 1, P)
    assert cs.window_end_mono is None and cs.mode == "IDLE"


def test_idle_binh_thuong_khong_bi_anh_huong():
    """IDLE luon co window_end_mono = None -> nhanh cu giu nguyen tung bit."""
    actions, cs = decide(view("act", ["h1"]), ControllerState(), 5.0, P)
    assert [a.link for a in actions] == ["h1-s1"]
