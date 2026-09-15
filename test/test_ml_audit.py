#!/usr/bin/env python3
"""Ghim các quyết định của Lesson 5.1 bằng test, không bằng trí nhớ."""
import numpy as np
import pandas as pd
import pytest

from ml.audit import audit_features, auc_separation, cohens_d_pooled, kept_features
from ml.flatten import flatten_snapshot, load_jsonl
from ml.schema import column_kind

SNAP = {
    'timestamp': '2026-09-15T09:41:38Z', 't_source': 1789465298.75,
    'cycle_scan_ms': 71.4,
    'things': {
        'link-h1-s1': {'attributes': {'type': 'link'}, 'features': {
            'status': {'state': 'up'},
            'capacity': {'bwMbps': 20.0},
            'traffic': {'rxRate': 1.0, 'txRate': 2.0, 'lossPct': None,
                        'qdiscValid': False, 'qdiscReason': 'warmup',
                        'qdiscCounters': {'h1-eth0': {'drops': 0}}}}},
        'host-h1': {'features': {'traffic': {'rxBytes': 100, 'rxRate': 0.5}}},
    },
}


def test_flatten_dat_ten_cot_theo_thing_feature_property():
    row = flatten_snapshot(SNAP)
    assert row['link-h1-s1.traffic.rxRate'] == 1.0
    assert row['host-h1.traffic.rxBytes'] == 100
    assert 'link-h1-s1.traffic.qdiscCounters' not in row   # lồng cấp 3: bỏ qua


def test_null_di_den_dataframe_duoi_dang_nan_khong_bi_dien_0():
    """Luật L1. Nếu test này đỏ, toàn bộ Phase 5 mất ý nghĩa."""
    row = flatten_snapshot(SNAP)
    assert row['link-h1-s1.traffic.lossPct'] is None
    df = pd.DataFrame([row])
    assert df['link-h1-s1.traffic.lossPct'].isna().all()
    assert not (df['link-h1-s1.traffic.lossPct'] == 0).any()


def test_state_duoc_suy_dien_khong_ghi_de_cot_goc():
    row = flatten_snapshot(SNAP)
    assert row['link-h1-s1.status.state'] == 'up'
    assert row['link-h1-s1.status.state_up'] == 1


def test_column_kind_phan_loai_dung_bon_nhom_rui_ro():
    assert column_kind('host-h1.traffic.rxBytes') == 'cumulative'
    assert column_kind('link-h1-s1.capacity.bwMbps') == 'config'
    assert column_kind('link-h1-s1.traffic.qdiscValid') == 'bool'
    assert column_kind('link-h1-s1.traffic.lossPct') == 'numeric'
    assert column_kind('tick') == 'meta'


def test_auc_khong_sup_do_khi_std_normal_bang_0():
    """Chính là trường hợp `lossPct`: normal toàn 0, fault > 0.

    Ba kết quả cần ghim:
      - công thức cũ (chia std_normal) -> inf, tức VÔ NGHĨA
      - AUC -> 1.0, vẫn đo được
      - d_pooled -> hữu hạn khi fault có phương sai (trường hợp THẬT),
        và NaN khi cả hai nhóm đều hằng số (thành thật: không xác định,
        chứ không bịa ra một con số)
    """
    normal = pd.Series([0.0] * 20)
    fault_real = pd.Series([50.0 + i * 0.5 for i in range(20)])
    fault_const = pd.Series([50.0] * 20)

    with np.errstate(divide='ignore'):
        assert np.isinf(abs(fault_real.mean() - normal.mean()) / normal.std(ddof=1))
    assert auc_separation(normal, fault_real) == 1.0
    assert np.isfinite(cohens_d_pooled(normal, fault_real))

    assert auc_separation(normal, fault_const) == 1.0
    assert np.isnan(cohens_d_pooled(normal, fault_const))


def test_auc_bang_0_5_khi_hai_phan_bo_trung_nhau():
    x = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert auc_separation(x, x) == pytest.approx(0.5)


