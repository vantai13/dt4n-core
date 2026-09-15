#!/usr/bin/env python3
"""Kiểm toán feature: mỗi cột được đo, được chấm điểm, và được QUYẾT ĐỊNH.

AUC dùng hạng trung bình khi hòa: P(fault > normal) + 0.5*P(tie).
Không cần chia cho độ lệch chuẩn; vẫn đo được khi normal có std = 0.
Cohen's d dùng pooled sample std, không phải std_normal đơn nhóm.
AUC gần 0.5 chỉ cho thấy ít tách biệt theo thứ tự đơn biến; hai phân bố
vẫn có thể khác hình dạng. Báo cáo cả AUC và d, không suy ra hiệu năng ML.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.schema import REASON, column_kind

NULL_LIMIT_PCT = 50.0     # thiếu quá ngưỡng này -> loại
AUC_DIST_MIN = 0.10       # |AUC-0.5|*2 dưới ngưỡng này -> chất vấn


def auc_separation(x_normal: pd.Series, x_fault: pd.Series) -> float:
    """AUC = P(fault > normal) + 0.5*P(tie), tính bằng hạng trung bình.

    Trả NaN nếu một trong hai nhóm không có mẫu hợp lệ.
    AUC = 0.5 -> không tách biệt theo thứ tự; không chứng minh phân bố trùng.
    AUC = 1 hoặc 0 -> tách hoàn toàn theo thứ tự trên các mẫu hữu hạn.
    """
    a = _numeric(pd.Series(x_normal)).dropna().to_numpy()
    b = _numeric(pd.Series(x_fault)).dropna().to_numpy()
    if a.size == 0 or b.size == 0:
        return float('nan')
    ranks = pd.Series(np.concatenate([a, b])).rank().to_numpy()
    n_fault, n_norm = b.size, a.size
    u = ranks[n_norm:].sum() - n_fault * (n_fault + 1) / 2.0
    return float(u / (n_fault * n_norm))


def cohens_d_pooled(x_normal: pd.Series, x_fault: pd.Series) -> float:
    """Cohen's d với độ lệch chuẩn gộp. Trả NaN nếu pooled std = 0."""
    a = _numeric(pd.Series(x_normal)).dropna()
    b = _numeric(pd.Series(x_fault)).dropna()
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return float('nan')
    pooled = np.sqrt(((n1 - 1) * a.std(ddof=1) ** 2 +
                      (n2 - 1) * b.std(ddof=1) ** 2) / (n1 + n2 - 2))
    if not np.isfinite(pooled) or pooled < 1e-12:
        return float('nan')
    return float(abs(b.mean() - a.mean()) / pooled)


def _numeric(series: pd.Series) -> pd.Series:
    """bool -> 0/1; còn lại ép về số, giá trị không ép được thành NaN."""
    if series.dtype == bool:
        return series.astype(float)
    return pd.to_numeric(series, errors='coerce').astype(float).replace([np.inf, -np.inf], np.nan)


def decide(row: pd.Series) -> tuple[str, str]:
    """(quyết_định, lý_do). Thứ tự luật là CÓ Ý: luật cấu trúc TRƯỚC luật số liệu.

    Luật cấu trúc (kind) không phụ thuộc dữ liệu pilot, nên nó đúng cả khi ta
    sinh thêm 16 run mới. Luật số liệu (hằng số, thiếu, không tách biệt) chỉ
    đúng trên dataset đang xét — vì vậy nó phải xếp SAU.
    """
    kind = row['kind']
    if kind == 'meta':
        return 'BO_QUA', REASON['meta']
    if kind == 'text':
        return 'BO_QUA', REASON['text']
    if kind == 'cumulative':
        return 'LOAI', REASON['cumulative']
    if kind == 'config':
        return 'LOAI', REASON['config']
    if row['pct_null'] > NULL_LIMIT_PCT:
        return 'LOAI', REASON['mostly_null']
    if row['nunique'] <= 1:
        return 'LOAI', REASON['constant']
    if not np.isfinite(row['auc_dist']):
        return 'CHAT_VAN', REASON['unmeasured']
    if np.isfinite(row['auc_dist']) and row['auc_dist'] < AUC_DIST_MIN:
        return 'CHAT_VAN', REASON['no_separation']
    return 'GIU', 'có biến thiên và có tách biệt đo được'


def audit_features(df: pd.DataFrame, fault_col: str = 'is_fault') -> pd.DataFrame:
    """Bảng kiểm toán: một dòng cho MỖI cột của df."""
    if fault_col not in df.columns:
        raise ValueError(f'thiếu cột nhãn {fault_col!r} để so normal vs fault')
    labels = df[fault_col]
    if labels.isna().any() or not labels.isin([0, 1, False, True]).all():
        raise ValueError('nhãn fault phải là 0/1, không có null hoặc chuỗi')
    mask_fault = labels.astype(bool)
    recs = []
    for col in df.columns:
        if col == fault_col:
            continue
        kind = column_kind(col)
        s_raw = df[col]
        if kind in ('numeric', 'bool', 'cumulative', 'config'):
            s_raw = _numeric(s_raw)
        rec = {
            'feature': col,
            'kind': kind,
            'nunique': int(s_raw.nunique(dropna=True)),
            'pct_null': round(100.0 * s_raw.isna().mean(), 2),
        }
        if kind in ('numeric', 'bool', 'cumulative', 'config'):
            s = _numeric(s_raw)
            n, f = s[~mask_fault], s[mask_fault]
            a = auc_separation(n, f)
            rec.update({
                'std': s.std(ddof=1),
                'n_normal': int(n.notna().sum()), 'n_fault': int(f.notna().sum()),
                'mean_normal': n.mean(), 'std_normal': n.std(ddof=1),
                'mean_fault': f.mean(), 'std_fault': f.std(ddof=1),
                'auc': a,
                'auc_dist': abs(a - 0.5) * 2 if np.isfinite(a) else float('nan'),
                'd_pooled': cohens_d_pooled(n, f),
            })
        else:
            rec.update({'std': float('nan'), 'n_normal': 0, 'n_fault': 0})
            for k in ('mean_normal', 'std_normal', 'mean_fault', 'std_fault',
                      'auc', 'auc_dist', 'd_pooled'):
                rec[k] = float('nan')
        recs.append(rec)
    out = pd.DataFrame(recs)
    decisions = out.apply(decide, axis=1, result_type='expand')
    out['quyet_dinh'] = decisions[0]
    out['ly_do'] = decisions[1]
    return out.sort_values(['quyet_dinh', 'auc_dist'],
                           ascending=[True, False], na_position='last'
                           ).reset_index(drop=True)


def kept_features(audit: pd.DataFrame) -> list[str]:
    """Danh sách cột được GIỮ — đầu vào của Phase 6."""
    return audit.loc[audit.quyet_dinh == 'GIU', 'feature'].tolist()
