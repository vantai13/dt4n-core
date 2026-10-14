"""Test GĐ3.1 — lõi what-if. Mọi con số ở đây tính tay được (ghi ngay cạnh assert).

Không cần Mininet, không cần Ditto. Chạy:
    python3 -m pytest -q test/test_whatif_model.py
"""
import pytest

from ml.design import route_paths
from whatif import model as M

FLOOD = {'op': 'addDemand', 'src': 'h1', 'dst': 'srv1', 'mbps': 50, 'kind': 'udp'}


def keys(hops):
    return tuple(M.canonical(*h) for h in hops)


@pytest.fixture
def s():
    return M.default_state()


# --------------------------------------------------------------------------- định tuyến
def test_duong_di_khop_bang_dinh_tuyen_da_commit(s):
    # ml.design.route_paths đi theo ditto/routing_table.json (bảng Ryu cài lúc mọi link sống)
    for (src, dst), expected in route_paths().items():
        assert keys(M.route(s, src, dst)) == expected


def test_tat_s1_s2_thi_di_vong_qua_s3(s):
    # đúng hiện tượng đo ở F-admin_down-s1-s2 (bài 1.2): s1->s3 tăng, s3->s2 từ 0 lên ~4
    s2 = M.apply(s, {'op': 'disableLink', 'link': 's1-s2'})
    assert M.route(s2, 'h1', 'srv1') == [('h1', 's1'), ('s1', 's3'), ('s3', 's2'), ('s2', 'srv1')]
    assert M.route(s2, 'srv1', 'srv2') == [('srv1', 's2'), ('s2', 's3'), ('s3', 'srv2')]


def test_tat_link_truy_nhap_thi_khong_toi_duoc(s):
    p = M.predict(M.apply(s, {'op': 'disableLink', 'link': 'h2-s1'}))
    assert p['summary']['unreachable'] == ['h2->srv2/tcp']
    assert p['flows']['h2->srv2/tcp']['delivered'] == 0.0
    assert p['flows']['h1->srv1/tcp']['delivered'] == pytest.approx(2.0)


def test_bat_lai_link_thi_ve_nhu_cu(s):
    s2 = M.apply(M.apply(s, {'op': 'disableLink', 'link': 's2-s1'}),
                 {'op': 'enableLink', 'link': 's1-s2'})
    assert M.predict(s2)['links'] == M.predict(s)['links']


# --------------------------------------------------------------------------- tải và mất gói
def test_tai_binh_thuong_khong_mat(s):
    L = M.predict(s)['links']
    assert L['s1->s2']['rho'] == pytest.approx(4 / 20)      # h1 + h3
    assert L['s1->s3']['rho'] == pytest.approx(2 / 20)      # h2
    assert L['s2->s3']['rho'] == pytest.approx(2 / 5)       # nền srv1 -> srv2 qua nút cổ chai
    assert L['s3->s2']['rho'] == 0.0                        # chiều ngược không ai đi
    assert all(v['loss'] == 0.0 for v in L.values())


def test_mot_luong_qua_link_nghen_mat_1_tru_1_chia_rho():
    st = M.default_state(demands=[M.Demand('h1', 'srv1', 30.0, 'udp')])
    p = M.predict(st)
    assert p['links']['h1->s1']['rho'] == pytest.approx(1.5)
    assert p['links']['h1->s1']['loss'] == pytest.approx(1 - 1 / 1.5)
    assert p['flows']['h1->srv1/udp']['delivered'] == pytest.approx(20.0)
    assert p['links']['s1->s2']['load'] == pytest.approx(20.0)  # link sau chỉ thấy cái còn lại


def test_flood_mat_o_link_truoc_lam_giam_tai_link_sau(s):
    p = M.predict(M.apply(s, FLOOD))
    L, F = p['links'], p['flows']
    assert L['h1->s1']['rho'] == pytest.approx(52 / 20)     # tcp 2 + udp 50
    assert L['s1->s2']['load'] == pytest.approx(22.0)       # h1 còn 20 + h3 2
    assert L['s2->srv1']['load'] == pytest.approx(20.0)     # ra khỏi s1->s2 đúng 20
    assert F['h3->srv1/tcp']['delivered'] == pytest.approx(2 * 20 / 22)
    assert F['h2->srv2/tcp']['delivered'] == pytest.approx(2.0)   # đường khác, không bị đụng
    # h3 là TCP đi qua link nghẽn -> con số 1,82 KHÔNG được tin
    assert 'h3->srv1/tcp' in p['summary']['outside_validity']
    assert 'h2->srv2/tcp' not in p['summary']['outside_validity']


