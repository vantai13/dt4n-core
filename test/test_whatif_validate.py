"""Test GĐ3.2 — kiểm hồi cứu what-if trên dữ liệu Phase 5 (có sẵn trong repo).

Phần 1 kiểm CÁCH ĐỌC dữ liệu (chiều đo, băng thông kịch bản đặt, lịch tải).
Phần 2 là test HỒI QUY: ghi lại kết luận của 3.2 để ai sửa mô hình/đọc dữ liệu mà làm
kết luận đổi thì test báo ngay. Chạy:
    python3 -m pytest -q test/test_whatif_validate.py
"""
import json

import pytest

from ml import campaign as C
from whatif import validate as V

P5 = C.load_contract(C.ROOT / 'results/report/experiment_matrix.json')
REC = {r['run_id']: r for r in P5['runs']}


def snaps(rid):
    return C.read_snapshots(C.run_paths(rid)['final'])


# --------------------------------------------------------------------------- 1. đọc dữ liệu
def test_bang_thong_degrade_dung_nhu_kich_ban_da_dat():
    # công thức max(1, C0·(1−factor)) phải khớp băng thông twin ghi lại lúc sự cố
    for rid, rec in REC.items():
        if rec.get('fault') in ('degrade', 'shift') and rec['split'] == 'test':
            p = rec['fault_parameters']
            twin = snaps(rid)[30]['things']['link-' + p['link_key']]['features']['capacity']
            assert V.applied_bw(p) == pytest.approx(twin['bwMbps'])


def test_chieu_do_cua_link():
    r = V.directed_rates(snaps('C-load2M-s2001-r1'), V.PRE)
    assert r['s1->s2'] == pytest.approx(4.3, abs=0.2)     # h1 + h3
    assert r['s2->s1'] < 0.5                               # chỉ ACK
    assert r['h1->s1'] == pytest.approx(2.16, abs=0.1)
    assert r['s2->s3'] == pytest.approx(2.16, abs=0.1)     # luồng nền srv1 -> srv2
    assert r['s3->s2'] < 0.5


def test_lich_tai_doi_thi_pha_gia_dinh():
    assert V.demand_changes(REC['C-vary-s2002-r1']) is True
    assert V.demand_changes(REC['C-load2M-s2001-r1']) is False
    assert not any(V.demand_changes(r) for r in REC.values() if r['group'] == 'F')


def test_thoi_gian_day_hang_doi():
    assert V.fill_time_s(2.16, 1.0) == pytest.approx(1000 * 1512 * 8 / 1.16e6)   # ~10,4 s
    assert V.fill_time_s(1.0, 2.0) is None


# --------------------------------------------------------------------------- 2. hồi quy kết luận
@pytest.fixture(scope='module')
def rep():
    return V.validate()


def test_cham_dung_10_run_tap_test(rep):
    assert [r['run_id'] for r in rep['runs']] == P5['split']['test']


def test_trong_vung_hop_le_tai_tung_chieu_gan_nhu_dung(rep):
    s = rep['summary_rates_mbps']['trong']
    assert s['n'] >= 50 and s['max_abs'] <= 0.15


def test_moi_sai_lon_ve_tai_deu_nam_ngoai_vung_hoac_pha_gia_dinh(rep):
    big = [r for run in rep['runs'] for r in run['rates'] if abs(r['err']) >= 0.25]
    assert big and all(r['zone'] != 'trong' for r in big)


def test_nan_nhan_tcp_cua_flood_bi_doan_sai_va_bi_gan_co(rep):
    run = next(r for r in rep['runs'] if r['run_id'] == 'F-flood-h1_to_srv1-s3005-r1')
    h3 = next(r for r in run['rates'] if r['dlink'] == 'h3->s1')
    assert h3['zone'] == 'ngoài' and h3['err'] > 1.0          # đoán ~2,2, đo ~0,4


def test_mat_goi_on_dinh_cua_udp_khop(rep):
    run = next(r for r in rep['runs'] if r['run_id'] == 'F-shift-s1-s2-s3007-r1')
    s23 = next(r for r in run['losses'] if r['link'] == 's2-s3')
    assert s23['zone'] == 'trong' and abs(s23['err_pp']) < 1.0   # 75% = 1 − 5/20


def test_qua_do_hang_doi_giai_thich_ca_lech_degrade_s2_s3(rep):
    run = next(r for r in rep['runs'] if r['run_id'] == 'F-degrade-s2-s3-s3004-r1')
    d = run['post_hoc_diagnostics'][0]
    assert abs(d['first_loss_tick_pred'] - d['first_loss_tick_meas']) <= 1
    assert abs(d['loss_after_fill_meas_pct'] - d['loss_pred_pct']) < 3
