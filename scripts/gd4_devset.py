#!/usr/bin/env python3
"""
gd4_devset.py — GĐ4: hai phân tích MÔ TẢ trên tập phát triển (đã mở từ Phase 6), bản 2.1.

  1. Báo nhầm theo vị trí của excess và dual: cụm báo nhầm sau khi gỡ sự cố dài bao nhiêu
     giây (bản cũ: 23 lần excess ở giây 41–47, cụm 7 giây). Cửa sổ ức chế 8 s KHÔNG đổi
     theo kết quả này (results/gd4/deviation_2.md).
  2. Isolation Forest học lại trên tập train sạch: cùng 72 cột đã đăng ký, max_samples 256,
     ngưỡng q = 0,01 từ điểm train, 5 seed, cùng hàm chấm của scripts/run_phase6_iforest.py.

Mỗi phần phải tái lập ĐÚNG số Phase 6 với tập train cũ (v1) trước khi tính cho v21; lệch thì
dừng, không ghi kết quả.

    python3 scripts/gd4_devset.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402
from ml import gd2_envelope as GE  # noqa: E402
from ml import gd4_retrain as R  # noqa: E402
from ml.detectors import envelope as E  # noqa: E402
from ml.detectors import iforest as F  # noqa: E402
from ml.features import add_aggregate_features, add_delta_features, select_features  # noqa: E402
from ml.missing import apply_policy  # noqa: E402

OUT = C.ROOT / 'results/report/gd4_devset.json'
REVERT_TICK = 40


# ---------------------------------------------------------------- 1. envelope theo vị trí
def envelope_ticks(variant: str):
    from scripts.run_phase6_envelope import evaluate, families_from_registration, \
        verify_registration
    fam = families_from_registration()
    unc = verify_registration()['prereg']['content']['metrics']['uncertainty']
    train_raw, test_raw, warmup, used = R.load_raw(variant, C.ROOT)
    base, _ = apply_policy(train_raw, warmup_ticks=warmup)
    base = base.sort_values(['run_id', 'tick']).reset_index(drop=True)
    calib = E.heldout_calibration(base, fam)
    tr, _ = apply_policy(train_raw, warmup_ticks=warmup)
    te, _ = apply_policy(test_raw, warmup_ticks=warmup)
    tr, link_stats = add_aggregate_features(tr, link_stats=None)
    te, _ = add_aggregate_features(te, link_stats=link_stats)
    cols = fam['primary']
    for frame in (tr, te):
        frame[cols] = frame[cols].apply(pd.to_numeric, errors='coerce').replace(
            [np.inf, -np.inf], np.nan)
    tr = tr.sort_values(['run_id', 'tick']).reset_index(drop=True)
    te = te.sort_values(['run_id', 'tick']).reset_index(drop=True)
    p5 = C.load_contract(C.ROOT / GE.P5_CONTRACT)
    faults = {r['run_id']: r.get('fault') for r in p5['runs']}
    report, ticks = evaluate(fam=fam, X_train_env=tr[cols], X_test_env=te[cols],
                             keys=te[['run_id', 'tick']].to_dict('records'),
                             y=te['is_fault'].to_numpy(), eval_primary=te['eval_primary'].to_numpy(),
                             faults=faults, thresholds=calib['thresholds'],
                             n_boot=unc['n_boot'], rng_seed=unc['rng_seed'])
    return report, ticks, calib['thresholds']


def false_alarm_positions(ticks: pd.DataFrame, column: str) -> dict:
    fp = ticks[(ticks['y'] == 0) & ticks[column].astype(bool)]
    by_tick = fp.groupby('tick').size().to_dict()
    clusters = {}
    for rid, g in ticks[ticks.run_id.str.startswith('F-')].groupby('run_id'):
        alarmed = set(g.loc[g[column].astype(bool) & (g['y'] == 0), 'tick'])
        n, t = 0, REVERT_TICK + 1
        while t in alarmed:
            n, t = n + 1, t + 1
        clusters[rid] = n
    post = fp[fp.tick > REVERT_TICK]
    return {
        'n_false_alarms': int(len(fp)),
        'n_in_normal_runs': int(fp.run_id.str.startswith('C-').sum()),
        'n_before_inject': int((fp.tick <= 20).sum()),
        'by_tick': {int(k): int(v) for k, v in sorted(by_tick.items())},
        'post_revert_ticks_span': ([int(post.tick.min()), int(post.tick.max())]
                                   if len(post) else None),
        'longest_post_revert_cluster_s': max(clusters.values()) if clusters else 0,
        'cluster_by_run': clusters,
    }


def envelope_part() -> dict:
    out = {}
    pub = json.loads((C.ROOT / 'results/report/phase6_envelope.json').read_text())['content']
    for variant in ('v1', 'v21'):
        report, ticks, thresholds = envelope_ticks(variant)
        if variant == 'v1':
            for name in ('secondary_excess', 'secondary_dual'):
                a, b = report[name]['scores'], pub['variants'][name]['scores']
                if (a['tp'], a['fp'], a['fn']) != (b['tp'], b['fp'], b['fn']):
                    raise SystemExit('v1 không tái lập Phase 6: %s' % name)
        out[variant] = {
            'thresholds': {k: {'K': v['K'], 'E': v['E']} for k, v in thresholds.items()},
            **{name: {
                'recall': report[name]['scores']['recall'],
                'fpr': report[name]['scores']['fpr'],
                'tp': report[name]['scores']['tp'], 'fp': report[name]['scores']['fp'],
                'n_positive': report[name]['scores']['n_positive'],
                'n_negative': report[name]['scores']['n_negative'],
                'recall_by_fault': {f: v['pooled']['recall']
                                    for f, v in report[name]['by_fault'].items()},
                'positions': false_alarm_positions(ticks, 'alarm_' + name),
            } for name in ('secondary_excess', 'secondary_dual')},
            'by_run_detected_ticks': {
                rid: {name: int(g.loc[g.y == 1, 'alarm_' + name].astype(bool).sum())
                      for name in ('secondary_excess', 'secondary_dual')}
                for rid, g in ticks[ticks.run_id.str.startswith('F-')].groupby('run_id')},
        }
    v1 = out['v1']['secondary_excess']['positions']
    if v1['n_false_alarms'] != 23 or v1['longest_post_revert_cluster_s'] != 7:
        raise SystemExit('v1 không tái lập vị trí báo nhầm 23 lần / cụm 7 giây: %s' % v1)
    return out


# ---------------------------------------------------------------- 2. Isolation Forest
def if_matrices(variant: str, columns: list[str]):
    """Đúng các bước của ml.dataset.load_split, chỉ đổi nguồn train."""
    train_raw, test_raw, warmup, used = R.load_raw(variant, C.ROOT)
    tr, _ = apply_policy(train_raw, warmup_ticks=warmup)
    te, _ = apply_policy(test_raw, warmup_ticks=warmup)
    tr, link_stats = add_aggregate_features(tr, link_stats=None)
    te, _ = add_aggregate_features(te, link_stats=link_stats)
    env_cols = sorted(select_features(tr)['envelope'])
    for frame in (tr, te):
        frame[env_cols] = frame[env_cols].apply(pd.to_numeric, errors='coerce').replace(
            [float('inf'), -float('inf')], float('nan'))
    feats = [c for c in columns if not c.startswith('d1.')]
    tr = add_delta_features(tr, feats)
    te = add_delta_features(te, feats)
    for frame in (tr, te):
        frame[columns] = frame[columns].apply(pd.to_numeric, errors='coerce').replace(
            [float('inf'), -float('inf')], float('nan'))
    tr = tr.sort_values(['run_id', 'tick']).reset_index(drop=True)
    te = te.sort_values(['run_id', 'tick']).reset_index(drop=True)
    tr_ok = tr.loc[tr[columns].notna().all(axis=1)].copy()
    return tr_ok, te, used


def iforest_part() -> dict:
    from scripts.run_phase6_iforest import evaluate_one, frozen_columns_from_manifest, \
        verify_registration
    from ml.dataset import load_split
    columns = frozen_columns_from_manifest()
    unc = verify_registration()['prereg']['content']['metrics']['uncertainty']
    p5 = C.load_contract(C.ROOT / GE.P5_CONTRACT)
    faults = {r['run_id']: r.get('fault') for r in p5['runs']}

    # Tái lập ma trận: v1 qua đường mới phải bằng đúng load_split()
    split = load_split()
    tr1, te1, _ = if_matrices('v1', columns)
    same = (np.array_equal(F.matrix(tr1, columns).to_numpy(),
                           F.matrix(split.X_train, columns).to_numpy(), equal_nan=True)
            and np.array_equal(F.matrix(te1, columns).to_numpy(),
                               F.matrix(split.X_test, columns).to_numpy(), equal_nan=True))
    if not same:
        raise SystemExit('ma trận IF dựng lại không khớp load_split() với train cũ')

    pub = json.loads((C.ROOT / 'results/report/phase6_iforest.json').read_text())['content']
    pub_row = pub['configs'][str(F.PRIMARY_MAX_SAMPLES)]['across_seeds'][str(F.PRIMARY_Q)]
    out = {'columns': len(columns), 'max_samples': F.PRIMARY_MAX_SAMPLES,
           'q': F.PRIMARY_Q, 'seeds': list(F.SEEDS)}
    for variant in ('v1', 'v21'):
        tr, te, used = if_matrices(variant, columns)
        X_train, X_test = F.matrix(tr, columns), F.matrix(te, columns)
        keys = te[['run_id', 'tick']].to_dict('records')
        y, eval_primary = te['is_fault'].to_numpy(), te['eval_primary'].to_numpy()
        per_seed = {}
        for seed in F.SEEDS:
            model = F.fit(X_train, seed=seed, max_samples=F.PRIMARY_MAX_SAMPLES)
            train_scores = F.score(model, X_train)['score'].to_numpy()
            rep, _ = evaluate_one(model_scores_train=train_scores,
                                  model_scores_test=F.score(model, X_test), keys=keys, y=y,
                                  eval_primary=eval_primary, faults=faults, q=F.PRIMARY_Q,
                                  n_boot=unc['n_boot'], rng_seed=unc['rng_seed'])
            per_seed[str(seed)] = {k: rep['scores'][k] for k in ('recall', 'fpr', 'tp', 'fp')}
        out[variant] = {'n_train_rows': len(X_train), 'train_run_ids': used,
                        'recall_mean': float(np.mean([v['recall'] for v in per_seed.values()])),
                        'fpr_mean': float(np.mean([v['fpr'] for v in per_seed.values()])),
                        'per_seed': per_seed}
    if (abs(out['v1']['recall_mean'] - pub_row['recall']['mean']) > 1e-12
            or abs(out['v1']['fpr_mean'] - pub_row['fpr']['mean']) > 1e-12):
        raise SystemExit('IF v1 không tái lập Phase 6: %s vs %s' % (out['v1'], pub_row))
    out['v1_reproduces_phase6'] = True
    return out


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    content = {'note': ('Tập phát triển đã mở từ Phase 6: mọi số ở đây chỉ mô tả. Cửa sổ ức '
                        'chế 8 s không đổi theo kết quả này.'),
               'envelope': envelope_part(), 'iforest': iforest_part(),
               'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    C.atomic_json(OUT, {'content': content, 'content_sha256': C.sha256_bytes(
        C.canonical_json(content).encode('utf-8'))})
    for v in ('v1', 'v21'):
        e = content['envelope'][v]
        for name in ('secondary_excess', 'secondary_dual'):
            x = e[name]; p = x['positions']
            print('%-4s %-17s recall %.4f FPR %.4f | báo nhầm %d (C %d, trước sự cố %d) '
                  'giây %s, cụm sau gỡ dài nhất %d s' % (
                      v, name, x['recall'], x['fpr'], p['n_false_alarms'], p['n_in_normal_runs'],
                      p['n_before_inject'], p['post_revert_ticks_span'],
                      p['longest_post_revert_cluster_s']))
        print('     theo loại sự cố (dual):', {k: round(val, 3) for k, val in
                                                e['secondary_dual']['recall_by_fault'].items()})
        i = content['iforest'][v]
        print('     IF recall %.5f FPR %.4f (%d dòng train)' % (
            i['recall_mean'], i['fpr_mean'], i['n_train_rows']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
