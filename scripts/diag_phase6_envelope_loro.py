#!/usr/bin/env python3
"""Exploratory leave-one-run-out stability diagnostic for envelope thresholds."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ml import campaign as C
from ml.detectors import envelope as E
from scripts import run_phase6_envelope as R

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_envelope_loro_diag.json'
CV = REPORT / 'phase6_envelope_cv.json'
HASH_FIELD = 'content_sha256'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def current_content():
    cv = json.loads(CV.read_text())
    if content_hash(cv['content']) != cv['content_sha256']:
        raise RuntimeError('phase6_envelope_cv.json bi sua')
    base = R.load_train_base()
    families = R.families_from_registration()
    folds = []
    for fold, held_run in enumerate(sorted(base.run_id.unique())):
        fit_frame = base[base.run_id != held_run]
        val_frame = base[base.run_id == held_run]
        fit_aggregate, val_aggregate = E._prepare(fit_frame, val_frame)
        record = {
            'fold': fold, 'held_out_run': held_run,
            'held_out_config': str(val_frame.config_id.iloc[0]),
            'n_fit_rows': len(fit_frame), 'n_val_rows': len(val_frame),
            'families': {},
        }
        primary_bounds = E.fit_bounds(fit_aggregate, families['primary'])
        judgeable71 = E.score(val_aggregate, primary_bounds,
                              families['primary']).judgeable
        for name, columns in families.items():
            bounds = E.fit_bounds(fit_aggregate, columns)
            scores = E.score(val_aggregate, bounds, columns)
            if name in ('indicator', 'rate_shared'):
                scores['judgeable'] = judgeable71
            valid = scores[scores.judgeable]
            if valid.empty:
                raise RuntimeError('LORO fold has no judgeable row')
            record['families'][name] = {
                'k_max': int(valid.k.max()),
                'excess_max': float(valid.excess.max()),
                'share_k_gt_0': float((valid.k > 0).mean()),
                'n_judgeable': len(valid),
            }
        folds.append(record)
    primary_excess = [row['families']['primary']['excess_max'] for row in folds]
    vary = [row for row in folds if row['held_out_config'] == 'normal_varying|vary']
    vary_excess = [row['families']['primary']['excess_max'] for row in vary]
    registered = cv['content']['thresholds']['primary']
    return {
        'diagnostic_id': 'DT4N-P6-ENVELOPE-LORO-v1',
        'status': 'EXPLORATORY TRAIN-ONLY; REGISTERED THRESHOLDS UNCHANGED',
        'bound_to': {'envelope_cv_content_sha256': cv['content_sha256']},
        'folds': folds,
        'primary_summary': {
            'registered_leave_one_config_out_K': registered['K'],
            'registered_leave_one_config_out_E': registered['E'],
            'loro_k_max_range': [min(row['families']['primary']['k_max'] for row in folds),
                                 max(row['families']['primary']['k_max'] for row in folds)],
            'loro_excess_max_range': [min(primary_excess), max(primary_excess)],
            'vary_run_excess_max_values': vary_excess,
            'vary_run_excess_max_range': [min(vary_excess), max(vary_excess)],
            'n_vary_replicates': len(vary_excess),
        },
        'interpretation': (
            'LORO retains the other replicate of the same configuration in '
            'training, so it measures repeatability within profile rather than '
            'unseen-configuration generalisation. It does not replace LOCO.'),
    }


def main():
    if OUT.exists():
        print('[loro] exists; refusing overwrite'); return 1
    content = current_content()
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, HASH_FIELD: content_hash(content)}
    with OUT.open('x') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    print('[loro] vary E:', content['primary_summary']['vary_run_excess_max_values'])
    print('[loro] all E range:', content['primary_summary']['loro_excess_max_range'])
    print('[loro] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
