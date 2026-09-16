#!/usr/bin/env python3
"""Lesson 6.2 — API DUY NHẤT để tính chỉ số Phase 6.

Quy ước lấy từ results/report/phase6_prereg.json (DT4N-P6-PREREG-v1).
Không có hàm accuracy. Không có bootstrap theo dòng. Không có point-adjust.
Thiếu một thứ trong API = không thể vô tình dùng nó.

MỘT CỔNG VÀO: mọi hàm nhận `EvalFrame` do build_frame() tạo ra. Muốn tạo
frame phải khai đủ y, mặt nạ, judgeable, alarm, group, fault — không có giá
trị mặc định. Frame được kiểm tra một lần, các hàm sau tin tưởng nó.
"""
from __future__ import annotations

import math
from numbers import Integral
from dataclasses import dataclass

import numpy as np
import pandas as pd

MASKS = ('eval_primary', 'eval_sensitivity', 'common_judgeable_primary')
GROUPS = ('C', 'F')
COUNT_KEYS = ('tp', 'fp', 'fn', 'tn', 'n_unknown_positive', 'n_unknown_negative')


_FRAME_TOKEN = object()

@dataclass(frozen=True, init=False)
class EvalFrame:
    """Validated immutable-by-copy evaluation rows; construct via build_frame."""
    _records: tuple
    mask_name: str
    def __init__(self, rows, mask_name, _token=None):
        if _token is not _FRAME_TOKEN:
            raise ValueError('EvalFrame must be created by build_frame')
        object.__setattr__(self, '_records', tuple(rows[['run_id','tick','group','fault','y','in_eval','judgeable','alarm']].itertuples(index=False,name=None)))
        object.__setattr__(self, 'mask_name', mask_name)
    @property
    def rows(self):
        df=pd.DataFrame.from_records(self._records,columns=['run_id','tick','group','fault','y','in_eval','judgeable','alarm'])
        for col in ('y','in_eval','judgeable','alarm'): df[col]=df[col].astype(bool)
        return df


# =========================================================================
# 1. CỔNG VÀO — kiểm tra một lần, từ chối thay vì sửa âm thầm
# =========================================================================
def _binary(name, values) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f'{name} phai la mang 1 chieu')
    if arr.dtype == bool:
        return arr.copy()
    if arr.dtype.kind not in 'iuf' or not np.isfinite(arr).all() or not np.isin(arr, (0, 1)).all():
        raise ValueError(f'{name} phai nhi phan 0/1')
    return arr.astype(bool)


def build_frame(*, run_id, tick, group, fault, y, eval_mask, judgeable, alarm,
                mask_name: str) -> EvalFrame:
    if mask_name not in MASKS:
        raise ValueError('mask_name la: %s' % (MASKS,))
    raw_run=np.asarray(run_id,dtype=object);raw_tick=np.asarray(tick)
    if raw_run.ndim != 1 or any(not isinstance(x,str) or not x for x in raw_run):
        raise ValueError('run_id phai la chuoi khong rong')
    if raw_tick.ndim != 1 or raw_tick.dtype.kind not in 'iu' or raw_tick.dtype.kind == 'b' or (raw_tick < 0).any():
        raise ValueError('tick phai la so nguyen khong am')
    cols = dict(run_id=raw_run, tick=raw_tick.astype('int64'),
                group=np.asarray(group, dtype=object), fault=np.asarray(fault, dtype=object),
                y=_binary('y', y), in_eval=_binary('eval_mask', eval_mask),
                judgeable=_binary('judgeable', judgeable), alarm=_binary('alarm', alarm))
    n = {len(v) for v in cols.values()}
    if n == {0}: raise ValueError('evaluation frame cannot be empty')
    if len(n) != 1:
        raise ValueError('cac mang khac do dai: %s' % sorted(n))
    df = pd.DataFrame(cols)
    if df.duplicated(['run_id', 'tick']).any():
        raise ValueError('trung khoa (run_id, tick)')
    if not df.group.isin(GROUPS).all():
        raise ValueError('group chi duoc la C hoac F')
    # Detector KHONG duoc bao dong o tick khong phan duoc. Tu choi, khong ep ve 0:
    # ep am tham se che mot loi o detector (vd quen xu ly NaN).
    if (df.alarm & ~df.judgeable).any():
        raise ValueError('alarm=1 tai tick judgeable=0: detector vi pham quy uoc unknown')
    for rid, g in df.groupby('run_id', sort=True):
        if g.group.nunique() != 1 or g.fault.nunique(dropna=False) != 1:
            raise ValueError('group/fault khong nhat quan trong run ' + rid)
        is_c = g.group.iat[0] == 'C'
        ticks = g.sort_values('tick')
        pos = ticks.tick[ticks.y].to_numpy()
        if is_c and (len(pos) or not pd.isna(ticks.fault.iat[0])):
            raise ValueError('run C khong duoc co y=1 hay fault: ' + rid)
        if not is_c and pd.isna(ticks.fault.iat[0]):
            raise ValueError('run F thieu fault: ' + rid)
        if not is_c and (len(pos) == 0 or np.any(np.diff(pos) != 1)):
            raise ValueError('run F phai co dung mot khoi y=1 lien tiep: ' + rid)
    df = df.sort_values(['run_id', 'tick']).reset_index(drop=True)
    return EvalFrame(rows=df, mask_name=mask_name, _token=_FRAME_TOKEN)


