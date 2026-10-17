#!/usr/bin/env python3
"""Lesson 5.2 — phân tích dữ liệu thiếu trên dataset pilot v2.

CHẠY:   python3 -m scripts.analyze_missing
RA:     results/report/missing_analysis.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import numpy as np

from ml.flatten import load_many
from ml.missing import (apply_policy, assert_no_fabricated_zero_in_loss,
                        missing_by_profile, missing_by_tick_position,
                        missing_reasons, mnar_evidence, rate_fabrication_audit)
from scripts.audit_features import PILOT, sha256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/report'
WARMUP_TICKS = 1          # pilot ghi từ tick 0; Lesson 5.4 sẽ dùng 5
TOTAL_LIMIT_PCT = 5.0     # gate của plan


def main() -> int:
    import sys
    if "--campaign" in sys.argv:
        from scripts.analyze_ml_campaign import analyze
        return analyze(ROOT)
    df = load_many({ROOT / p: m for p, m in PILOT.items()})
    assert_no_fabricated_zero_in_loss(df)          # bất biến, kiểm TRƯỚC mọi thứ

    by_profile = missing_by_profile(df)
    clean, policy = apply_policy(df, warmup_ticks=WARMUP_TICKS)
    loss = [c for c in df.columns if c.endswith('.traffic.lossPct')]
    total_pct = 100.0 * df[loss].isna().to_numpy().sum() / df[loss].size

    spans = []
    for path in PILOT:
        for line in (ROOT / path).read_text().splitlines():
            snap = json.loads(line)
            times = [float(t['t_source']) for t in snap['things'].values() if t.get('t_source') is not None]
            if times:
                spans.append((max(times)-min(times))*1000)
    report = {
        'dataset': 'pilot v2 (3 segments, 150 snapshot)',
        'thing_timestamp_span_ms': {'n':len(spans), 'p50':float(np.percentile(spans,50)), 'p95':float(np.percentile(spans,95)), 'max':max(spans)},
        'sources': {p: {'sha256': sha256(ROOT / p), 'meta': m} for p,m in PILOT.items()},
        'total_pct_cells_missing': round(total_pct, 3),
        'gate_total_lt_5pct': bool(total_pct < TOTAL_LIMIT_PCT),
        'by_profile': by_profile.to_dict(orient='records'),
        'by_reason': (missing_reasons(df).groupby(['profile', 'reason'])['count']
                      .sum().reset_index().to_dict(orient='records')),
        'by_tick_position': missing_by_tick_position(df),
        'mnar_evidence': mnar_evidence(df),
        'rate_fabrication_channel_b': rate_fabrication_audit(df),
        'policy_applied': policy,
        'decision': {
            'name': 'DT4N-M1',
            'tier1_structural': f'bỏ {WARMUP_TICKS} tick đầu mỗi run (warmup)',
            'tier2_residual': 'giữ dòng + cột n_loss_missing; KHÔNG bỏ dòng',
            'tier3_train_only': 'dòng còn NaN ở feature train thì bỏ, có đếm',
            'inference_counterpart': ('Phase 7: detector KHÔNG phát trong warmup và '
                                      'ghi anomalyStatus="unknown" khi thiếu, '
                                      'không ghi "normal"'),
            'forbidden': 'fillna(0) cho lossPct ở mọi tầng',
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'missing_analysis.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    pd.set_option('display.width', 200)
    print(by_profile.to_string(index=False))
    ev = report['mnar_evidence']
    print(f"\nthô        : fault {ev['pct_missing_fault']}%  vs  normal {ev['pct_missing_normal']}%"
          f"   (Fisher p = {ev['fisher_p_two_sided']})")
    pw = ev['post_warmup']
    print(f"sau warmup : fault {pw['pct_missing_fault']}%  vs  normal {pw['pct_missing_normal']}%"
          f"   (CI95 fault {pw['ci95_fault_pct']})")
    print(f"cơ chế xác định được: {ev['mechanism_identified']}  ->  {ev['conclusion']}")
    fab = report['rate_fabrication_channel_b']
    print(f"\nkênh B (bịa số 0 ở rate): {fab['n_findings']} phát hiện {fab['by_kind']}")
    print(f"\nchính sách: bỏ {policy['rows_dropped_warmup']}/{policy['rows_before']} dòng warmup, "
          f"còn {policy['cells_missing_after']} ô thiếu")
    print(f"\n-> {OUT / 'missing_analysis.json'}")

    if total_pct >= TOTAL_LIMIT_PCT:
        print(f'\nGATE FAIL: thiếu {total_pct:.2f}% >= {TOTAL_LIMIT_PCT}%. Truy nguyên nhân.')
        return 1
    if not ev['mechanism_identified']:
        print('\nGATE FAIL: có lý do thiếu ngoài warmup. Điều tra trước khi đi tiếp.')
        return 1
    print('GATE PASS: thiếu < 5%, mọi ô thiếu được giải thích bởi warmup ở tick 0; chưa kết luận MNAR tổng quát.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
