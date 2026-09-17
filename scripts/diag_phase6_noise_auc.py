#!/usr/bin/env python3
"""Phase 6 step 3: ranking AUC for the registered Gaussian noise control.

EXPLORATORY POST-FREEZE. Test labels are used only for diagnosis. This script
does not change a detector, threshold, hypothesis, feature set, or decision.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml import campaign as C
from ml.detectors import iforest as F

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_noise_auc.json'
IFOREST = REPORT / 'phase6_iforest.json'
IF_TICKS = REPORT / 'phase6_iforest_ticks.csv'
LEDGER_3 = REPORT / 'phase6_hypothesis_ledger_3.json'
PREREG = REPORT / 'phase6_prereg.json'
HASH_FIELD = 'content_sha256'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _verify(path, hash_field=HASH_FIELD):
    document = _read(path)
    if content_hash(document['content']) != document[hash_field]:
        raise RuntimeError('%s bi sua sau khi ky' % path.name)
    return document


def auc_lower_is_anomalous(scores, labels):
    """AUC where a lower score means more anomalous; ties contribute 0.5.

    For every positive score, count negatives to its right (higher score,
    therefore less anomalous), plus half of equal-score negatives.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels)
    if scores.ndim != 1 or labels.ndim != 1 or len(scores) != len(labels):
        raise ValueError('scores and labels must be equal-length 1-D arrays')
    if not np.isfinite(scores).all():
        raise ValueError('scores must be finite after applying the mask')
    if not np.isin(labels, (0, 1, False, True)).all():
        raise ValueError('labels must be binary')
    labels = labels.astype(bool)
    pos = np.sort(scores[labels])
    neg = np.sort(scores[~labels])
    if len(pos) == 0 or len(neg) == 0:
        return None
    total = 0.0
    for score in pos:
        left = np.searchsorted(neg, score, side='left')
        right = np.searchsorted(neg, score, side='right')
        total += len(neg) - right + 0.5 * (right - left)
    return float(total / (len(pos) * len(neg)))


def _distribution(values):
    values = np.asarray(values, dtype=float)
    return {
        'mean': float(np.mean(values)),
        'std': float(np.std(values, ddof=1)),
        'min': float(np.min(values)), 'max': float(np.max(values)),
    }


