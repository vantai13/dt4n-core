#!/usr/bin/env python3
"""EXPLORATORY: reconstruct all five IF seeds and evaluate hybrid rules.

This is reproduction, not re-decision: models and thresholds are already frozen.
Every reconstructed seed must reproduce the signed IF test TP/FP exactly before
any hybrid result is written.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import metrics as M
from ml.dataset import load_split
from ml.detectors import iforest as F
from scripts import run_phase6_iforest as R

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_hybrid_diag.json'
CV = REPORT / 'phase6_iforest_cv.json'
IFOREST = REPORT / 'phase6_iforest.json'
ENVELOPE = REPORT / 'phase6_envelope.json'
ENVELOPE_TICKS = REPORT / 'phase6_envelope_ticks.csv'
LEDGER_3 = REPORT / 'phase6_hypothesis_ledger_3.json'
PREREG = REPORT / 'phase6_prereg.json'
HASH_FIELD = 'content_sha256'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _verify_document(path, hash_field=HASH_FIELD):
    document = _read(path)
    if content_hash(document['content']) != document[hash_field]:
        raise RuntimeError('%s bi sua sau khi ky' % path.name)
    return document


def combine_flags(envelope_alarm, iforest_alarm,
                  envelope_judgeable, iforest_judgeable):
    """Pure Boolean hybrid logic, including the registered OR unknown rule."""
    arrays = [np.asarray(x, dtype=bool) for x in
              (envelope_alarm, iforest_alarm,
               envelope_judgeable, iforest_judgeable)]
    if any(x.ndim != 1 for x in arrays) or len({len(x) for x in arrays}) != 1:
        raise ValueError('hybrid inputs must be equal-length one-dimensional arrays')
    env_alarm, if_alarm, env_ok, if_ok = arrays
    if (env_alarm & ~env_ok).any() or (if_alarm & ~if_ok).any():
        raise ValueError('member alarmed on an unjudgeable row')
    common = env_ok & if_ok
    return {
        'excess': {'alarm': env_alarm, 'judgeable': env_ok},
        'excess_or_iforest': {
            'alarm': env_alarm | if_alarm,
            'judgeable': env_ok | if_ok,  # registered: unknown iff all unknown
        },
        'excess_and_iforest': {
            'alarm': env_alarm & if_alarm,
            'judgeable': common,
        },
        'common_judgeable': common,
    }


def reconstruct_and_verify(split, columns, cv, iforest,
                           q='0.01', max_samples=F.PRIMARY_MAX_SAMPLES):
    """Re-fit deterministic models and stop unless signed TP/FP are reproduced."""
    sealed = iforest['content']['configs'][str(max_samples)]['per_seed']
    X_train = F.matrix(split.X_train, columns)
    X_test = F.matrix(split.X_test, columns)
    y = split.y_test.to_numpy(dtype=bool)
    mask = split.eval_primary.to_numpy(dtype=bool)
    flags, checks, judgeable = {}, {}, None
    for seed in F.SEEDS:
        model = F.fit(X_train, seed=seed, max_samples=max_samples)
        frozen = cv['content']['final_thresholds'][str(max_samples)][str(seed)][
            'threshold_by_q'][q]
        train_scores = F.score(model, X_train)['score'].to_numpy()
        recalculated = F.threshold_from_train(train_scores, float(q))
        if recalculated != frozen:
            raise RuntimeError('nguong seed %d khong tai lap bit-exact' % seed)
        scores = F.score(model, X_test)
        fired = F.alarm(scores, frozen)
        expected = sealed[str(seed)]['by_q'][q]['scores']
        got_tp = int((y & mask & fired).sum())
        got_fp = int((~y & mask & fired).sum())
        if (got_tp, got_fp) != (expected['tp'], expected['fp']):
            raise RuntimeError(
                'tai lap seed %d khong khop artifact da ky: '
                'tp %d vs %d, fp %d vs %d' %
                (seed, got_tp, expected['tp'], got_fp, expected['fp']))
        current_judgeable = scores['judgeable'].to_numpy(dtype=bool)
        if judgeable is None:
            judgeable = current_judgeable
        elif not np.array_equal(judgeable, current_judgeable):
            raise RuntimeError('judgeable mask thay doi theo seed')
        flags[str(seed)] = fired
        checks[str(seed)] = {
            'threshold_frozen': frozen,
            'threshold_recalculated': recalculated,
            'threshold_bit_exact': True,
            'expected_tp': expected['tp'], 'reconstructed_tp': got_tp,
            'expected_fp': expected['fp'], 'reconstructed_fp': got_fp,
            'tp_fp_bit_exact': True,
        }
    return flags, judgeable, checks


def _frame(split, keys, faults, alarm, judgeable, eval_mask, mask_name):
    run_id = [key['run_id'] for key in keys]
    return M.build_frame(
        run_id=run_id, tick=[int(key['tick']) for key in keys],
        group=[rid[0] for rid in run_id],
        fault=[faults.get(rid) for rid in run_id],
        y=split.y_test.to_numpy(), eval_mask=eval_mask,
        judgeable=judgeable, alarm=alarm, mask_name=mask_name)


def _metrics(frame, uncertainty):
    boot = M.cluster_bootstrap(
        frame, n_boot=uncertainty['n_boot'], rng_seed=uncertainty['rng_seed'],
        ci=tuple(uncertainty['ci']))
    return {
        'scores': M.point_wise_scores(frame),
        'fpr': M.fpr_breakdown(frame),
        'bootstrap_recall_fpr': {
            'recall': boot['recall'], 'fpr': boot['fpr'],
            'method': boot['method'], 'rng_seed': boot['rng_seed'],
        },
    }


def _seed_summary(per_seed, section, variant, metric):
    return M.summarize_seeds(
        row[section][variant]['scores'][metric] for row in per_seed.values())


def current_content():
    cv = _verify_document(CV)
    iforest = _verify_document(IFOREST)
    envelope = _verify_document(ENVELOPE)
    prereg = _verify_document(PREREG, 'prereg_content_sha256')
    ledger3 = _verify_document(LEDGER_3, 'ledger_content_sha256')
    if C.sha256_file(ENVELOPE_TICKS) != envelope['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_envelope_ticks.csv bi sua')
    if iforest['content']['cv_content_sha256'] != cv['content_sha256']:
        raise RuntimeError('IF test khong tro toi CV hien tai')

    split = load_split()
    columns = R.frozen_columns_from_manifest()
    if columns != cv['content']['columns'] or sorted(split.feature_names) != columns:
        raise RuntimeError('tap cot tai lap lech tap cot da dong bang')
    flags, if_judgeable, checks = reconstruct_and_verify(
        split, columns, cv, iforest)

    ticks = pd.read_csv(ENVELOPE_TICKS)
    keys = split.meta['test_row_keys']
    expected_keys = pd.DataFrame(keys)
    if not ticks[['run_id', 'tick']].equals(expected_keys[['run_id', 'tick']]):
        raise RuntimeError('envelope ticks lech thu tu/khoa cua split')
    y = split.y_test.to_numpy(dtype=bool)
    if not np.array_equal(ticks['y'].to_numpy(dtype=bool), y):
        raise RuntimeError('nhan envelope ticks lech split')

    env_alarm = ticks['alarm_secondary_excess'].to_numpy(dtype=bool)
    env_judgeable = ticks['judgeable71'].to_numpy(dtype=bool)
    eval_primary = split.eval_primary.to_numpy(dtype=bool)
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {row['run_id']: row.get('fault') for row in contract['runs']}
    uncertainty = prereg['content']['metrics']['uncertainty']

    # Baseline bootstrap is seed-independent and stored once.
    env_frame = _frame(split, keys, faults, env_alarm, env_judgeable,
                       eval_primary, 'eval_primary')
    baseline = _metrics(env_frame, uncertainty)
    per_seed = {}
    for seed in F.SEEDS:
        hybrid = combine_flags(env_alarm, flags[str(seed)],
                               env_judgeable, if_judgeable)
        common = hybrid.pop('common_judgeable')
        primary = {}
        for name, values in hybrid.items():
            frame = _frame(split, keys, faults, values['alarm'],
                           values['judgeable'], eval_primary, 'eval_primary')
            primary[name] = _metrics(frame, uncertainty)

        common_eval = eval_primary & common
        common_results = {}
        for name, values in hybrid.items():
            common_alarm = values['alarm'] & common
            frame = _frame(split, keys, faults, common_alarm, common,
                           common_eval, 'common_judgeable_primary')
            common_results[name] = _metrics(frame, uncertainty)

        unique_tp = int((flags[str(seed)] & ~env_alarm & y & eval_primary).sum())
        added_fp = int((flags[str(seed)] & ~env_alarm & ~y & eval_primary).sum())
        common_unique_tp = int((flags[str(seed)] & ~env_alarm & y &
                                eval_primary & common).sum())
        common_added_fp = int((flags[str(seed)] & ~env_alarm & ~y &
                               eval_primary & common).sum())
        per_seed[str(seed)] = {
            'reconstruction_check': checks[str(seed)],
            'iforest_unique_true_positives': unique_tp,
            'added_false_positives': added_fp,
            'common_judgeable_unique_true_positives': common_unique_tp,
            'common_judgeable_added_false_positives': common_added_fp,
            'primary_all_rows': primary,
            'secondary_common_judgeable_rows': common_results,
        }

    summary = {}
    for section in ('primary_all_rows', 'secondary_common_judgeable_rows'):
        summary[section] = {
            variant: {
                metric: _seed_summary(per_seed, section, variant, metric)
                for metric in ('recall', 'fpr')
            }
            for variant in ('excess', 'excess_or_iforest',
                            'excess_and_iforest')
        }
    return {
        'diagnostic_id': 'DT4N-P6-HYBRID-POSTHOC-v1',
        'status': 'EXPLORATORY POST-FREEZE REPRODUCTION',
        'uses_test_labels': True,
        'follows_ledger_3_sha256': ledger3['ledger_content_sha256'],
        'authorises_no_change_to': ['detector', 'threshold', 'hypothesis',
                                    'column set'],
        'reproduction_definition': (
            'refit deterministic registered IF models with frozen CV thresholds; '
            'require exact signed-test TP/FP before evaluating hybrids'),
        'comparison_sets': {
            'primary_all_rows': (
                'all 590 eval_primary rows; registered unknown policies; OR is '
                'unknown iff both members are unknown'),
            'secondary_common_judgeable_rows': (
                'only rows judgeable by both members; identical denominator for '
                'excess, OR and AND'),
        },
        'bound_to': {
            'prereg_content_sha256': prereg['prereg_content_sha256'],
            'ledger_3_content_sha256': ledger3['ledger_content_sha256'],
            'iforest_cv_content_sha256': cv['content_sha256'],
            'iforest_test_content_sha256': iforest['content_sha256'],
            'envelope_test_content_sha256': envelope['content_sha256'],
            'envelope_ticks_sha256': C.sha256_file(ENVELOPE_TICKS),
        },
        'configuration': {
            'max_samples': F.PRIMARY_MAX_SAMPLES, 'q': F.PRIMARY_Q,
            'seeds': list(F.SEEDS), 'n_boot': uncertainty['n_boot'],
            'bootstrap_rng_seed': uncertainty['rng_seed'],
            'bootstrap_ci': uncertainty['ci'],
        },
        'n_rows': len(y),
        'n_common_judgeable_rows': int((env_judgeable & if_judgeable).sum()),
        'all_five_seeds_reproduced_exactly': all(
            row['tp_fp_bit_exact'] and row['threshold_bit_exact']
            for row in checks.values()),
        'envelope_excess_primary_baseline': baseline,
        'per_seed': per_seed,
        'across_seeds': summary,
    }


def main():
    if OUT.exists():
        print('[hybrid] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content, HASH_FIELD: content_hash(content),
    }
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    print('[hybrid] reproduction: 5/5 seeds TP/FP bit-exact')
    for seed, row in content['per_seed'].items():
        op = row['primary_all_rows']['excess_or_iforest']['scores']
        print('[hybrid] seed=%s unique_tp=%d added_fp=%d OR tp=%d fp=%d' %
              (seed, row['iforest_unique_true_positives'],
               row['added_false_positives'], op['tp'], op['fp']))
    print('[hybrid] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
