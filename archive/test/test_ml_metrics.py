"""Lesson 6.2 — test ghim quy uoc chi so. Chi dung mang GIA mang cau truc that.

Cau truc (run, tick, y, unknown) lay tu phase6_prereg.json — do la thong tin
THIET KE da khoa, khong phai gia tri feature hay diem detector tren test.
"""
import inspect
import json

import numpy as np
import pytest

from ml import metrics as M
from scripts import build_phase6_prereg as P

PREREG = json.loads(P.OUT.read_text(encoding='utf-8'))['content']
RUNS = sorted(r['run_id'] for r in PREREG['run_predictions'])
UNKNOWN = {name: {tuple(k) for k in PREREG['facts']['unknown'][name]['unknown_keys']}
           for name in ('iforest', 'envelope')}


def skeleton(mask='eval_primary'):
    """590 dong: 10 run x tick 1..59, y=1 o tick 21..40 cua run F."""
    rows = []
    for rid in RUNS:
        grp = rid[0]
        fault = None if grp == 'C' else rid.split('-')[1]
        for t in range(1, 60):
            y = int(grp == 'F' and 21 <= t <= 40)
            ev = 1 if mask == 'eval_primary' else int(not (grp == 'F' and t in (21, 22, 41, 42)))
            rows.append((rid, t, grp, fault, y, ev))
    return rows


def frame(alarm_fn, judge='iforest', mask='eval_primary'):
    rows = skeleton(mask)
    judgeable = [int((r[0], r[1]) not in UNKNOWN[judge]) for r in rows]
    alarm = [int(j and alarm_fn(r)) for r, j in zip(rows, judgeable)]
    cols = list(zip(*rows))
    return M.build_frame(run_id=cols[0], tick=cols[1], group=cols[2], fault=cols[3],
                         y=cols[4], eval_mask=cols[5], judgeable=judgeable,
                         alarm=alarm, mask_name=mask)


# --- hai mo hinh tam thuong ------------------------------------------------
def test_always_normal_recall_zero_and_accuracy_is_the_dumb_7288():
    s = M.point_wise_scores(frame(lambda r: False))
    assert (s['tp'], s['recall'], s['fpr']) == (0, 0.0, 0.0)
    accuracy = (s['tp'] + s['tn']) / (s['n_positive'] + s['n_negative'])   # chi trong test
    assert round(accuracy, 4) == 0.7288


@pytest.mark.parametrize('judge,ceiling,fpr_all', [('iforest', 0.95, 412 / 430),
                                                   ('envelope', 0.975, 426 / 430)])
def test_always_alarm_hits_ceiling_not_one(judge, ceiling, fpr_all):
    s = M.point_wise_scores(frame(lambda r: True, judge))
    assert s['recall'] == s['recall_ceiling'] == ceiling
    assert s['fpr'] == pytest.approx(fpr_all)          # KHONG phai 1.0: TN van hanh
    assert s['fpr_judgeable_only'] == 1.0


# --- unknown ---------------------------------------------------------------
def test_unknown_positive_is_fn_not_dropped():
    s = M.point_wise_scores(frame(lambda r: True))
    assert s['n_positive'] == 160 and s['fn'] == 8 == s['n_unknown_positive']


def test_alarm_on_unknown_tick_is_rejected():
    rows = skeleton()
    cols = list(zip(*rows))
    with pytest.raises(ValueError, match='judgeable=0'):
        M.build_frame(run_id=cols[0], tick=cols[1], group=cols[2], fault=cols[3],
                      y=cols[4], eval_mask=cols[5], judgeable=[0] * len(rows),
                      alarm=[1] * len(rows), mask_name='eval_primary')


def test_build_frame_has_no_defaults():
    params = inspect.signature(M.build_frame).parameters.values()
    assert all(p.default is inspect.Parameter.empty for p in params)
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)


def test_api_has_no_accuracy_or_point_adjust():
    names = dir(M)
    assert not any('accuracy' in n or 'adjust' in n for n in names)


# --- mat na ----------------------------------------------------------------
def test_sensitivity_mask_counts_match_manifest():
    s = M.point_wise_scores(frame(lambda r: False, mask='eval_sensitivity'))
    assert (s['n_positive'], s['n_positive'] + s['n_negative']) == (144, 558)


def test_common_judgeable_uses_identical_rows():
    f_if = frame(lambda r: True, 'iforest')
    f_env = frame(lambda r: True, 'envelope')
    s = M.point_wise_scores(M.restrict_to_common_judgeable(f_if, f_env))
    assert s['n_positive'] + s['n_negative'] == 590 - 26
    assert s['n_unknown_positive'] == s['n_unknown_negative'] == 0


# --- FPR ba muc ------------------------------------------------------------
def test_fpr_breakdown_denominators():
    b = M.fpr_breakdown(frame(lambda r: True, 'iforest'))
    assert (b['control']['n_negative'], b['in_fault_runs']['n_negative'], b['all']['n_negative']) == (118, 312, 430)
    assert b['all']['n_judgeable_negative'] == 412
    assert b['control']['fpr'] == pytest.approx(116 / 118)