def current_content():
    iforest = _verify(IFOREST)
    ledger = _verify(LEDGER_3, 'ledger_content_sha256')
    prereg = _verify(PREREG, 'prereg_content_sha256')
    if C.sha256_file(IF_TICKS) != iforest['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_iforest_ticks.csv bi sua')

    ticks = pd.read_csv(IF_TICKS)
    y = ticks.y.to_numpy(dtype=bool)
    judgeable = ticks.judgeable.to_numpy(dtype=bool)
    real_scores = ticks.score.to_numpy(dtype=float)
    real_auc = auc_lower_is_anomalous(real_scores[judgeable], y[judgeable])

    registered = prereg['content']['detectors']['random_noise_control']
    if registered['seeds'] != list(F.SEEDS):
        raise RuntimeError('noise seeds lech prereg')
    sealed = iforest['content']['noise_control']['per_seed']
    n_train = sealed['0']['n_train']
    n_test = sealed['0']['n_test']
    n_features = sealed['0']['n_features']
    if (n_train, n_test, n_features) != (464, 590, 72):
        raise RuntimeError('noise shape lech registered campaign shape')

    per_seed = {}
    for seed in F.SEEDS:
        rng = np.random.default_rng(F.NOISE_RNG_BASE + seed)
        train = pd.DataFrame(rng.normal(size=(n_train, n_features)))
        test = pd.DataFrame(rng.normal(size=(n_test, n_features)))
        model = F.fit(train, seed=seed, max_samples=F.PRIMARY_MAX_SAMPLES)
        train_scores = F.score(model, train)['score'].to_numpy()
        threshold = F.threshold_from_train(train_scores, F.PRIMARY_Q)
        noise_scores = F.score(model, test)
        fired_raw = F.alarm(noise_scores, threshold)
        fired_masked = fired_raw & judgeable
        expected = sealed[str(seed)]
        expected_metrics = expected['metrics']['scores']
        got_tp = int((fired_masked & y).sum())
        got_fp = int((fired_masked & ~y).sum())
        threshold_exact = threshold == expected['threshold']
        raw_alarm_exact = int(fired_raw.sum()) == expected['n_alarm']
        tp_fp_exact = (got_tp, got_fp) == (
            expected_metrics['tp'], expected_metrics['fp'])
        if not (threshold_exact and raw_alarm_exact and tp_fp_exact):
            raise RuntimeError('noise seed %d khong tai lap artifact da ky' % seed)
        auc = auc_lower_is_anomalous(
            noise_scores.loc[judgeable, 'score'].to_numpy(), y[judgeable])
        per_seed[str(seed)] = {
            'auc_noise': auc,
            'n_judgeable': int(judgeable.sum()),
            'n_positive_judgeable': int((y & judgeable).sum()),
            'n_negative_judgeable': int((~y & judgeable).sum()),
            'reproduction_check': {
                'threshold_expected': expected['threshold'],
                'threshold_reconstructed': threshold,
                'threshold_bit_exact': threshold_exact,
                'raw_n_alarm_expected': expected['n_alarm'],
                'raw_n_alarm_reconstructed': int(fired_raw.sum()),
                'raw_n_alarm_exact': raw_alarm_exact,
                'masked_tp_expected': expected_metrics['tp'],
                'masked_tp_reconstructed': got_tp,
                'masked_fp_expected': expected_metrics['fp'],
                'masked_fp_reconstructed': got_fp,
                'masked_tp_fp_exact': tp_fp_exact,
            },
        }

    aucs = [row['auc_noise'] for row in per_seed.values()]
    summary = {
        'auc_noise': _distribution(aucs),
        'auc_real_seed0': real_auc,
        'real_minus_noise_mean': real_auc - float(np.mean(aucs)),
        'noise_auc_mean_in_predeclared_sanity_range_0_45_0_55': bool(
            0.45 <= float(np.mean(aucs)) <= 0.55),
        'n_individual_seeds_in_0_45_0_55': int(
            sum(0.45 <= value <= 0.55 for value in aucs)),
        'individual_seed_range_note': (
            'The preregistered control is summarized over five seeds; the '
            'sanity gate applies to that mean. Individual finite-sample AUCs '
            'are retained without clipping.'),
        'all_five_noise_arms_reproduced_exactly': all(
            all(check[key] for key in (
                'threshold_bit_exact', 'raw_n_alarm_exact',
                'masked_tp_fp_exact'))
            for check in (row['reproduction_check']
                          for row in per_seed.values())),
    }
    return {
        'diagnostic_id': 'DT4N-P6-NOISE-AUC-v1',
        'status': 'EXPLORATORY POST-FREEZE',
        'uses_test_labels': True,
        'authorises_no_change_to': ['detector', 'threshold', 'hypothesis',
                                    'column set'],
        'follows_ledger_3_sha256': ledger['ledger_content_sha256'],
        'bound_to': {
            'prereg_content_sha256': prereg['prereg_content_sha256'],
            'iforest_content_sha256': iforest['content_sha256'],
            'iforest_ticks_sha256': C.sha256_file(IF_TICKS),
        },
        'rng_rule': registered['rng_rule'],
        'mask': 'campaign IF judgeable mask (equal coverage)',
        'auc_definition': (
            'probability a positive has a lower score than a negative; '
            'ties contribute 0.5'),
        'shape': {'train': [n_train, n_features],
                  'test': [n_test, n_features]},
        'per_seed': per_seed,
        'summary': summary,
        'interpretation': (
            'campaign IF contains ranking signal relative to Gaussian noise, '
            'but that signal does not yield useful recall at the registered '
            'low-FPR operating threshold'),
    }


def main():
    if OUT.exists():
        print('[noise-auc] exists; refusing overwrite')
        return 1
    content = current_content()
    summary = content['summary']
    if not summary['noise_auc_mean_in_predeclared_sanity_range_0_45_0_55']:
        print('[noise-auc] STOP: mean noise AUC is outside [0.45, 0.55]')
        return 2
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content, HASH_FIELD: content_hash(content),
    }
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    for seed, row in content['per_seed'].items():
        print('[noise-auc] seed=%s AUC=%.6f reproduction=exact' %
              (seed, row['auc_noise']))
    noise = summary['auc_noise']
    print('[noise-auc] noise mean=%.6f std=%.6f range=[%.6f, %.6f]' %
          (noise['mean'], noise['std'], noise['min'], noise['max']))
    print('[noise-auc] real seed0=%.6f gap=%.6f' %
          (summary['auc_real_seed0'], summary['real_minus_noise_mean']))
    print('[noise-auc] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
