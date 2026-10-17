#!/usr/bin/env python3
"""Lesson 6.5: evaluate frozen alarms under eval_sensitivity.

No detector or threshold is changed. IF flags are deterministically reproduced
and must match the signed primary-mask TP/FP before sensitivity metrics run.
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
from scripts import diag_phase6_hybrid as H
from scripts import run_phase6_iforest as R

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_sensitivity.json'
PREREG = REPORT / 'phase6_prereg.json'
ENV = REPORT / 'phase6_envelope.json'
ENV_TICKS = REPORT / 'phase6_envelope_ticks.csv'
IFOREST = REPORT / 'phase6_iforest.json'
CV = REPORT / 'phase6_iforest_cv.json'
LEDGER_3 = REPORT / 'phase6_hypothesis_ledger_3.json'
HYBRID = REPORT / 'phase6_hybrid_diag.json'
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


def _compact_bootstrap(frame, uncertainty):
    boot = M.cluster_bootstrap(
        frame, n_boot=uncertainty['n_boot'], rng_seed=uncertainty['rng_seed'],
        ci=tuple(uncertainty['ci']))
    return {'recall': boot['recall'], 'fpr': boot['fpr'],
            'method': boot['method'], 'rng_seed': boot['rng_seed']}


def _frame(split, keys, faults, alarm, judgeable, mask, mask_name):
    run_id = [key['run_id'] for key in keys]
    return M.build_frame(
        run_id=run_id, tick=[int(key['tick']) for key in keys],
        group=[rid[0] for rid in run_id], fault=[faults.get(rid) for rid in run_id],
        y=split.y_test.to_numpy(), eval_mask=mask, judgeable=judgeable,
        alarm=alarm, mask_name=mask_name)


def evaluate_pair(split, keys, faults, alarm, judgeable, uncertainty):
    primary_mask = split.eval_primary.to_numpy(dtype=bool)
    sensitivity_mask = split.eval_sensitivity.to_numpy(dtype=bool)
    results = {}
    for name, mask in (('eval_primary', primary_mask),
                       ('eval_sensitivity', sensitivity_mask)):
        frame = _frame(split, keys, faults, alarm, judgeable, mask, name)
        results[name] = {
            'scores': M.point_wise_scores(frame),
            'fpr': M.fpr_breakdown(frame),
            'by_fault': M.scores_by_fault(frame),
            'bootstrap_recall_fpr': _compact_bootstrap(frame, uncertainty),
        }
    y = split.y_test.to_numpy(dtype=bool)
    excluded = primary_mask & ~sensitivity_mask
    results['mask_effect'] = {
        'n_excluded': int(excluded.sum()),
        'n_excluded_positive': int((excluded & y).sum()),
        'n_excluded_negative': int((excluded & ~y).sum()),
        'alarms_excluded': int((excluded & alarm).sum()),
        'true_positive_alarms_excluded': int((excluded & alarm & y).sum()),
        'false_positive_alarms_excluded': int((excluded & alarm & ~y).sum()),
    }
    return results


def _summary(per_seed, mask, metric):
    return M.summarize_seeds(
        row[mask]['scores'][metric] for row in per_seed.values())


def _verify_primary(name, calculated, expected):
    got = calculated['eval_primary']['scores']
    if (got['tp'], got['fp'], got['fn'], got['tn']) != tuple(
            expected[key] for key in ('tp', 'fp', 'fn', 'tn')):
        raise RuntimeError('%s primary metrics lech artifact da ky' % name)


def current_content():
    prereg = _verify(PREREG, 'prereg_content_sha256')
    env_doc = _verify(ENV)
    if_doc = _verify(IFOREST)
    cv = _verify(CV)
    ledger = _verify(LEDGER_3, 'ledger_content_sha256')
    hybrid_doc = _verify(HYBRID)
    if C.sha256_file(ENV_TICKS) != env_doc['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_envelope_ticks.csv bi sua')

    split = load_split()
    keys = split.meta['test_row_keys']
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {row['run_id']: row.get('fault') for row in contract['runs']}
    uncertainty = prereg['content']['metrics']['uncertainty']
    columns = R.frozen_columns_from_manifest()
    if_flags, if_judgeable, reconstruction = H.reconstruct_and_verify(
        split, columns, cv, if_doc)

    ticks = pd.read_csv(ENV_TICKS)
    if not ticks[['run_id', 'tick']].equals(pd.DataFrame(keys)):
        raise RuntimeError('envelope ticks lech split')
    envelope_specs = {
        'primary_k': ('alarm_primary_k', 'judgeable71'),
        'secondary_excess': ('alarm_secondary_excess', 'judgeable71'),
        'secondary_dual': ('alarm_secondary_dual', 'judgeable71'),
        'ablation_loss_only': ('alarm_ablation_loss_only', 'judgeable_loss'),
    }
    envelope = {}
    for name, (alarm_col, judge_col) in envelope_specs.items():
        result = evaluate_pair(
            split, keys, faults, ticks[alarm_col].to_numpy(dtype=bool),
            ticks[judge_col].to_numpy(dtype=bool), uncertainty)
        _verify_primary(name, result, env_doc['content']['variants'][name]['scores'])
        envelope[name] = result

    iforest = {}
    for seed in F.SEEDS:
        result = evaluate_pair(split, keys, faults, if_flags[str(seed)],
                               if_judgeable, uncertainty)
        expected = if_doc['content']['configs']['256']['per_seed'][str(seed)][
            'by_q']['0.01']['scores']
        _verify_primary('iforest_seed_' + str(seed), result, expected)
        result['reconstruction_check'] = reconstruction[str(seed)]
        iforest[str(seed)] = result

    hybrid = {'literal_primary_k_or_iforest': {},
              'secondary_excess_or_iforest': {}}
    env_judgeable = ticks.judgeable71.to_numpy(dtype=bool)
    for seed in F.SEEDS:
        for label, column in (
                ('literal_primary_k_or_iforest', 'alarm_primary_k'),
                ('secondary_excess_or_iforest', 'alarm_secondary_excess')):
            combined = H.combine_flags(
                ticks[column].to_numpy(dtype=bool), if_flags[str(seed)],
                env_judgeable, if_judgeable)['excess_or_iforest']
            result = evaluate_pair(split, keys, faults, combined['alarm'],
                                   combined['judgeable'], uncertainty)
            if label == 'secondary_excess_or_iforest':
                signed = hybrid_doc['content']['per_seed'][str(seed)][
                    'primary_all_rows']['excess_or_iforest']['scores']
                _verify_primary(label + '_seed_' + str(seed), result, signed)
            hybrid[label][str(seed)] = result

    across = {
        'iforest': {mask: {metric: _summary(iforest, mask, metric)
                           for metric in ('recall', 'fpr')}
                     for mask in ('eval_primary', 'eval_sensitivity')},
    }
    for label, rows in hybrid.items():
        across[label] = {
            mask: {metric: _summary(rows, mask, metric)
                   for metric in ('recall', 'fpr')}
            for mask in ('eval_primary', 'eval_sensitivity')}

    primary_mask = split.eval_primary.to_numpy(dtype=bool)
    sensitivity_mask = split.eval_sensitivity.to_numpy(dtype=bool)
    y = split.y_test.to_numpy(dtype=bool)
    excluded = primary_mask & ~sensitivity_mask
    return {
        'diagnostic_id': 'DT4N-P6-EVAL-SENSITIVITY-v1',
        'status': 'POST-FREEZE MASK SENSITIVITY; NO REFIT DECISION',
        'uses_test_labels': True,
        'follows_ledger_3_sha256': ledger['ledger_content_sha256'],
        'bound_to': {
            'prereg_content_sha256': prereg['prereg_content_sha256'],
            'envelope_content_sha256': env_doc['content_sha256'],
            'iforest_content_sha256': if_doc['content_sha256'],
            'iforest_cv_content_sha256': cv['content_sha256'],
            'hybrid_content_sha256': hybrid_doc['content_sha256'],
            'envelope_ticks_sha256': C.sha256_file(ENV_TICKS),
        },
        'mask_counts': {
            'eval_primary': {'n': int(primary_mask.sum()),
                             'positive': int((primary_mask & y).sum()),
                             'negative': int((primary_mask & ~y).sum())},
            'eval_sensitivity': {'n': int(sensitivity_mask.sum()),
                                 'positive': int((sensitivity_mask & y).sum()),
                                 'negative': int((sensitivity_mask & ~y).sum())},
            'excluded_transition_ticks': {
                'n': int(excluded.sum()), 'positive': int((excluded & y).sum()),
                'negative': int((excluded & ~y).sum())},
        },
        'hybrid_under_specification': {
            'reported_both_readings': True,
            'literal': 'primary_k OR iforest',
            'secondary_reading': 'secondary_excess OR iforest',
        },
        'configuration': {
            'iforest_max_samples': F.PRIMARY_MAX_SAMPLES,
            'iforest_q': F.PRIMARY_Q, 'seeds': list(F.SEEDS),
            'n_boot': uncertainty['n_boot'],
            'bootstrap_rng_seed': uncertainty['rng_seed'],
            'bootstrap_ci': uncertainty['ci'],
        },
        'envelope': envelope, 'iforest': iforest, 'hybrid': hybrid,
        'across_seeds': across,
    }


def main():
    if OUT.exists():
        print('[sensitivity] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content, HASH_FIELD: content_hash(content),
    }
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    for name in ('primary_k', 'secondary_excess', 'secondary_dual'):
        row = content['envelope'][name]
        p, s = row['eval_primary']['scores'], row['eval_sensitivity']['scores']
        print('[sensitivity] %-18s recall %.4f -> %.4f; FPR %.4f -> %.4f; control %.4f -> %.4f' %
              (name, p['recall'], s['recall'], p['fpr'], s['fpr'],
               row['eval_primary']['fpr']['control']['fpr'],
               row['eval_sensitivity']['fpr']['control']['fpr']))
    print('[sensitivity] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
