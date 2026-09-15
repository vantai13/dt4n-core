#!/usr/bin/env python3
"""Lesson 5.1 — kiểm toán feature trên dataset pilot v2.

CHẠY:   python3 -m scripts.audit_features
RA:     results/report/feature_audit.csv
        results/report/feature_audit_summary.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import importlib.metadata
import platform

from ml.audit import audit_features, kept_features
from ml.flatten import load_many

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/report'

# Pilot v2: một lần chạy mỗi profile. `run_id` ở đây là TẠM — Lesson 5.3 sẽ
# sinh run_id thật. Nhưng đặt nó NGAY TỪ BÂY GIỜ để API không đổi về sau.
PILOT = {
    'logs/ml_normal_v2.jsonl':    {'profile': 'normal',    'run_id': 'pilot-normal-v2',    'is_fault': 0},
    'logs/ml_flood_v2.jsonl':     {'profile': 'flood',     'run_id': 'pilot-flood-v2',     'is_fault': 1},
    'logs/ml_injection_v2.jsonl': {'profile': 'injection', 'run_id': 'pilot-injection-v2', 'is_fault': 1},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()



def pilot_diagnostics(df: pd.DataFrame) -> dict:
    """Diagnostics preserve warmup and direction provenance of the raw pilot."""
    valid_cols = [c for c in df if c.endswith('.qdiscValid')]
    directions = [c for c in df if c.endswith('.utilDirectionSource')]
    profiles = {}
    for profile, group in df.groupby('profile', sort=False):
        invalid = group[valid_cols].eq(False)
        intervals = group.t_source.diff().dropna()
        reasons = {}
        for col in valid_cols:
            values = group.loc[invalid[col], col.replace('qdiscValid', 'qdiscReason')]
            for reason, count in values.value_counts().items():
                reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
        cumulative_corr = {}
        for col in group:
            if col.endswith(('.rxBytes', '.txBytes')):
                value = group[col].corr(group.tick)
                cumulative_corr[col] = float(value) if pd.notna(value) else None
        profiles[str(profile)] = {
            'n_snapshots': len(group), 'fault_label': int(group.is_fault.iloc[0]),
            'qdisc_link_samples': int(invalid.size),
            'qdisc_invalid': int(invalid.to_numpy().sum()),
            'qdisc_invalid_reasons': reasons,
            'qdisc_invalid_ticks': [int(t) for t in group.loc[invalid.any(axis=1), 'tick']],
            'interval_median_s': float(intervals.median()),
            'interval_min_s': float(intervals.min()), 'interval_max_s': float(intervals.max()),
            'scan_median_ms': float(group.cycle_scan_ms.median()),
            'cumulative_tick_pearson_diagnostic_only': cumulative_corr,
        }
    return {'profiles': profiles,
            'direction_sources': {c: {str(k): int(v) for k, v in df[c].value_counts().items()}
                                  for c in directions},
            'python': platform.python_version(),
            'packages': {p: importlib.metadata.version(p) for p in ('pandas', 'numpy', 'matplotlib')},
            'warning': 'Transport/load/profile and collection order are confounded; these are in-sample univariate statistics.'}


def main() -> int:
    spec = {ROOT / p: m for p, m in PILOT.items()}
    df = load_many(spec)
    audit = audit_features(df, fault_col='is_fault')

    OUT.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUT / 'feature_audit.csv', index=False)

    counts = audit.quyet_dinh.value_counts().to_dict()
    summary = {
        'n_snapshots': int(len(df)),
        'n_columns': int(len(df.columns) - 1),
        'by_decision': {k: int(v) for k, v in counts.items()},
        'kept': kept_features(audit),
        'n_auc_dist_gt_0_5': int(((audit.quyet_dinh == 'GIU') & (audit.auc_dist > 0.5)).sum()),
        'n_kept_d_pooled_gt_1': int(((audit.quyet_dinh == 'GIU') & (audit.d_pooled > 1)).sum()),
        'sources': {p: {'sha256': sha256(ROOT / p), 'meta': m}
                    for p, m in PILOT.items()},
        'separation_metric': 'AUC = P(fault > normal) + 0.5*P(tie); d_pooled uses pooled sample std',
        'audit_parameters': {'null_limit_pct': 50, 'auc_dist_min': 0.10, 'strong_auc_dist': 0.5},
        'gate_counts_only_kept_features': True,
        'scope': 'pilot 1 run/profile — KHÔNG phải bằng chứng hiệu năng ML',
        'gate': {'minimum_strong_kept': 5, 'pass': int(((audit.quyet_dinh == 'GIU') & (audit.auc_dist > 0.5)).sum()) >= 5},
        'diagnostics': pilot_diagnostics(df),
    }
    (OUT / 'feature_audit_summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    pd.set_option('display.width', 200)
    pd.set_option('display.float_format', lambda v: f'{v:,.3f}')
    print(f'snapshot = {len(df)}   cột = {len(df.columns) - 1}')
    print(audit.groupby(['quyet_dinh', 'kind']).size().to_string())
    print(f'\nGIỮ = {len(summary["kept"])} feature; '
          f'auc_dist > 0.5 ở {summary["n_auc_dist_gt_0_5"]} feature')
    print(f'\n-> {OUT / "feature_audit.csv"}')

    # GATE: không có feature nào tách biệt rõ -> dừng lại, đừng đi tiếp
    strong = int(((audit.quyet_dinh == 'GIU') & (audit.auc_dist > 0.5)).sum())
    if strong < 5:
        print('\nGATE FAIL: dưới 5 feature có auc_dist > 0.5. '
              'Sinh lại dữ liệu với profile tách bạch hơn trước khi qua Phase 6.')
        return 1
    print('GATE PASS: có >= 5 feature tách biệt rõ.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
