#!/usr/bin/env python3
"""Exploratory post-freeze diagnostics; never authorises detector changes."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ml.campaign import ROOT, canonical_json, sha256_bytes, sha256_file

REPORT = ROOT / 'results/report'
OUT = REPORT / 'phase6_envelope_posthoc_diag.json'
TEST = REPORT / 'phase6_envelope.json'
CV = REPORT / 'phase6_envelope_cv.json'
AM1 = REPORT / 'phase6_prereg_amendment_1.json'
TICKS = REPORT / 'phase6_envelope_ticks.csv'
HASH_FIELD = 'content_sha256'
QUANTILES = (0.90, 0.95, 0.975, 0.99, 1.00)


def content_hash(value):
    return sha256_bytes(canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sealed_inputs():
    test, cv, amendment1 = _read(TEST), _read(CV), _read(AM1)
    if content_hash(test['content']) != test[HASH_FIELD]:
        raise ValueError('phase6_envelope.json bi sua')
    if content_hash(cv['content']) != cv[HASH_FIELD]:
        raise ValueError('phase6_envelope_cv.json bi sua')
    if content_hash(amendment1['content']) != amendment1['amendment_content_sha256']:
        raise ValueError('phase6_prereg_amendment_1.json bi sua')
    if test['content']['cv_content_sha256'] != cv[HASH_FIELD]:
        raise ValueError('chuoi tham chieu test -> cv bi dut')
    if test['content']['ticks_csv_sha256'] != sha256_file(TICKS):
        raise ValueError('bang tick khong con khop hash da ky')
    return test, cv, amendment1


def separability(ticks):
    judged = ticks[ticks.judgeable71]
    y = judged.y.to_numpy()
    positive = judged.k[y == 1]
    negative = judged.k[y == 0]
    negative_max = negative.max()
    return {
        'n_judgeable_positive': int(y.sum()),
        'n_judgeable_negative': int((1 - y).sum()),
        'auc_k': float(roc_auc_score(y, judged.k)),
        'auc_excess': float(roc_auc_score(y, judged.excess)),
        'k_positive_median': float(positive.median()),
        'k_positive_max': int(positive.max()),
        'k_negative_max': int(negative_max),
        'k_negative_max_run': str(judged.run_id[(y == 0) &
                                                 (judged.k == negative_max)].iloc[0]),
        'excess_positive_median': float(judged.excess[y == 1].median()),
        'excess_negative_max': float(judged.excess[y == 0].max()),
    }


def oracle_sweep(ticks):
    judged = ticks[ticks.judgeable71]
    n_positive = int(ticks.y.sum())
    n_negative = int((1 - ticks.y).sum())
    rows = []
    for threshold in range(0, int(ticks.k.max()) + 1):
        alarms = judged.k > threshold
        rows.append({
            'threshold_k_gt': threshold,
            'recall': float(((judged.y == 1) & alarms).sum() / n_positive),
            'fpr': float(((judged.y == 0) & alarms).sum() / n_negative),
        })
    best = max(rows, key=lambda row: row['recall'] - row['fpr'])
    return {
        'sweep': rows,
        'best_by_youden_j': best,
        'caveat': 'oracle: thresholds scanned on labelled test; never reportable as performance',
    }


def quantile_alternatives(cv):
    pooled = []
    for fold in cv['content']['folds']:
        distribution = fold['families']['primary']['k_distribution']
        for value, count in distribution.items():
            pooled.extend([int(value)] * count)
    pooled = np.asarray(pooled)
    return {
        'n_pooled_heldout_rows': int(pooled.size),
        'registered_rule': 'K = max held-out k',
        'registered_K': int(pooled.max()),
        'alternative_K_by_quantile': {
            str(q): float(np.quantile(pooled, q)) for q in QUANTILES},
        'mean_heldout_k': float(pooled.mean()),
    }


def structural_reachability(amendment1, registered_K):
    secondary = amendment1['content']['secondary_detector']
    columns = sorted(secondary['indicator_columns'] + secondary['rate_shared_columns'])
    per_entity = {}
    for column in columns:
        entity = column.split('.')[0]
        per_entity[entity] = per_entity.get(entity, 0) + 1
    aggregate = per_entity.get('agg', 0)
    link = max(value for key, value in per_entity.items() if key.startswith('link-'))
    host = max(value for key, value in per_entity.items() if key.startswith('host-'))
    bound = link + 2 * host + aggregate
    return {
        'n_registered_columns': len(columns),
        'columns_per_link': link,
        'columns_per_host': host,
        'columns_agg': aggregate,
        'generous_upper_bound_single_link_fault': bound,
        'registered_K': registered_K,
        'K_reachable_by_single_link_fault': registered_K < bound,
        'K_as_share_of_all_columns': round(registered_K / len(columns), 4),
        'note': ('computable from the registered column list alone, before opening test; '
                 'recommended as a gate in every future threshold calibration'),
    }


def current_content():
    test, cv, amendment1 = sealed_inputs()
    ticks = pd.read_csv(TICKS)
    if len(ticks) != 590:
        raise ValueError('expected exactly 590 frozen test ticks')
    registered_k = cv['content']['thresholds']['primary']['K']
    return {
        'diagnostic_id': 'DT4N-P6-ENVELOPE-POSTHOC-v1',
        'status': 'EXPLORATORY POST-FREEZE; not confirmatory performance',
        'uses_test_labels': True,
        'authorises_no_change_to': ['detector', 'threshold', 'hypothesis', 'column set'],
        'bound_to': {
            'envelope_test_content_sha256': test[HASH_FIELD],
            'envelope_cv_content_sha256': cv[HASH_FIELD],
            'amendment_1_content_sha256': amendment1['amendment_content_sha256'],
            'ticks_csv_sha256': sha256_file(TICKS),
        },
        'separability': separability(ticks),
        'oracle_threshold_sweep': oracle_sweep(ticks),
        'quantile_alternatives': quantile_alternatives(cv),
        'structural_reachability': structural_reachability(amendment1, registered_k),
    }


def main():
    if OUT.exists():
        print('[diag] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        HASH_FIELD: content_hash(content),
    }
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    sep = content['separability']
    best = content['oracle_threshold_sweep']['best_by_youden_j']
    reach = content['structural_reachability']
    print('[diag] AUC k=%.4f excess=%.4f' % (sep['auc_k'], sep['auc_excess']))
    print('[diag] oracle k > %d: recall=%.4f FPR=%.4f' %
          (best['threshold_k_gt'], best['recall'], best['fpr']))
    print('[diag] registered K=%d, structural bound=%d, reachable=%s' %
          (reach['registered_K'], reach['generous_upper_bound_single_link_fault'],
           reach['K_reachable_by_single_link_fault']))
    print('[diag] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