def test_bop_h1_xuong_7(s):
    p = M.predict(M.apply_all(s, [FLOOD, {'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}]))
    assert p['links']['s1->s2']['rho'] == pytest.approx((7 + 2) / 20)
    assert p['flows']['h3->srv1/tcp']['delivered'] == pytest.approx(2.0)
    assert p['flows']['h3->srv1/tcp']['outside_validity'] is False
    assert p['flows']['h1->srv1/tcp']['outside_validity'] is True   # cái giá: h1 tự nghẽn


def test_tat_s1_s2_keo_h2_thanh_nan_nhan(s):
    p = M.predict(M.apply_all(s, [FLOOD, {'op': 'disableLink', 'link': 's1-s2'}]))
    L, F = p['links'], p['flows']
    assert L['s1->s3']['load'] == pytest.approx(24.0)        # h1 20 + h3 2 + h2 2
    assert L['s3->s2']['load'] == pytest.approx(22 * 20 / 24)   # đã mất một phần ở s1->s3
    assert L['s3->s2']['rho'] == pytest.approx(22 * 20 / 24 / 5)
    assert F['h2->srv2/tcp']['delivered'] == pytest.approx(2 * 20 / 24)
    assert F['h2->srv2/tcp']['outside_validity'] is True


def test_bao_toan_luu_luong(s):
    # tổng gửi − tổng tới đích = tổng bị bỏ ở mọi chặng; không chặng nào mang quá dung lượng
    for actions in ([], [FLOOD], [FLOOD, {'op': 'disableLink', 'link': 's1-s2'}],
                    [{'op': 'setBandwidth', 'link': 's2-s3', 'mbps': 1}]):
        p = M.predict(M.apply_all(s, actions))
        dropped = sum(v['load'] - min(v['load'], v['capacity']) for v in p['links'].values())
        assert p['summary']['lost_mbps'] == pytest.approx(dropped)
        for v in p['links'].values():
            assert min(v['load'], v['capacity']) <= v['capacity'] + 1e-9


# --------------------------------------------------------------------------- so sánh và lỗi
def test_compare_danh_dau_nan_nhan_moi(s):
    r = M.compare(M.apply(s, FLOOD), M.DEMO_OPTIONS)
    assert set(r) == {'không làm gì', 'setBandwidth h1-s1 = 7', 'disableLink s1-s2'}
    assert r['không làm gì']['new_victims'] == []
    assert 'h2->srv2/tcp' in r['disableLink s1-s2']['new_victims']
    assert 'h2->srv2/tcp' not in r['setBandwidth h1-s1 = 7']['new_victims']


def test_apply_khong_sua_state_goc(s):
    before = (dict(s.capacity), set(s.down), list(s.demands))
    M.apply_all(s, [FLOOD, {'op': 'disableLink', 'link': 's1-s2'},
                    {'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}])
    assert (s.capacity, s.down, s.demands) == before


@pytest.mark.parametrize('bad', [
    {'op': 'disableLink', 'link': 'h1-s2'},                         # link không tồn tại
    {'op': 'setBandwidth', 'link': 's1-s2', 'mbps': 0},             # băng thông 0
    {'op': 'addDemand', 'src': 'h1', 'dst': 'h1', 'mbps': 1},       # gửi cho chính mình
    {'op': 'addDemand', 'src': 'h1', 'dst': 'srv1', 'mbps': 1, 'kind': 'icmp'},
    {'op': 'addDemand', 'src': 'h1', 'dst': 'srv1', 'mbps': 2, 'kind': 'tcp'},  # trùng luồng
    {'op': 'reboot'},
])
def test_hanh_dong_sai_bi_tu_choi(s, bad):
    with pytest.raises(ValueError):
        M.apply(s, bad)