def restrict_to_common_judgeable(*frames: EvalFrame) -> EvalFrame:
    """So sanh phu: chi giu tick MOI detector deu phan duoc.

    Nhan cac EvalFrame (moi detector mot frame) thay vi mang tran: frame da
    sap theo (run_id, tick), nen doi chieu khoa o day chan loi lech thu tu.
    Alarm lay tu frame DAU TIEN.
    """
    if len(frames) < 2 or any(f.mask_name != 'eval_primary' for f in frames):
        raise ValueError('can >= 2 frame eval_primary')
    base = frames[0].rows
    for other in frames[1:]:
        o = other.rows
        if not (base[['run_id','tick','group','fault','y','in_eval']].equals(o[['run_id','tick','group','fault','y','in_eval']])):
            raise ValueError('cac frame khong cung dong/nhan/mat na')
    common = np.logical_and.reduce([f.rows.judgeable.to_numpy() for f in frames])
    rows = base.copy()
    rows['in_eval'] = rows.in_eval.to_numpy() & common
    return EvalFrame(rows=rows, mask_name='common_judgeable_primary', _token=_FRAME_TOKEN)


# =========================================================================
# 2. BẢNG NHẦM LẪN VÀ CHỈ SỐ ĐIỂM
# =========================================================================
def _counts(rows: pd.DataFrame) -> dict:
    r = rows[rows.in_eval]
    y, a, j = r.y.to_numpy(), r.alarm.to_numpy(), r.judgeable.to_numpy()
    return {'tp': int((y & a).sum()), 'fp': int((~y & a).sum()),
            'fn': int((y & ~a).sum()), 'tn': int((~y & ~a).sum()),
            'n_unknown_positive': int((y & ~j).sum()),
            'n_unknown_negative': int((~y & ~j).sum())}


def confusion(frame: EvalFrame) -> dict:
    return _counts(frame.rows)


def _ratio(num, den):
    return None if den == 0 else num / den


def scores_from_counts(c: dict) -> dict:
    if set(c) != set(COUNT_KEYS) or any(not isinstance(c[k], Integral) or isinstance(c[k], (bool,np.bool_)) or c[k] < 0 for k in COUNT_KEYS):
        raise ValueError('counts require exactly nonnegative integer COUNT_KEYS')
    if c['n_unknown_positive'] > c['fn'] or c['n_unknown_negative'] > c['tn']:
        raise ValueError('unknown counts cannot exceed FN/TN')
    p, n = c['tp'] + c['fn'], c['fp'] + c['tn']
    judgeable_neg = n - c['n_unknown_negative']
    return {
        'recall': _ratio(c['tp'], p),
        'recall_ceiling': _ratio(p - c['n_unknown_positive'], p),
        'fpr': _ratio(c['fp'], n),                       # TN van hanh gom unknown
        'fpr_judgeable_only': _ratio(c['fp'], judgeable_neg),
        'precision': _ratio(c['tp'], c['tp'] + c['fp']),
        # F1 = 2TP/(2TP+FP+FN): tuong duong 2PR/(P+R), nhung chi undefined khi
        # khong co duong va khong co bao dong
        'f1': _ratio(2 * c['tp'], 2 * c['tp'] + c['fp'] + c['fn']),
        'n_positive': p, 'n_negative': n, 'n_judgeable_negative': judgeable_neg,
        **c}


def point_wise_scores(frame: EvalFrame) -> dict:
    out = scores_from_counts(confusion(frame))
    out['mask'] = frame.mask_name
    return out


def fpr_breakdown(frame: EvalFrame) -> dict:
    rows = frame.rows
    def fpr(sub):
        s = scores_from_counts(_counts(sub))
        return {'fpr': s['fpr'], 'fpr_judgeable_only': s['fpr_judgeable_only'],
                'fp': s['fp'], 'n_negative': s['n_negative'],
                'n_judgeable_negative': s['n_judgeable_negative']}
    return {'control': fpr(rows[rows.group == 'C']),
            'in_fault_runs': fpr(rows[(rows.group == 'F') & ~rows.y]),
            'all': fpr(rows[~rows.y]),
            'per_control_run': {rid: fpr(g) for rid, g in rows[rows.group == 'C'].groupby('run_id')}}


