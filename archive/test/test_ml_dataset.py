"""Lesson 5.6 — test chống leakage. Phần lớn chạy bằng DataFrame giả."""
import numpy as np
import pandas as pd
import pytest

from ml import dataset as D
from ml import labels as L
from ml.features import (NULL_LIMIT_PCT_TRAIN, add_aggregate_features,
                         add_delta_features, add_rolling_features,
                         select_features)


def fake(n_runs=2, n=6, run_prefix='N'):
    rows = []
    for r in range(n_runs):
        for t in range(n):
            rows.append({'run_id': '%s-%d' % (run_prefix, r), 'tick': t,
                         'link-a.traffic.rxRate': 100.0 + t,
                         'link-a.traffic.lossPct': 0.0,
                         'link-b.traffic.lossPct': 0.0,
                         'link-a.status.state_up': 1,
                         'link-a.traffic.rxBytes': 1000 * t,     # cumulative
                         'link-a.traffic.bwMbps': 10.0,          # config
                         'link-a.traffic.qdiscReason': 'ok',     # text
                         'git_hash': 'abc'})                     # meta
    return pd.DataFrame(rows)


# --- T4: CHỌN FEATURE KHÔNG DÙNG NHÃN -----------------------------------
def test_selection_signature_cannot_receive_labels():
    """Hang rao o CHU KY HAM: khong co tham so nao nhan nhan."""
    import inspect
    params = set(inspect.signature(select_features).parameters)
    assert params == {'train_df', 'null_limit_pct'}
    assert not (params & {'y', 'labels', 'is_fault', 'test_df', 'auc'})


def test_selection_never_uses_label_based_rules():
    sel = select_features(fake())
    assert sel['rules']['label_based_rules_used'] == []


def test_selection_drops_structural_columns():
    sel = select_features(fake())
    for col in ('link-a.traffic.rxBytes', 'link-a.traffic.bwMbps',
                'link-a.traffic.qdiscReason', 'git_hash'):
        assert col in sel['dropped'], col
        assert col not in sel['features']


def test_selection_drops_constant_and_mostly_null_on_train():
    df = fake()
    df['link-c.traffic.lossPct'] = np.nan          # 100% null
    sel = select_features(df)
    assert 'link-a.traffic.lossPct' in sel['envelope']      # hằng số 0.0
    assert 'link-c.traffic.lossPct' in sel['dropped']
    assert 'link-a.traffic.rxRate' in sel['features']      # có biến thiên


def test_feature_order_is_deterministic():
    """Doi thu tu cot = doi cay IF = doi score, MA KHONG BAO LOI."""
    a = select_features(fake())['features']
    b = select_features(fake()[list(reversed(fake().columns))])['features']
    assert a == b == sorted(a)


# --- Tổng hợp: giữ cực trị, không pha loãng -----------------------------
def test_aggregate_uses_max_not_mean():
    df = fake()
    df.loc[0, 'link-a.traffic.lossPct'] = 53.0     # 1 link nặng, 1 link sạch
    out, _ = add_aggregate_features(df)
    assert out.loc[0, 'agg.loss_max'] == 53.0      # nguyên vẹn
    assert out.loc[0, 'agg.loss_n_above_alert'] == 1
    assert 'agg.loss_mean' not in out.columns      # mean bị cấm: dìm 8 lần


def test_aggregate_nan_does_not_become_zero():
    df = fake()
    df.loc[0, ['link-a.traffic.lossPct', 'link-b.traffic.lossPct']] = np.nan
    out, _ = add_aggregate_features(df)
    assert pd.isna(out.loc[0, 'agg.loss_max'])     # khong do duoc -> khong biet
    assert out.loc[0, 'agg.loss_n_measured'] == 0


def test_link_stats_fit_on_train_are_reused_for_test():
    """T3: scaler fit tren TRAIN, transform cho TEST. Fit lai = leakage."""
    tr, stats = add_aggregate_features(fake(run_prefix='N'))
    te, stats2 = add_aggregate_features(fake(run_prefix='F'), link_stats=stats)
    assert stats2 == stats                          # KHONG fit lai
    col = 'link-a.traffic.rxRate'
    assert stats[col]['mean'] == pytest.approx(
        pd.to_numeric(fake()[col]).mean())


# --- T2: feature thời gian chỉ dùng quá khứ -----------------------------
def test_delta_never_crosses_run_boundary():
    out = add_delta_features(fake(n_runs=2, n=4), ['link-a.traffic.rxRate'])
    first = out.loc[out.tick == 0, 'd1.link-a.traffic.rxRate']
    assert first.isna().all()          # tick 0 moi run: khong co qua khu
    assert out['d1.link-a.traffic.rxRate'].notna().sum() == 2 * 3


