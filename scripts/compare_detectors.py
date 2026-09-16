#!/usr/bin/env python3
"""Lesson 6.5: frozen tick-level detector contribution and Jaccard tables.

This script reads only the two signed tick artifacts. It does not fit a model,
change a threshold, or reinterpret the registered primary detector.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from ml import campaign as C

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_comparison.json'
ENV = REPORT / 'phase6_envelope.json'
IFOREST = REPORT / 'phase6_iforest.json'
ENV_TICKS = REPORT / 'phase6_envelope_ticks.csv'
IF_TICKS = REPORT / 'phase6_iforest_ticks.csv'
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


def contribution_table(y, alarm_a, alarm_b):
    """Return the four positive-tick cells and Jaccard of detected sets."""
    y = pd.Series(y, dtype=bool).to_numpy()
    a = pd.Series(alarm_a, dtype=bool).to_numpy()
    b = pd.Series(alarm_b, dtype=bool).to_numpy()
    if not (len(y) == len(a) == len(b)):
        raise ValueError('contribution arrays must have equal length')
    pos = y
    both = int((pos & a & b).sum())
    only_a = int((pos & a & ~b).sum())
    only_b = int((pos & ~a & b).sum())
    both_miss = int((pos & ~a & ~b).sum())
    union = both + only_a + only_b
    return {
        'n_positive_ticks': int(pos.sum()),
        'both_detect': both, 'a_only': only_a, 'b_only': only_b,
        'both_miss': both_miss,
        'jaccard': None if union == 0 else both / union,
        'jaccard_note': ('undefined: detected-set union is empty'
                         if union == 0 else 'intersection / union'),
    }


def _fault_of(run_id):
    return run_id.split('-')[1] if run_id.startswith('F-') else None


def _by_fault(frame, alarm_a, alarm_b):
    rows = []
    for fault, group in frame[frame.y.astype(bool)].groupby('fault', sort=True):
        indices = group.index.to_numpy()
        row = contribution_table(group.y, alarm_a[indices], alarm_b[indices])
        rows.append((fault, row))
    return dict(rows)


def _false_positive_overlap(y, alarm_a, alarm_b):
    y = pd.Series(y, dtype=bool).to_numpy()
    a = pd.Series(alarm_a, dtype=bool).to_numpy()
    b = pd.Series(alarm_b, dtype=bool).to_numpy()
    neg = ~y
    return {
        'both_alarm': int((neg & a & b).sum()),
        'a_only': int((neg & a & ~b).sum()),
        'b_only': int((neg & ~a & b).sum()),
        'neither': int((neg & ~a & ~b).sum()),
    }


def current_content():
    env_doc = _verify(ENV)
    if_doc = _verify(IFOREST)
    ledger = _verify(LEDGER_3, 'ledger_content_sha256')
    hybrid = _verify(HYBRID)
    if C.sha256_file(ENV_TICKS) != env_doc['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_envelope_ticks.csv bi sua')
    if C.sha256_file(IF_TICKS) != if_doc['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_iforest_ticks.csv bi sua')

    env = pd.read_csv(ENV_TICKS)
    ifr = pd.read_csv(IF_TICKS)
    keys = ['run_id', 'tick']
    if not env[keys].equals(ifr[keys]):
        raise RuntimeError('hai tick artifact khong cung khoa/thu tu')
    if not env.y.equals(ifr.y):
        raise RuntimeError('hai tick artifact khong cung nhan')
    frame = env[keys + ['y']].copy()
    frame['fault'] = frame.run_id.map(_fault_of)
    y = frame.y.to_numpy(dtype=bool)
    if_alarm = ifr.alarm_q01.to_numpy(dtype=bool)

    readings = {}
    for name, column in (
            ('registered_secondary_excess_vs_iforest_seed0',
             'alarm_secondary_excess'),
            ('literal_primary_k_vs_iforest_seed0', 'alarm_primary_k')):
        env_alarm = env[column].to_numpy(dtype=bool)
        readings[name] = {
            'members': {'A': column.removeprefix('alarm_'),
                        'B': 'iforest_q01_seed0'},
            'positive_contribution': contribution_table(y, env_alarm, if_alarm),
            'by_fault': _by_fault(frame, env_alarm, if_alarm),
            'negative_alarm_overlap': _false_positive_overlap(
                y, env_alarm, if_alarm),
        }

    excess = readings['registered_secondary_excess_vs_iforest_seed0']
    primary = readings['literal_primary_k_vs_iforest_seed0']
    hybrid_seed0 = hybrid['content']['per_seed']['0']
    if excess['positive_contribution']['b_only'] != \
            hybrid_seed0['iforest_unique_true_positives']:
        raise RuntimeError('comparison lech hybrid diagnostic da ky')
    if excess['negative_alarm_overlap']['b_only'] != \
            hybrid_seed0['added_false_positives']:
        raise RuntimeError('FP contribution lech hybrid diagnostic da ky')

    return {
        'diagnostic_id': 'DT4N-P6-COMPARISON-v1',
        'status': 'POST-FREEZE; NO REFIT; NO THRESHOLD CHANGE',
        'uses_test_labels': True,
        'follows_ledger_3_sha256': ledger['ledger_content_sha256'],
        'bound_to': {
            'envelope_content_sha256': env_doc['content_sha256'],
            'iforest_content_sha256': if_doc['content_sha256'],
            'hybrid_content_sha256': hybrid['content_sha256'],
            'envelope_ticks_sha256': C.sha256_file(ENV_TICKS),
            'iforest_ticks_sha256': C.sha256_file(IF_TICKS),
        },
        'n_rows': len(frame),
        'hybrid_under_specification': {
            'issue': ('preregistered hybrid_or does not identify whether the '
                      'envelope member is primary_k or secondary_excess'),
            'reporting_rule': 'report both literal and secondary-excess readings',
            'primary_secondary_labels_unchanged': True,
        },
        'readings': readings,
        'interpretation': {
            'jaccard_zero_is_not_complementarity': (
                'IF has zero unique positive ticks; complementarity requires '
                'useful unique contribution from both members'),
            'disjoint_feature_sets_are_not_sufficient': True,
            'excess_if_unique_tp_seed0':
                excess['positive_contribution']['b_only'],
            'excess_if_added_fp_seed0':
                excess['negative_alarm_overlap']['b_only'],
            'literal_primary_if_union_positive_ticks_seed0': (
                primary['positive_contribution']['both_detect'] +
                primary['positive_contribution']['a_only'] +
                primary['positive_contribution']['b_only']),
        },
    }


def main():
    if OUT.exists():
        print('[comparison] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content, HASH_FIELD: content_hash(content),
    }
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    row = content['readings'][
        'registered_secondary_excess_vs_iforest_seed0']['positive_contribution']
    print('[comparison] both=%d env_only=%d if_only=%d miss=%d J=%s' %
          (row['both_detect'], row['a_only'], row['b_only'], row['both_miss'],
           row['jaccard']))
    print('[comparison] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