def test_bo_dem_cong_don_luon_bi_loai_du_auc_bang_1():
    """rxBytes tách biệt hoàn hảo nhưng là ARTIFACT — phải bị loại."""
    df = pd.DataFrame({
        'host-h1.traffic.rxBytes': list(range(10)) + list(range(100, 110)),
        'link-h1-s1.traffic.lossPct': [0.0] * 10 + [50.0] * 10,
        'is_fault': [0] * 10 + [1] * 10,
    })
    a = audit_features(df)
    row = a.set_index('feature').loc['host-h1.traffic.rxBytes']
    assert row['auc'] == 1.0            # trong số liệu thì nó "hoàn hảo"
    assert row['quyet_dinh'] == 'LOAI'  # nhưng luật cấu trúc vẫn loại nó
    assert 'host-h1.traffic.rxBytes' not in kept_features(a)
    assert 'link-h1-s1.traffic.lossPct' in kept_features(a)


def test_feature_hang_so_bi_loai():
    df = pd.DataFrame({'x.traffic.rxRate': [5.0] * 20,
                       'y.traffic.rxRate': list(range(20)),
                       'is_fault': [0] * 10 + [1] * 10})
    a = audit_features(df).set_index('feature')
    assert a.loc['x.traffic.rxRate', 'quyet_dinh'] == 'LOAI'
    assert a.loc['y.traffic.rxRate', 'quyet_dinh'] == 'GIU'


@pytest.mark.parametrize('path', ['logs/ml_normal_v2.jsonl',
                                  'logs/ml_flood_v2.jsonl',
                                  'logs/ml_injection_v2.jsonl'])
def test_dataset_pilot_doc_duoc_va_giu_nguyen_null(path):
    df = load_jsonl(path, profile='x', run_id='x')
    assert len(df) > 0
    loss_cols = [c for c in df.columns if c.endswith('.traffic.lossPct')]
    assert len(loss_cols) == 8
    # dòng đầu mỗi file là warmup -> lossPct phải là NaN, không phải 0
    assert df.loc[0, loss_cols].isna().all()

@pytest.mark.parametrize('state', ['unknown', None])
def test_unknown_state_is_not_encoded_as_down(state):
    row = flatten_snapshot({'things': {'link-x-y': {'features': {'status': {'state': state}}}}})
    assert row['link-x-y.status.state_up'] is None


def test_ditto_properties_wrapper_and_invalid_cached_loss():
    snap = {'things': {'link-x-y': {'features': {
        'traffic': {'properties': {'lossPct': 7.0, 'qdiscValid': False}},
        'status': {'properties': {'state': 'down'}}}}}}
    row = flatten_snapshot(snap)
    assert row['link-x-y.traffic.lossPct'] is None
    assert row['link-x-y.status.state_up'] == 0


def test_unmeasured_group_cannot_be_kept_with_nan_auc():
    df = pd.DataFrame({'x.traffic.rxRate': [1.0,2.0,np.nan,np.nan], 'is_fault': [0,0,1,1]})
    audit = audit_features(df).set_index('feature')
    assert audit.loc['x.traffic.rxRate','quyet_dinh'] == 'CHAT_VAN'
    assert audit.loc['x.traffic.rxRate','n_fault'] == 0


@pytest.mark.parametrize('label', [None, 'normal', 2])
def test_missing_or_ambiguous_label_fails_instead_of_becoming_fault(label):
    with pytest.raises(ValueError):
        audit_features(pd.DataFrame({'x.traffic.rxRate':[1,2], 'is_fault':[0,label]}))


def test_cumulative_and_config_cannot_satisfy_gate():
    df = pd.DataFrame({'host-x.traffic.rxBytes':list(range(20)),
                       'link-x-y.capacity.bwMbps':[20]*10+[5]*10,
                       'is_fault':[0]*10+[1]*10})
    a = audit_features(df)
    assert (a.auc_dist > .5).sum() == 2
    assert ((a.quyet_dinh == 'GIU') & (a.auc_dist > .5)).sum() == 0