def test_rolling_is_shifted_and_grouped():
    """Thieu .shift(1) la dung chinh diem dang du doan. Test nay bat duoc."""
    out = add_rolling_features(fake(n_runs=2, n=6), ['link-a.traffic.rxRate'], 3)
    col = 'ma3.link-a.traffic.rxRate'
    r0 = out.loc[out.run_id == 'N-0'].sort_values('tick')
    assert r0[col].iloc[:3].isna().all()           # 3 tick dau: chua du cua so
    # tick 3 = mean(tick 0,1,2) = mean(100,101,102) = 101 -> KHONG chua tick 3
    assert r0[col].iloc[3] == pytest.approx(101.0)
    assert r0[col].iloc[3] != pytest.approx(
        pd.to_numeric(r0['link-a.traffic.rxRate']).iloc[1:4].mean())


def test_rolling_window_cost_is_what_we_claimed():
    """Ghim con so 6 tick priming/run — co so de quyet dinh KHONG dung mac dinh."""
    out = add_rolling_features(fake(n_runs=1, n=60), ['link-a.traffic.rxRate'], 5)
    assert out['ma5.link-a.traffic.rxRate'].isna().sum() == 5
    out1 = add_delta_features(fake(n_runs=1, n=60), ['link-a.traffic.rxRate'])
    assert out1['d1.link-a.traffic.rxRate'].isna().sum() == 1


# --- Nhãn không bao giờ là feature --------------------------------------
def test_label_columns_can_never_become_features():
    df = fake()
    for c in D.LABEL_COLS:
        df[c] = 1
    sel = select_features(df)
    assert not (set(sel['features']) & set(D.LABEL_COLS))


def test_config_id_groups_replications_together():
    """r1 va r2 cung 2 Mbps phai CUNG nhom -> leave-one-config-out."""
    r1 = {'run_id': 'N-load2M-s1003-r1', 'profile': 'normal',
          'load_mbps_per_client': 2.0}
    r2 = {'run_id': 'N-load2M-s1004-r2', 'profile': 'normal',
          'load_mbps_per_client': 2.0}
    r4 = {'run_id': 'N-load4M-s1005-r1', 'profile': 'normal',
          'load_mbps_per_client': 4.0}
    v = {'run_id': 'N-vary-s1007-r1', 'profile': 'normal_varying',
         'load_mbps_per_client': None}
    assert D.config_id(r1) == D.config_id(r2)
    assert D.config_id(r1) != D.config_id(r4) != D.config_id(v)


# --- Test cần dữ liệu thật (skip sạch nếu raw không có) -----------------
def _raw_available():
    from ml import campaign as C
    return (C.ROOT / 'data/phase5/raw/N-load1M-s1001-r1.jsonl').exists()


live = pytest.mark.skipif(not _raw_available(),
                          reason='raw .jsonl la local custody, khong o git')


@live
def test_train_and_test_run_ids_are_disjoint():
    s = D.load_split()
    assert set(s.groups_train_run) & set(s.meta['split']['test']) == set()


@live
def test_train_contains_no_faults():
    s = D.load_split()
    assert s.meta['warning_train_has_no_faults'] is True


@live
def test_no_nan_in_train_matrix():
    s = D.load_split()
    assert not s.X_train.isna().any().any()
    assert s.meta['n_train_rows_dropped_nan'] >= 0


@live
def test_test_keeps_nan_rows_and_counts_them():
    """MNAR co cau truc: khong duoc loai 4 o counter_reset trong cua so fault."""
    s = D.load_split()
    assert s.meta['n_test_rows'] == 590
    assert s.meta['n_test_rows_with_nan_and_fault'] == 8
    assert s.meta['n_test_rows_with_nan_feature'] == 26
    assert s.meta['n_test_rows_with_nan_and_normal'] == 18
    assert (s.meta['n_test_rows_with_nan_feature'] ==
            s.meta['n_test_rows_with_nan_and_fault'] +
            s.meta['n_test_rows_with_nan_and_normal'])


@live
def test_label_count_matches_test_rows():
    s = D.load_split()
    assert len(s.y_test) == len(s.X_test) == s.meta['n_test_rows']


@live
def test_load_split_is_deterministic():
    a, b = D.load_split(), D.load_split()
    assert a.feature_names == b.feature_names
    pd.testing.assert_frame_equal(a.X_train, b.X_train)
    pd.testing.assert_series_equal(a.y_test, b.y_test)


@live
def test_base_rate_from_split_matches_lesson_55():
    s = D.load_split()
    m = s.eval_primary.eq(L.EVAL)
    assert round(s.y_test[m].sum() / m.sum(), 4) == 0.2712


