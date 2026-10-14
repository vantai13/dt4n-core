"""Test GĐ1.4 — bộ điều khiển cloud.

Phần lớn test gọi decide() THUẦN (không mạng). Hai test tích hợp:
  - observe() đọc đúng 3 Thing từ một Ditto giả;
  - step() + CloudActuator THẬT trên AWS giả lập (moto): twin chậm -> lệnh lặp là noop.
Chạy:
    python3 -m pytest -q test/test_cloud_controller.py
"""
import importlib
import json

import pytest

from cloud.controller import CState, Obs, Params, decide

P = Params()
MBPS = 1e6 / 8.0                       # 1 Mbps tính ra B/s


def obs(rho=0.1, state='up', desired=0, net_age=1.0, cloud_age=2.0, poll_ok=True):
    """Quan sát giả: ρ của srv1 trên link 20 Mbps."""
    return Obs(srv1_state=state, srv1_rx_Bps=rho * 20 * MBPS, bw_mbps=20,
               net_age_s=net_age, cloud_desired=desired, cloud_healthy=desired,
               cloud_age_s=cloud_age, cloud_poll_ok=poll_ok)


def run_seq(seq, s=None, t0=1000.0, dt=2.0, desired=0, follow=True):
    """Chạy decide() qua một chuỗi quan sát. follow=True: AWS làm theo target ngay."""
    s = s or CState()
    out = []
    for i, kw in enumerate(seq):
        s, target, info = decide(s, obs(desired=desired, **kw), P, t0 + i * dt)
        out.append((target, info))
        if follow and target is not None:
            desired = target
    return s, out, desired


def test_qua_tai_phai_du_3_nhip_lien_moi_them_may():
    _, out, _ = run_seq([{'rho': 0.95}] * 3)
    assert [t for t, _ in out] == [0, 0, 1]


def test_dot_bien_ngan_khong_lam_them_may():
    _, out, _ = run_seq([{'rho': 0.95}, {'rho': 0.95}, {'rho': 0.5}, {'rho': 0.95}])
    assert [t for t, _ in out] == [0, 0, 0, 0]


def test_vung_giua_hai_nguong_giu_nguyen_muc():
    # ρ = 0.5 nằm giữa 0.3 và 0.8: không lên, không xuống (hysteresis)
    s, _, d = run_seq([{'rho': 0.95}] * 3)
    _, out, _ = run_seq([{'rho': 0.5}] * 40, s=s, desired=d, t0=2000)
    assert all(t == 1 for t, _ in out)


def test_bot_may_phai_cho_nhan_lau_va_qua_cooldown():
    s, _, d = run_seq([{'rho': 0.95}] * 3, t0=1000)          # lên 1 máy lúc ~1004
    assert d == 1
    # nhàn 20 nhịp ngay sau đó: đủ n_down nhưng CHƯA qua cooldown 120 s -> giữ 1
    s, out, d = run_seq([{'rho': 0.1}] * 20, s=s, desired=d, t0=1006)
    assert d == 1 and out[-1][1]['code'] == 'cooldown_scale_in'
    # sau cooldown -> được bớt về 0
    _, out, d = run_seq([{'rho': 0.1}], s=s, desired=d, t0=1200)
    assert d == 0


def test_srv1_sap_thi_cloud_bu_va_on_dinh_lai_thi_thoi_bu():
    s, out, d = run_seq([{'state': 'down', 'rho': 0.0}] * 2)
    assert d == 1 and out[-1][1]['failover'] == 1
    s, out, d = run_seq([{'state': 'up', 'rho': 0.2}] * 5, s=s, desired=d, t0=1500)
    assert d == 0 and out[-1][1]['failover'] == 0


def test_qua_tai_roi_srv1_sap_thi_can_hai_may():
    s, _, d = run_seq([{'rho': 0.95}] * 3)
    _, out, d = run_seq([{'state': 'down', 'rho': 0.0}] * 2, s=s, desired=d, t0=1010)
    assert d == 2


def test_luon_bi_kep_tran():
    s = CState(load_level=1, failover_level=1)
    _, target, _ = decide(s, obs(rho=0.95), Params(), 0.0)
    assert target <= 3


@pytest.mark.parametrize('kw,code', [
    ({'net_age': 50.0}, 'hold_stale_net'),
    ({'net_age': None}, 'hold_stale_net'),
    ({'cloud_age': 30.0}, 'hold_stale_cloud'),
    ({'poll_ok': False}, 'hold_stale_cloud'),
    ({'state': 'unknown'}, 'hold_srv1_unknown'),
])
def test_du_lieu_khong_tin_duoc_thi_hold_va_khong_dem_nhip(kw, code):
    s0 = CState(high_streak=2)                 # chỉ còn 1 nhịp nữa là thêm máy
    s1, target, info = decide(s0, obs(rho=0.95, **kw), P, 0.0)
    assert target is None and info['code'] == code
    assert s1 == s0                            # nhịp cũ/không rõ KHÔNG được tính


