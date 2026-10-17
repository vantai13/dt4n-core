#!/usr/bin/env python3
"""Lesson 6.5: five-seed contribution, Jaccard, and hybrid-delay tables.

Models are deterministically reconstructed only to recover the four IF seeds
not stored in the tick CSV. Frozen thresholds and signed TP/FP must reproduce
exactly. No detector, threshold, or primary/secondary label is changed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from ml import campaign as C
from ml import metrics as M
from ml.dataset import load_split
from ml.detectors import iforest as F
from scripts import diag_phase6_hybrid as H
from scripts import run_phase6_iforest as R

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_comparison.json'
ENV = REPORT / 'phase6_envelope.json'
IFOREST = REPORT / 'phase6_iforest.json'
ENV_TICKS = REPORT / 'phase6_envelope_ticks.csv'
IF_TICKS = REPORT / 'phase6_iforest_ticks.csv'
LEDGER_3 = REPORT / 'phase6_hypothesis_ledger_3.json'
HYBRID = REPORT / 'phase6_hybrid_diag.json'
CV = REPORT / 'phase6_iforest_cv.json'
HASH_FIELD = 'content_sha256'
SUPERSEDES_CONTENT_SHA256 = '46daa750adf5405c781e37d1f1c684c9e48582c3842843593e77d4c7badd3a96'


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


def _reading(frame, alarm_a, alarm_b, common):
    y = frame.y.to_numpy(dtype=bool)
    all_rows = {
        'positive_contribution': contribution_table(y, alarm_a, alarm_b),
        'by_fault': _by_fault(frame, alarm_a, alarm_b),
        'negative_alarm_overlap': _false_positive_overlap(y, alarm_a, alarm_b),
        'n_rows': len(frame),
    }
    sub = frame.loc[common].reset_index(drop=True)
    a_common = alarm_a[common]; b_common = alarm_b[common]
    common_rows = {
        'positive_contribution': contribution_table(
            sub.y.to_numpy(dtype=bool), a_common, b_common),
        'by_fault': _by_fault(sub, a_common, b_common),
        'negative_alarm_overlap': _false_positive_overlap(
            sub.y.to_numpy(dtype=bool), a_common, b_common),
        'n_rows': len(sub),
    }
    return {'primary_all_rows': all_rows,
            'secondary_common_judgeable_rows': common_rows}


def _hybrid_delay(split, keys, faults, alarm, judgeable):
    run_id = [key['run_id'] for key in keys]
    eval_frame = M.build_frame(
        run_id=run_id, tick=[int(key['tick']) for key in keys],
        group=[rid[0] for rid in run_id], fault=[faults.get(rid) for rid in run_id],
        y=split.y_test.to_numpy(), eval_mask=split.eval_primary.to_numpy(),
        judgeable=judgeable, alarm=alarm, mask_name='eval_primary')
    delay = M.detection_delay(eval_frame)
    by_fault = {}
    for fault in sorted(set(value for value in faults.values() if value)):
        values = [value for rid, value in delay['per_run'].items()
                  if faults.get(rid) == fault]
        detected = [value for value in values if value is not None]
        by_fault[fault] = {
            'per_run': values, 'n_incidents': len(values),
            'n_censored': len(values) - len(detected),
            'median_delay_detected': (float(pd.Series(detected).median())
                                      if detected else None),
        }
    return {'overall': delay, 'by_fault': by_fault,
            'mask': 'eval_primary only; delay is preregistered on this mask'}


def current_content():
    env_doc = _verify(ENV)
    if_doc = _verify(IFOREST)
    ledger = _verify(LEDGER_3, 'ledger_content_sha256')
    hybrid = _verify(HYBRID)
    cv = _verify(CV)
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
    split = load_split()
    columns = R.frozen_columns_from_manifest()
    if_flags, if_judgeable, reconstruction = H.reconstruct_and_verify(
        split, columns, cv, if_doc)
    env_judgeable = env.judgeable71.to_numpy(dtype=bool)
    common = env_judgeable & if_judgeable
    keys_from_split = pd.DataFrame(split.meta['test_row_keys'])
    if not env[keys].equals(keys_from_split):
        raise RuntimeError('tick artifacts lech split')
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {row['run_id']: row.get('fault') for row in contract['runs']}

    per_seed = {}
    for seed in F.SEEDS:
        if_alarm = if_flags[str(seed)]
        rows = {'reconstruction_check': reconstruction[str(seed)]}
        for label, column in (
                ('secondary_excess_vs_iforest', 'alarm_secondary_excess'),
                ('literal_primary_k_vs_iforest', 'alarm_primary_k')):
            env_alarm = env[column].to_numpy(dtype=bool)
            reading = _reading(frame, env_alarm, if_alarm, common)
            hybrid_alarm = env_alarm | if_alarm
            hybrid_judgeable = env_judgeable | if_judgeable
            reading['hybrid_or_delay'] = _hybrid_delay(
                split, split.meta['test_row_keys'], faults,
                hybrid_alarm, hybrid_judgeable)
            rows[label] = reading
        per_seed[str(seed)] = rows

    # Reproduce the already signed five-seed excess hybrid counts.
    for seed in F.SEEDS:
        signed = hybrid['content']['per_seed'][str(seed)]
        got = per_seed[str(seed)]['secondary_excess_vs_iforest'][
            'primary_all_rows']
        if got['positive_contribution']['b_only'] != signed[
                'iforest_unique_true_positives'] or \
                got['negative_alarm_overlap']['b_only'] != signed[
                'added_false_positives']:
            raise RuntimeError('comparison seed %d lech hybrid artifact' % seed)

    def sequence(label, section, field):
        return [per_seed[str(seed)][label][section][
            'positive_contribution'][field] for seed in F.SEEDS]

    summary = {}
    for label in ('secondary_excess_vs_iforest',
                  'literal_primary_k_vs_iforest'):
        summary[label] = {}
        for section in ('primary_all_rows',
                        'secondary_common_judgeable_rows'):
            summary[label][section] = {
                field + '_per_seed': sequence(label, section, field)
                for field in ('both_detect', 'a_only', 'b_only', 'both_miss')}

    return {
        'diagnostic_id': 'DT4N-P6-COMPARISON-v2',
        'supersedes_content_sha256': SUPERSEDES_CONTENT_SHA256,
        'status': 'POST-FREEZE REPRODUCTION; NO THRESHOLD CHANGE',
        'uses_test_labels': True,
        'follows_ledger_3_sha256': ledger['ledger_content_sha256'],
        'bound_to': {
            'envelope_content_sha256': env_doc['content_sha256'],
            'iforest_content_sha256': if_doc['content_sha256'],
            'hybrid_content_sha256': hybrid['content_sha256'],
            'iforest_cv_content_sha256': cv['content_sha256'],
            'envelope_ticks_sha256': C.sha256_file(ENV_TICKS),
            'iforest_ticks_sha256': C.sha256_file(IF_TICKS),
        },
        'comparison_sets': {
            'primary_all_rows': {'n_rows': len(frame),
                                 'n_positive': int(y.sum()),
                                 'n_negative': int((~y).sum())},
            'secondary_common_judgeable_rows': {
                'n_rows': int(common.sum()),
                'n_positive': int((y & common).sum()),
                'n_negative': int((~y & common).sum())},
        },
        'hybrid_under_specification': {
            'issue': ('preregistered hybrid_or does not identify whether the '
                      'envelope member is primary_k or secondary_excess'),
            'reporting_rule': 'report both literal and secondary-excess readings',
            'primary_secondary_labels_unchanged': True,
        },
        'per_seed': per_seed,
        'across_seeds': summary,
        'delay_sensitivity_note': (
            'No eval_sensitivity delay is computed: delay was preregistered '
            'only on eval_primary, and dropping onset ticks changes the time origin.'),
        'interpretation': {
            'jaccard_zero_is_not_complementarity': (
                'IF has zero unique positive ticks; complementarity requires '
                'useful unique contribution from both members'),
            'disjoint_feature_sets_are_not_sufficient': True,
            'excess_if_unique_tp_per_seed': summary[
                'secondary_excess_vs_iforest']['primary_all_rows'][
                    'b_only_per_seed'],
            'literal_primary_if_unique_tp_per_seed': summary[
                'literal_primary_k_vs_iforest']['primary_all_rows'][
                    'b_only_per_seed'],
            'coverage_advantage': (
                'common-positive denominator is 152 rather than 160 because '
                'IF has eight unknown positive ticks; envelope catches three '
                'positive ticks outside that common set'),
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
    row = content['per_seed']['0']['secondary_excess_vs_iforest'][
        'primary_all_rows']['positive_contribution']
    print('[comparison] both=%d env_only=%d if_only=%d miss=%d J=%s' %
          (row['both_detect'], row['a_only'], row['b_only'], row['both_miss'],
           row['jaccard']))
    print('[comparison] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
