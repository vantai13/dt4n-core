#!/usr/bin/env python3
"""Run the frozen Phase 6.6 A1-A3 exploratory ablations."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import metrics as M
from ml.dataset import load_split
from ml.detectors import envelope as E
from ml.detectors import iforest as F
from scripts import run_phase6_envelope as ER
from scripts import run_phase6_iforest as IR

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_ablations.json'
PREREG = REPORT / 'phase6_ablation_prereg.json'
PHASE6_PREREG = REPORT / 'phase6_prereg.json'
HASH_FIELD = 'content_sha256'
CODE = C.ROOT / 'scripts/run_phase6_ablations.py'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text())


def verify_prereg():
    document = _read(PREREG)
    if content_hash(document['content']) != document['prereg_content_sha256']:
        raise RuntimeError('ablation prereg bi sua')
    if document['content']['knowledge_state']['A1_A2_A3_results_seen']:
        raise RuntimeError('ablation prereg khai da thay ket qua')
    dirty = subprocess.check_output(
        ['git', 'status', '--porcelain', '--', str(PREREG.relative_to(C.ROOT))],
        cwd=C.ROOT, text=True).strip()
    tracked = subprocess.run(
        ['git', 'ls-files', '--error-unmatch', str(PREREG.relative_to(C.ROOT))],
        cwd=C.ROOT, capture_output=True).returncode == 0
    if dirty or not tracked:
        raise RuntimeError('ablation prereg chua commit sach')
    return document


def ablation_columns(frozen):
    raw = F.base_columns(frozen)
    a1 = list(raw)
    a3 = [column for column in raw if not column.startswith('agg.')]
    if (len(frozen), len(a1), len(a3)) != (72, 36, 34):
        raise RuntimeError('unexpected ablation column counts')
    return {'A1_drop_delta': a1, 'A3_raw_no_agg': a3}


def _frame(split, keys, faults, alarm, judgeable):
    run_id = [key['run_id'] for key in keys]
    return M.build_frame(
        run_id=run_id, tick=[int(key['tick']) for key in keys],
        group=[rid[0] for rid in run_id], fault=[faults.get(rid) for rid in run_id],
        y=split.y_test.to_numpy(), eval_mask=split.eval_primary.to_numpy(),
        judgeable=judgeable, alarm=alarm, mask_name='eval_primary')


def _evaluate_frame(frame, uncertainty):
    return {
        'scores': M.point_wise_scores(frame), 'fpr': M.fpr_breakdown(frame),
        'by_fault': M.scores_by_fault(frame), 'delay': M.detection_delay(frame),
        'bootstrap': M.cluster_bootstrap(
            frame, n_boot=uncertainty['n_boot'], rng_seed=uncertainty['rng_seed'],
            ci=tuple(uncertainty['ci'])),
    }


def evaluate_if(split, columns, faults, uncertainty):
    X_train = F.matrix(split.X_train, columns)
    X_test = F.matrix(split.X_test, columns)
    keys = split.meta['test_row_keys']
    per_seed = {}
    for seed in F.SEEDS:
        model = F.fit(X_train, seed=seed, max_samples=F.PRIMARY_MAX_SAMPLES)
        train_scores = F.score(model, X_train)['score'].to_numpy()
        threshold = F.threshold_from_train(train_scores, F.PRIMARY_Q)
        test_scores = F.score(model, X_test)
        alarm = F.alarm(test_scores, threshold)
        frame = _frame(split, keys, faults, alarm,
                       test_scores.judgeable.to_numpy(dtype=bool))
        per_seed[str(seed)] = {
            'threshold': threshold, **_evaluate_frame(frame, uncertainty)}
    across = {
        metric: M.summarize_seeds(
            row['scores'][metric] for row in per_seed.values())
        for metric in ('recall', 'fpr', 'fpr_judgeable_only', 'precision', 'f1')
    }
    return {'n_features': len(columns), 'columns': columns,
            'n_train_rows': len(X_train), 'per_seed': per_seed,
            'across_seeds': across}


def _rolling(frame, columns, window=3):
    result = frame.copy()
    for column in columns:
        result[column] = result.groupby('run_id', sort=False)[column].transform(
            lambda values: values.rolling(window).mean().shift(1))
    return result


def rolling_envelope(split, families, faults, uncertainty, window=3):
    base = ER.load_train_base()
    pooled_k, pooled_excess, folds = [], [], []
    for fold, held, fit_frame, val_frame in E.fold_splits(base):
        fit_agg, val_agg = E._prepare(fit_frame, val_frame)
        fit_roll = _rolling(fit_agg, families['primary'], window)
        val_roll = _rolling(val_agg, families['primary'], window)
        bounds = E.fit_bounds(fit_roll, families['primary'])
        scores = E.score(val_roll, bounds, families['primary'])
        valid = scores[scores.judgeable]
        if valid.empty:
            raise RuntimeError('rolling envelope fold has no judgeable rows')
        pooled_k.extend(valid.k.tolist()); pooled_excess.extend(valid.excess.tolist())
        folds.append({'fold': fold, 'held_out_config': held,
                      'n_judgeable': len(valid), 'k_max': int(valid.k.max()),
                      'excess_max': float(valid.excess.max())})
    K, threshold = int(max(pooled_k)), float(max(pooled_excess))

    train = split.X_train_envelope.copy()
    train_keys = base[['run_id', 'tick']].reset_index(drop=True)
    if len(train) != len(train_keys):
        raise RuntimeError('rolling envelope train keys do not align')
    train = pd.concat([train_keys, train.reset_index(drop=True)], axis=1)
    test_keys = pd.DataFrame(split.meta['test_row_keys'])
    test = pd.concat([test_keys, split.X_test_envelope.reset_index(drop=True)], axis=1)
    train_roll = _rolling(train, families['primary'], window)
    test_roll = _rolling(test, families['primary'], window)
    bounds = E.fit_bounds(train_roll, families['primary'])
    scores = E.score(test_roll, bounds, families['primary'])
    alarm = E.alarm(scores, threshold, key='excess')
    frame = _frame(split, split.meta['test_row_keys'], faults, alarm,
                   scores.judgeable.to_numpy(dtype=bool))
    return {'window': window, 'n_columns': len(families['primary']),
            'calibration': {'rule': 'max held-out, strict >', 'K': K,
                            'E': threshold, 'folds': folds},
            **_evaluate_frame(frame, uncertainty)}


def current_content():
    prereg = verify_prereg()
    phase6 = _read(PHASE6_PREREG)
    if content_hash(phase6['content']) != phase6['prereg_content_sha256']:
        raise RuntimeError('phase6 prereg bi sua')
    uncertainty = phase6['content']['metrics']['uncertainty']
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {row['run_id']: row.get('fault') for row in contract['runs']}
    split = load_split()
    frozen = IR.frozen_columns_from_manifest()
    columns = ablation_columns(frozen)

    a1 = evaluate_if(split, columns['A1_drop_delta'], faults, uncertainty)
    rolling_split = load_split(use_rolling=True, rolling_window=3)
    a2_if = evaluate_if(rolling_split, sorted(rolling_split.feature_names),
                        faults, uncertainty)
    families = ER.families_from_registration()
    a2_env = rolling_envelope(split, families, faults, uncertainty)
    a3 = evaluate_if(split, columns['A3_raw_no_agg'], faults, uncertainty)

    a1_recall = a1['across_seeds']['recall']['mean']
    a3_recall = a3['across_seeds']['recall']['mean']
    a1_unknown_neg = {row['scores']['n_unknown_negative'] for row in a1['per_seed'].values()}
    a1_unknown_pos = {row['scores']['n_unknown_positive'] for row in a1['per_seed'].values()}
    a2_if_delays = [row['delay']['median_delay_detected']
                    for row in a2_if['per_seed'].values()]
    return {
        'result_id': 'DT4N-P6-ABLATIONS-v1',
        'status': 'EXPLORATORY; PREDICTIONS FROZEN BEFORE EXECUTION',
        'bound_to': {'ablation_prereg_sha256': prereg['prereg_content_sha256']},
        'code_sha256': C.sha256_file(CODE),
        'A1_drop_delta': a1,
        'A2_rolling_window3': {'iforest': a2_if, 'envelope_excess': a2_env},
        'A3_raw_no_agg': a3,
        'decisions': {
            'A1': {
                'status': ('supported' if a1_recall > .30 and
                           a1_unknown_neg == {8} else 'refuted'),
                'mean_recall': a1_recall,
                'unknown_negative': sorted(a1_unknown_neg),
                'unknown_positive': sorted(a1_unknown_pos),
                'registered_refutation': 'mean recall <=5% OR unknown_negative !=8',
            },
            'A2': {
                'status': ('supported' if
                           all(value is not None and value >= 1
                               for value in a2_if_delays) and
                           a2_env['delay']['median_delay_detected'] is not None and
                           a2_env['delay']['median_delay_detected'] >= 1
                           else 'refuted'),
                'iforest_delay_medians': a2_if_delays,
                'envelope_delay_median': a2_env['delay']['median_delay_detected'],
                'registered_refutation': 'delay does not increase for either detector',
            },
            'A3': {
                'status': 'supported' if a3_recall < a1_recall else 'refuted',
                'A1_mean_recall': a1_recall, 'A3_mean_recall': a3_recall,
                'registered_refutation': 'A3 recall >= A1 recall',
            },
            'A4': {'status': 'completed before ablation prereg',
                   'artifact_sha256': prereg['content']['ablations'][
                       'A4_mask_sensitivity']['artifact_sha256']},
        },
        'deviations': [],
    }


def main():
    if OUT.exists():
        print('[ablations] exists; refusing overwrite'); return 1
    content = current_content()
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, HASH_FIELD: content_hash(content)}
    with OUT.open('x') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    for name, row in content['decisions'].items():
        print('[ablations]', name, row['status'])
    print('[ablations] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
