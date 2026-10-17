#!/usr/bin/env python3
"""Ghim các quyết định của Lesson 5.2 bằng test.

Test quan trọng nhất của cả Phase 5 nằm ở đây:
`test_fillna_0_bi_bat_qua_tang` — nếu test này biến mất, một dòng
`.fillna(0)` vô tình sẽ phá toàn bộ Phase 6 mà không ai biết.
"""
import numpy as np
import pandas as pd
import pytest

from ml.flatten import load_many
from ml.missing import (apply_policy, assert_no_fabricated_zero_in_loss,
                        fisher_exact_two_sided, missing_by_profile,
                        mnar_evidence, rate_fabrication_audit, wilson_ci)
from scripts.audit_features import PILOT, ROOT


def _frame(n=6, invalid_ticks=(0,), fault=0, run='r1'):
    """DataFrame tối thiểu có đúng hình dạng snapshot: 1 link, cờ + lý do."""
    rows = []
    for t in range(n):
        bad = t in invalid_ticks
        rows.append({
            'run_id': run, 'profile': 'p', 'tick': t, 'is_fault': fault,
            't_source': 1000.0 + t,
            'link-a-b.traffic.lossPct': None if bad else 0.0,
            'link-a-b.traffic.qdiscValid': not bad,
            'link-a-b.traffic.qdiscReason': 'warmup' if bad else 'ok',
        })
    return pd.DataFrame(rows)


# ------------------------------------------------ bất biến null ≠ 0
def test_fillna_0_bi_bat_qua_tang():
    """Mô phỏng đúng lỗi một dòng: df.fillna(0). Hàm bảo vệ PHẢI nổ."""
    df = _frame()
    df['link-a-b.traffic.lossPct'] = df['link-a-b.traffic.lossPct'].fillna(0)
    with pytest.raises(AssertionError, match='bịa số'):
        assert_no_fabricated_zero_in_loss(df)


def test_bat_bien_van_dung_sau_khi_ap_chinh_sach():
    df = _frame(n=8, invalid_ticks=(0, 5))
    clean, _ = apply_policy(df, warmup_ticks=1)
    assert_no_fabricated_zero_in_loss(clean)
    assert clean['link-a-b.traffic.lossPct'].isna().sum() == 1   # tick 5 VẪN NaN


# ------------------------------------------------------- chính sách
def test_chinh_sach_bo_warmup_nhung_KHONG_bo_dong_giua_run():
    """Phase 7 phải ra quyết định mỗi tick -> tầng 2 không được bỏ dòng."""
    df = _frame(n=10, invalid_ticks=(0, 6))
    clean, rep = apply_policy(df, warmup_ticks=1)
    assert rep['rows_dropped_warmup'] == 1
    assert 6 in clean['tick'].tolist()                  # dòng giữa run CÒN LẠI
    assert rep['rows_with_residual_missing'] == 1


def test_chinh_sach_bo_warmup_theo_TUNG_run_khong_bo_toan_bang():
    a = _frame(n=5, invalid_ticks=(0,), run='r1')
    b = _frame(n=5, invalid_ticks=(0,), run='r2', fault=1)
    clean, rep = apply_policy(pd.concat([a, b], ignore_index=True), warmup_ticks=1)
    assert rep['rows_dropped_warmup'] == 2              # MỖI run một tick
    assert clean.groupby('run_id')['tick'].min().tolist() == [1, 1]


# ------------------------------------------------------- thống kê
def test_wilson_ci_khong_cho_bien_duoi_am():
    """Công thức thường cho [0,0] khi k=0 — tức 'chắc chắn 0%', là SAI."""
    lo, hi = wilson_ci(0, 480)
    assert lo == 0.0 and 0 < hi < 0.02
    naive_lo = 0.0 - 1.96 * np.sqrt(0.0 * 1.0 / 480)
    assert naive_lo == 0.0          # naive sụp về 0, mất hẳn độ bất định
    assert hi > 0.0                 # Wilson vẫn nói "có thể tới 0.8%"


def test_mnar_evidence_bat_duoc_MNAR_khi_thieu_TANG_luc_fault():
    """Fault làm tc timeout -> thiếu dồn vào đúng lúc có sự cố."""
    ok = _frame(n=20, invalid_ticks=(), fault=0, run='n1')
    bad = _frame(n=20, invalid_ticks=tuple(range(5, 18)), fault=1, run='f1')
    bad['link-a-b.traffic.qdiscReason'] = bad['link-a-b.traffic.qdiscReason'].replace(
        'warmup', 'unavailable')
    ev = mnar_evidence(pd.concat([ok, bad], ignore_index=True))
    assert ev['mechanism_identified'] is False
    assert 'unavailable' in ev['reasons_seen']
    assert ev['fisher_p_two_sided'] < 0.001
    assert 'CHƯA KẾT LUẬN' in ev['conclusion']