# --- do tre ----------------------------------------------------------------
def test_delay_structural_minimum_and_censored():
    # bao dong o MOI tick phan duoc cua run degrade s2-s3, khong bao o run khac
    target = 'F-degrade-s2-s3-s3004-r1'
    d_if = M.detection_delay(frame(lambda r: r[0] == target, 'iforest'))
    d_env = M.detection_delay(frame(lambda r: r[0] == target, 'envelope'))
    assert d_if['per_run'][target] == 2 and d_env['per_run'][target] == 1
    assert d_if['n_censored'] == 7 and d_if['per_run']['F-flood-h1_to_srv1-s3005-r1'] is None
    assert d_if['median_delay_detected'] == 2.0


def test_delay_refuses_non_primary_mask():
    with pytest.raises(ValueError):
        M.detection_delay(frame(lambda r: True, mask='eval_sensitivity'))


# --- bootstrap -------------------------------------------------------------
def _row_bootstrap_recall(f, n_boot, seed):
    """CACH SAI, chi o trong test de do do chenh. API khong co ham nay."""
    r = f.rows[f.rows.y]
    rng = np.random.default_rng(seed)
    vals = [r.alarm.to_numpy()[rng.integers(0, len(r), len(r))].mean() for _ in range(n_boot)]
    return np.percentile(vals, 2.5), np.percentile(vals, 97.5)


def test_cluster_ci_is_much_wider_than_row_ci():
    caught = set(RUNS[2:6])                             # 4/8 run F bat tron, 4 bo sot tron
    f = frame(lambda r: r[0] in caught, 'envelope')
    cl = M.cluster_bootstrap(f, n_boot=2000, rng_seed=20260916)['recall']
    lo, hi = _row_bootstrap_recall(f, 2000, 20260916)
    assert (cl['ci_high'] - cl['ci_low']) > 3 * (hi - lo)


def test_bootstrap_is_deterministic_and_reports_valid_count():
    f = frame(lambda r: r[1] % 7 == 0)
    a = M.cluster_bootstrap(f, n_boot=300, rng_seed=1)
    b = M.cluster_bootstrap(f, n_boot=300, rng_seed=1)
    assert a == b and a['recall']['n_valid'] == 300


# --- chan dau vao sai ------------------------------------------------------
def test_zero_denominator_is_none_not_zero():
    s = M.scores_from_counts({k: 0 for k in M.COUNT_KEYS})
    assert s['recall'] is None and s['fpr'] is None and s['f1'] is None


def test_control_run_with_positive_label_is_rejected():
    rows = skeleton()
    cols = [list(c) for c in zip(*rows)]
    cols[4][0] = 1                                      # C-load2M tick 1 y=1
    with pytest.raises(ValueError, match='run C'):
        M.build_frame(run_id=cols[0], tick=cols[1], group=cols[2], fault=cols[3],
                      y=cols[4], eval_mask=cols[5], judgeable=[1] * len(rows),
                      alarm=[0] * len(rows), mask_name='eval_primary')


def test_summarize_seeds_uses_sample_std_and_skips_none():
    s = M.summarize_seeds([0.8, 0.9, None, 1.0])
    assert s['n_seeds'] == 4 and s['n_valid'] == 3
    assert s['std'] == pytest.approx(0.1)

@pytest.mark.parametrize('field,value', [('tick',[1.5]*590),('tick',[True]*590),('run_id',['']*590),('y',[np.nan]*590),('alarm',np.zeros((590,1)))])
def test_gate_rejects_silent_coercions(field,value):
    rows=skeleton();cols=list(zip(*rows));args=dict(run_id=cols[0],tick=cols[1],group=cols[2],fault=cols[3],y=cols[4],eval_mask=cols[5],judgeable=[1]*len(rows),alarm=[0]*len(rows),mask_name='eval_primary');args[field]=value
    with pytest.raises(ValueError): M.build_frame(**args)

def test_evalframe_cannot_be_forged_and_rows_are_copy_protected():
    f=frame(lambda r:False)
    with pytest.raises(ValueError): M.EvalFrame(f.rows,'eval_primary')
    rows=f.rows;rows.loc[0,'y']=True
    assert not f.rows.loc[0,'y']
    assert not hasattr(f,'_rows') and isinstance(f._records,tuple)

def test_common_judgeable_rejects_metadata_mismatch():
    a=frame(lambda r:False);rows=a.rows;rows.loc[0,'group']='F'
    b=M.EvalFrame(rows,'eval_primary',_token=M._FRAME_TOKEN)
    with pytest.raises(ValueError): M.restrict_to_common_judgeable(a,b)

def test_counts_reject_invalid_external_accounting():
    with pytest.raises(ValueError): M.scores_from_counts({'tp':0})
    bad={k:0 for k in M.COUNT_KEYS};bad['n_unknown_positive']=1
    with pytest.raises(ValueError): M.scores_from_counts(bad)

@pytest.mark.parametrize('kwargs',[{'n_boot':True,'rng_seed':1},{'n_boot':1,'rng_seed':True},{'n_boot':1,'rng_seed':1,'ci':(95,5)}])
def test_bootstrap_rejects_invalid_protocol(kwargs):
    with pytest.raises(ValueError): M.cluster_bootstrap(frame(lambda r:False),**kwargs)

def test_seed_summary_rejects_infinity():
    with pytest.raises(ValueError): M.summarize_seeds([1,float('inf')])


def test_empty_frame_is_rejected():
    with pytest.raises(ValueError):
        M.build_frame(run_id=[],tick=[],group=[],fault=[],y=[],eval_mask=[],judgeable=[],alarm=[],mask_name='eval_primary')