def scores_by_fault(frame: EvalFrame) -> dict:
    rows = frame.rows
    out = {}
    for fault, g in rows[rows.group == 'F'].groupby('fault', sort=True):
        out[fault] = {'pooled': scores_from_counts(_counts(g)),
                      'per_run': {rid: scores_from_counts(_counts(r))['recall']
                                  for rid, r in g.groupby('run_id', sort=True)},
                      'ci': 'none (2 runs per fault type)'}
    return out


# =========================================================================
# 3. ĐỘ TRỄ — censored là None, không bao giờ là 0 hay 20
# =========================================================================
def detection_delay(frame: EvalFrame) -> dict:
    if frame.mask_name != 'eval_primary':
        raise ValueError('delay chi dinh nghia tren eval_primary (prereg)')
    per_run = {}
    for rid, g in frame.rows[frame.rows.group == 'F'].groupby('run_id', sort=True):
        window = g[g.y]                                  # inject+1 .. revert
        onset = int(window.tick.min())
        hits = window.tick[window.alarm & window.in_eval]
        per_run[rid] = None if hits.empty else int(hits.min()) - onset
    detected = [d for d in per_run.values() if d is not None]
    return {'per_run': per_run, 'n_incidents': len(per_run),
            'n_detected': len(detected), 'n_censored': len(per_run) - len(detected),
            'median_delay_detected': float(np.median(detected)) if detected else None}


# =========================================================================
# 4. BẤT ĐỊNH — cluster bootstrap theo run, phân tầng C/F
# =========================================================================
METRICS_BOOT = ('recall', 'fpr', 'fpr_judgeable_only', 'precision', 'f1')


def cluster_bootstrap(frame: EvalFrame, *, n_boot: int, rng_seed: int,
                      ci=(2.5, 97.5)) -> dict:
    """Lay mau lai RUN trong tung tang, cong DON count cua run duoc chon.
    Cong count roi chia == noi het dong roi tinh lai: nhanh va chinh xac."""
    if not isinstance(n_boot,int) or isinstance(n_boot,bool) or n_boot < 1:
        raise ValueError('n_boot must be a positive integer')
    if not isinstance(rng_seed,int) or isinstance(rng_seed,bool):
        raise ValueError('rng_seed must be an integer')
    if len(ci)!=2 or not all(math.isfinite(float(x)) for x in ci) or not 0 <= ci[0] < ci[1] <= 100:
        raise ValueError('ci must be two ordered percentiles in [0,100]')
    rows = frame.rows
    per_run = rows.groupby('run_id', sort=True).apply(
        lambda g: pd.Series(_counts(g)), include_groups=False)
    strata = rows.groupby('run_id', sort=True).group.first()
    rng = np.random.default_rng(rng_seed)
    samples = {m: [] for m in METRICS_BOOT}
    for _ in range(n_boot):
        chosen = []
        for grp in GROUPS:
            ids = strata.index[strata == grp].to_numpy()
            if len(ids):
                chosen.extend(rng.choice(ids, size=len(ids), replace=True))
        c = per_run.loc[chosen].sum().astype(int).to_dict()
        s = scores_from_counts(c)
        for m in METRICS_BOOT:
            if s[m] is not None:
                samples[m].append(s[m])
    out = {}
    for m, vals in samples.items():
        out[m] = {'ci_low': float(np.percentile(vals, ci[0])) if vals else None,
                  'ci_high': float(np.percentile(vals, ci[1])) if vals else None,
                  'n_valid': len(vals), 'n_boot': n_boot}
    out['method'] = 'cluster bootstrap by run_id, stratified C/F'
    out['rng_seed'] = rng_seed
    return out


# =========================================================================
# 5. TỔNG HỢP QUA SEED
# =========================================================================
def summarize_seeds(values) -> dict:
    values = list(values)
    vals=[]
    for v in values:
        if v is None: continue
        try: x=float(v)
        except (TypeError,ValueError): raise ValueError('seed summaries require numeric values or None')
        if math.isnan(x): continue
        if not math.isfinite(x): raise ValueError('seed summaries reject infinite values')
        vals.append(x)
    return {'n_seeds': len(values), 'n_valid': len(vals),
            'mean': float(np.mean(vals)) if vals else None,
            'std': float(np.std(vals, ddof=1)) if len(vals) >= 2 else None,
            'min': min(vals) if vals else None, 'max': max(vals) if vals else None}