def test_mnar_evidence_khu_duoc_nhieu_gay_lan_do_dai_run():
    """Run ngắn có tỉ lệ thiếu thô cao hơn CHỈ vì 1 tick warmup chiếm phần lớn.

    Nếu không khử, kết luận 'fault thiếu nhiều hơn' là ảo giác.
    """
    long_n = _frame(n=60, invalid_ticks=(0,), fault=0, run='n1')
    short_f = _frame(n=10, invalid_ticks=(0,), fault=1, run='f1')
    ev = mnar_evidence(pd.concat([long_n, short_f], ignore_index=True))
    assert ev['pct_missing_fault'] > ev['pct_missing_normal']     # thô: LỆCH
    pw = ev['post_warmup']
    assert pw['pct_missing_fault'] == 0.0 and pw['pct_missing_normal'] == 0.0
    assert ev['mechanism_identified'] is True


# --------------------------------------- kênh B: rate bị bịa số 0
def test_kiem_toan_bat_duoc_rate_bia_0_giua_run():
    """rate báo 0 nhưng bộ đếm cộng dồn THẬT có tăng -> bịa."""
    rows = []
    for t in range(5):
        rows.append({'run_id': 'r', 'profile': 'p', 'tick': t, 'is_fault': 0,
                     't_source': 1000.0 + t,
                     'host-h1.traffic.rxBytes': 1000 * (t + 1),
                     'host-h1.traffic.rxRate': 0.0 if t == 3 else 1000.0,
                     'host-h1.traffic.txBytes': 0,
                     'host-h1.traffic.txRate': 0.0})
    out = rate_fabrication_audit(pd.DataFrame(rows))
    assert out['by_kind'].get('zero_but_counter_advanced', 0) == 1
    assert any(f['tick'] == 3 and f['field'] == 'rxRate' for f in out['findings'])


def test_rate_validity_phan_biet_0_that_voi_0_bia():
    """delta = 0 nghĩa là ĐO ĐƯỢC và rate = 0 -> phải valid."""
    from bridge.collector import rate_validity
    assert rate_validity(True, 1.0, (0, 0)) == (True, 'ok')
    assert rate_validity(False, 0, ()) == (False, 'warmup')
    assert rate_validity(True, 1.0, (-1, 5)) == (False, 'counter_reset')
    assert rate_validity(True, 0.0, (1, 1)) == (False, 'nonpositive_dt')


def test_dataset_v2_cu_khong_co_rateValid_va_mask_khong_no():
    """Tương thích ngược: dataset v2 sinh TRƯỚC khi vá vẫn load được."""
    from ml.missing import mask_invalid_rates
    df = load_many({ROOT / p: m for p, m in PILOT.items()})
    assert not any(c.endswith('.rateValid') for c in df.columns)
    out, rep = mask_invalid_rates(df)
    assert rep['total_cells_masked'] == 0
    assert len(out) == len(df)


# -------------------------------------------- dữ liệu pilot THẬT
def test_pilot_that_chi_thieu_do_warmup_o_tick_0():
    df = load_many({ROOT / p: m for p, m in PILOT.items()})
    ev = mnar_evidence(df)
    assert ev['reasons_seen'] == ['warmup']
    assert ev['all_missing_in_run_head'] is True
    assert ev['mechanism_identified'] is True
    assert ev['post_warmup']['pct_missing_fault'] == 0.0


def test_pilot_that_bia_so_0_chi_o_tick_0_khong_o_giua_run():
    """Kênh B trong pilot: 3 file x 5 host x 2 chiều = 30, TẤT CẢ ở tick 0."""
    df = load_many({ROOT / p: m for p, m in PILOT.items()})
    out = rate_fabrication_audit(df)
    assert out['by_kind'] == {'warmup_no_prev': 30}
    assert 'zero_but_counter_advanced' not in out['by_kind']


def test_missing_without_reason_cannot_pass_mechanism_gate():
    df = _frame()
    df.loc[0, 'link-a-b.traffic.qdiscReason'] = None
    assert not mnar_evidence(df)['mechanism_identified']


def test_warmup_reason_in_tick_one_requires_investigation():
    assert not mnar_evidence(_frame(invalid_ticks=(1,)))['mechanism_identified']


def test_absent_train_feature_makes_all_rows_ineligible():
    clean, rep = apply_policy(_frame(), feature_cols=['absent.traffic.lossPct'])
    assert len(clean) == 5
    assert rep['rows_trainable'] == 0
    assert rep['rows_dropped_train_nan'] == 5


def test_warmup_drop_uses_tick_order_even_if_rows_are_shuffled():
    clean, rep = apply_policy(_frame().iloc[::-1])
    assert 0 not in clean.tick.tolist()
    assert rep['rows_dropped_warmup'] == 1