def test_extreme_test_values_do_not_change_fitted_statistics():
    train = fake()
    _, stats = add_aggregate_features(train)
    test = fake(run_prefix='F')
    test['link-a.traffic.rxRate'] = 1e12
    out, reused = add_aggregate_features(test, stats)
    assert reused == stats
    assert out['agg.rate_absz_max'].min() > 1e9
    assert select_features(train)['features'] == select_features(fake())['features']


def test_changing_future_ticks_does_not_change_past_features():
    col = 'link-a.traffic.rxRate'
    df = fake(n_runs=1)
    altered = df.copy()
    altered.loc[altered.tick >= 4, col] = 1e12
    for fn, name in ((lambda d: add_delta_features(d,[col]), 'd1.'+col),
                     (lambda d: add_rolling_features(d,[col],3), 'ma3.'+col)):
        pd.testing.assert_series_equal(fn(df).loc[df.tick<4,name], fn(altered).loc[df.tick<4,name])


@live
def test_raw_checksum_tampering_is_rejected_without_mutating_original(tmp_path):
    import json, shutil
    from ml import campaign as C
    contract = C.load_contract()
    rid = contract['split']['train'][0]
    original = C.run_paths(rid)
    target = C.run_paths(rid, tmp_path)
    target['meta'].parent.mkdir(parents=True)
    shutil.copyfile(original['meta'], target['meta'])
    target['final'].write_bytes(original['final'].read_bytes()+b'\n')
    (tmp_path/'results/report').mkdir(parents=True)
    shutil.copyfile(C.ROOT/'results/report/ml_dataset_manifest.json', tmp_path/'results/report/ml_dataset_manifest.json')
    with pytest.raises(ValueError, match='raw lech sha256'):
        D._frames(contract, tmp_path, [rid])


@live
def test_delta_missingness_propagation_is_explicit_in_row_accounting():
    s = D.load_split()
    rows = s.meta['unjudgeable_rows']
    assert sum(r['tick']==1 for r in rows) == 10
    assert sum(r['tick'] in (21,41) for r in rows) == 8
    assert sum(r['tick'] in (22,42) for r in rows) == 8
    assert s.y_test.sum() == 160
    assert 1 - s.meta['n_test_rows_with_nan_and_fault']/160 == .95


def test_fault_indicators_go_to_envelope_not_dead():
    sel = select_features(fake())
    for col in ('link-a.traffic.lossPct','link-b.traffic.lossPct','link-a.status.state_up'):
        assert col in sel['envelope']
        assert col not in sel['dead'] and col not in sel['features']
    assert sel['envelope']['link-a.traffic.lossPct']['min'] == 0
    assert sel['envelope']['link-a.traffic.lossPct']['n_train'] == len(fake())


def test_envelope_catches_what_isolation_forest_cannot():
    from scripts.check_if_constant_blindness import experiment
    result = experiment()
    assert result['constant_never_split'] and result['constant_score_invariant']
    assert result['envelope_test']['k'] == [0,1,1,1]
    assert result['synthetic_noise_control']['trees_splitting_last_column'] > 0


def test_envelope_threshold_gives_zero_false_positive_on_same_train():
    from ml.features import envelope_alarm_threshold
    df = fake()
    env = select_features(df)['envelope']
    threshold = envelope_alarm_threshold(df,env,sorted(env))
    assert threshold['K'] == 0 and threshold['k_train_mean'] == 0
    assert 'held-out' in threshold['calibration_note']


def test_envelope_strict_edges_and_missing_are_separate():
    from ml.features import envelope_exceedance_counts
    df = pd.DataFrame({'loss':[0,1,2,np.nan,np.inf]})
    out = envelope_exceedance_counts(df,{'loss':{'min':0,'max':1}})
    assert out.k.tolist() == [0,0,1,0,0]
    assert out.n_missing.tolist() == [0,0,0,1,1]
    with pytest.raises(ValueError):
        envelope_exceedance_counts(df,{'loss':{'min':1,'max':0}})


def test_all_missing_indicator_cannot_produce_nan_bounds_at_100pct_limit():
    sel = select_features(pd.DataFrame({'link-a.traffic.lossPct':[np.nan,np.inf]}),100)
    assert not sel['envelope'] and 'link-a.traffic.lossPct' in sel['dropped']


@live
def test_envelope_test_keys_match_if_rows_and_parameters_are_deterministic():
    a,b = D.load_split(),D.load_split()
    pd.testing.assert_frame_equal(a.X_test_envelope,b.X_test_envelope)
    assert a.X_test_envelope.index.equals(a.y_test.index)
    assert a.envelope == b.envelope and a.envelope_threshold == b.envelope_threshold
    assert a.meta['n_envelope_only_columns'] > 0
    assert len(set(a.envelope)&set(a.feature_names)) > 0
    assert a.meta['envelope_fit_train_rows'] == 472
    assert len(a.X_test_envelope) == 590