def test_tuoi_30s_cua_sync_delta_van_duoc_chap_nhan():
    # srv1 đứng yên -> sync agent chỉ đồng bộ toàn phần mỗi ~30 s -> tuổi ~30 s là BÌNH THƯỜNG
    _, target, info = decide(CState(), obs(net_age=31.0), P, 0.0)
    assert target is not None and info['code'] == 'ok'


# ---------------------------------------------------------------------------
# observe(): đọc 3 Thing từ Ditto giả
# ---------------------------------------------------------------------------
class FakeResp:
    def __init__(self, body):
        self.status_code = 200 if body is not None else 404
        self._body = body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, things):
        self.things = things

    def get(self, url, timeout=None):
        return FakeResp(self.things.get(url.rsplit('/', 1)[-1]))


def test_observe_doc_dung_ba_thing_va_tinh_tuoi():
    import time
    from cloud.controller import observe
    now = time.time()
    things = {
        'org.dt4n:host-srv1': {'features': {
            'status': {'properties': {'state': 'up'}},
            'traffic': {'properties': {'rxRate': 2_000_000}},
            'meta': {'properties': {'tSource': now - 3.0}}}},
        'org.dt4n:link-s2-srv1': {'features': {
            'capacity': {'properties': {'bwMbps': 20}}}},
        'org.dt4n:cloud-pool': {'features': {
            'capacity': {'properties': {'desired': 1}},
            'pool': {'properties': {'healthy': 1}},
            'meta': {'properties': {'tSource': now - 4.0, 'pollOk': True}}}},
    }
    o = observe(FakeSession(things))
    assert o.srv1_state == 'up' and o.srv1_rx_Bps == 2_000_000 and o.bw_mbps == 20
    assert o.cloud_desired == 1 and o.cloud_healthy == 1 and o.cloud_poll_ok is True
    assert 2.5 < o.net_age_s < 4.0 and 3.5 < o.cloud_age_s < 5.0


def test_observe_thieu_thing_thi_quyet_dinh_hold():
    from cloud.controller import observe
    o = observe(FakeSession({}))
    _, target, info = decide(CState(), o, P, 0.0)
    assert target is None and info['code'] == 'hold_stale_net'


# ---------------------------------------------------------------------------
# step() + CloudActuator THẬT trên moto: twin chậm -> lệnh lặp lại là noop
# ---------------------------------------------------------------------------
@pytest.fixture
def aws_env(monkeypatch, tmp_path):
    # importorskip TRONG fixture: thiếu moto chỉ bỏ qua các test dùng AWS giả,
    # 17 test decide() thuần ở trên vẫn chạy.
    moto = pytest.importorskip('moto')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_REGION', 'ap-southeast-1')
    monkeypatch.setenv('DT4N_ALLOWED_CIDR', '203.0.113.5/32')
    monkeypatch.setenv('DT4N_CLOUD_STATE', str(tmp_path / 'state.json'))
    with moto.mock_aws():
        import cloud.config
        import cloud.infra
        import cloud.twin
        import cloud.actuator
        import cloud.controller
        for mod in (cloud.config, cloud.infra, cloud.twin, cloud.actuator, cloud.controller):
            importlib.reload(mod)
        cloud.infra.up()
        yield cloud.infra, cloud.actuator, cloud.controller, tmp_path


def test_twin_cham_sau_lenh_thi_lenh_lap_la_noop(aws_env):
    infra, actuator, controller, tmp = aws_env
    act = actuator.CloudActuator(audit_path=tmp / 'act.jsonl', push=None)
    # Twin "đứng hình" ở desired=0 (collector chưa kịp cập nhật) trong khi AWS đã đổi.
    stuck = lambda: obs(rho=0.95, desired=0)   # noqa: E731
    clock = iter(1000.0 + 2 * i for i in range(10))
    ctl = controller.CloudController(act, stuck, audit_path=tmp / 'ctl.jsonl',
                                     push=None, wall=lambda: next(clock))
    outcomes = [ctl.step()[2] for _ in range(4)]
    assert outcomes[0] is None and outcomes[1] is None          # 2 nhịp đầu: đang debounce
    assert outcomes[2]['outcome'] == 'applied'                  # nhịp 3: thêm máy
    assert outcomes[3]['outcome'] == 'noop'                     # twin chậm -> gửi lại -> noop
    assert infra.find_asg(infra.aws('autoscaling'))['DesiredCapacity'] == 1
    rows = [json.loads(x) for x in (tmp / 'ctl.jsonl').read_text().splitlines()]
    assert any(r['action'] and r['action']['outcome'] == 'applied' for r in rows)


def test_dry_run_chi_de_xuat_khong_doi_aws(aws_env):
    infra, actuator, controller, tmp = aws_env
    act = actuator.CloudActuator(audit_path=tmp / 'act.jsonl', push=None, dry_run=True)
    ctl = controller.CloudController(act, lambda: obs(rho=0.95), audit_path=tmp / 'c.jsonl',
                                     push=None)
    results = [ctl.step()[2] for _ in range(3)]
    assert results[2]['outcome'] == 'dry_run'
    assert infra.find_asg(infra.aws('autoscaling'))['DesiredCapacity'] == 0