def test_rate_mask_preserves_real_zero_and_masks_unknown_validity():
    from ml.missing import mask_invalid_rates
    df = pd.DataFrame({'host-x.traffic.rateValid': [True, False, None],
                       'host-x.traffic.rxRate': [0, 0, 10]})
    out, rep = mask_invalid_rates(df)
    assert out.iloc[0]['host-x.traffic.rxRate'] == 0
    assert out['host-x.traffic.rxRate'].isna().sum() == 2
    assert rep['total_cells_masked'] == 2


def test_rate_audit_does_not_compare_distinct_runs_of_same_profile():
    a = pd.DataFrame({'run_id': ['a']*2, 'profile': ['p']*2, 'tick': [0,1],
                      'host-x.traffic.rxBytes': [100,200], 'host-x.traffic.rxRate': [0,100]})
    b = a.copy()
    b['run_id'] = 'b'
    b['host-x.traffic.rxBytes'] += 1000
    rep = rate_fabrication_audit(pd.concat([a,b],ignore_index=True))
    assert rep['by_kind'] == {'warmup_no_prev': 2}


def test_thing_timestamp_preserved_as_metadata():
    from ml.flatten import flatten_snapshot
    from ml.schema import column_kind
    row = flatten_snapshot({'t_source': 1, 'things': {'host-x': {'t_source': 1.2}}})
    assert row['host-x.t_source'] == 1.2
    assert column_kind('host-x.t_source') == 'meta'
    assert column_kind('host-x.traffic.rateValid') == 'bool'
    assert column_kind('host-x.traffic.rateReason') == 'text'


def test_fisher_known_table():
    assert fisher_exact_two_sided(1,9,11,3) == pytest.approx(0.00275945618522)


@pytest.mark.parametrize('k,n', [(-1,10),(11,10),(0,-1)])
def test_wilson_rejects_invalid_counts(k,n):
    with pytest.raises(ValueError):
        wilson_ci(k,n)


@pytest.mark.parametrize('now,counts,reason', [
    (2,(100,200),'ok'), (1,(100,200),'nonpositive_dt'),
    (2,(50,200),'counter_reset'), (2,None,'interface_unavailable')])
def test_host_collector_emits_validity_for_each_read(monkeypatch,now,counts,reason):
    from types import SimpleNamespace
    from bridge import collector
    col = collector.Collector(None)
    host = SimpleNamespace(name='h1')
    col._prev['h1'] = (100,200,1)
    monkeypatch.setattr(collector,'read_host_net_dev',lambda h: '')
    monkeypatch.setattr(collector,'parse_proc_net_dev',lambda raw,iface: counts)
    traffic = col.collect_host(host,now)['features']['traffic']
    assert traffic['rateReason'] == reason
    assert traffic['rateValid'] == (reason == 'ok')
    assert isinstance(traffic['rxRate'],float)


def test_link_interface_failure_clears_loss_and_marks_rate_invalid(monkeypatch):
    from types import SimpleNamespace
    from bridge import collector
    a = SimpleNamespace(node=SimpleNamespace(name='h1'),name='h1-eth0',isUp=lambda:True)
    b = SimpleNamespace(node=SimpleNamespace(name='s1'),name='s1-eth3',isUp=lambda:True)
    link = SimpleNamespace(intf1=a,intf2=b)
    monkeypatch.setattr(collector,'read_intf_counters_full',lambda i:None)
    traffic = collector.Collector(None).collect_link(link,2)['features']['traffic']
    assert traffic['rateValid'] is False
    assert traffic['lossPct'] is None
    assert traffic['qdiscValid'] is False


def test_link_rate_flags_follow_warmup_zero_and_reset(monkeypatch):
    from types import SimpleNamespace
    from bridge import collector
    a = SimpleNamespace(node=SimpleNamespace(name='h1'),name='h1-eth0',isUp=lambda:True)
    b = SimpleNamespace(node=SimpleNamespace(name='s1'),name='s1-eth3',isUp=lambda:True)
    link = SimpleNamespace(intf1=a,intf2=b)
    counter = {'rx_bytes':100,'tx_bytes':200,'tx_packets':10,'tx_drop':0,'rx_drop':0}
    monkeypatch.setattr(collector,'read_intf_counters_full',lambda i:counter.copy())
    monkeypatch.setattr(collector,'read_qdisc_drops',lambda i:None)
    col = collector.Collector(None)
    first = col.collect_link(link,1)['features']['traffic']
    assert first['rateReason'] == 'warmup'
    zero = col.collect_link(link,2)['features']['traffic']
    assert zero['rateValid'] is True and zero['rxRate'] == 0.0
    counter['rx_bytes'] = 5
    reset = col.collect_link(link,3)['features']['traffic']
    assert reset['rateReason'] == 'counter_reset' and reset['rateValid'] is False
    assert reset['utilDirectionSource'] == 'directed_map'
