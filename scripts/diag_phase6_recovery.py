#!/usr/bin/env python3
"""Measure post-revert excess-alarm spans for Phase 8 cooldown design."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from ml import campaign as C

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_recovery.json'
TICKS = REPORT / 'phase6_envelope_ticks.csv'
ENVELOPE = REPORT / 'phase6_envelope.json'
REVERT_TICK = 40
HASH_FIELD = 'content_sha256'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def current_content():
    envelope = json.loads(ENVELOPE.read_text())
    if content_hash(envelope['content']) != envelope['content_sha256']:
        raise RuntimeError('phase6_envelope.json bi sua')
    if C.sha256_file(TICKS) != envelope['content']['ticks_csv_sha256']:
        raise RuntimeError('phase6_envelope_ticks.csv bi sua')
    ticks = pd.read_csv(TICKS)
    fault_rows = ticks[ticks.run_id.str.startswith('F-')]
    per_run = {}
    for run_id, rows in fault_rows.groupby('run_id', sort=True):
        fired = rows[(rows.tick > REVERT_TICK) & rows.y.eq(0) &
                     rows.alarm_secondary_excess.astype(bool)]
        alarm_ticks = [int(value) for value in fired.tick.tolist()]
        per_run[run_id] = {
            'fault': run_id.split('-')[1], 'fp_ticks_after_revert': alarm_ticks,
            'last_alarm_tick': alarm_ticks[-1] if alarm_ticks else None,
            'observed_recovery_span_ticks': (
                alarm_ticks[-1] - REVERT_TICK if alarm_ticks else 0),
            'n_post_revert_alarms': len(alarm_ticks),
        }
    by_fault = {}
    for fault in sorted({row['fault'] for row in per_run.values()}):
        rows = [row for row in per_run.values() if row['fault'] == fault]
        spans = [row['observed_recovery_span_ticks'] for row in rows]
        by_fault[fault] = {
            'per_run_span_ticks': spans, 'max_span_ticks': max(spans),
            'n_post_revert_alarms': sum(row['n_post_revert_alarms'] for row in rows),
        }
    maximum = max(row['observed_recovery_span_ticks'] for row in per_run.values())
    return {
        'diagnostic_id': 'DT4N-P6-RECOVERY-v1',
        'status': 'EXPLORATORY POST-FREEZE SYSTEM MEASUREMENT',
        'bound_to': {'envelope_content_sha256': envelope['content_sha256'],
                     'ticks_sha256': C.sha256_file(TICKS)},
        'revert_tick': REVERT_TICK, 'per_run': per_run, 'by_fault': by_fault,
        'maximum_observed_recovery_span_ticks': maximum,
        'recommended_phase8_cooldown_ticks': maximum + 1,
        'interpretation': (
            'post-revert excess alarms measure residual state across 71 channels; '
            'they are distinct from ground-truth recovery on one strongest witness'),
        'zero_span_note': (
            'zero means no post-revert excess alarm was observed; it is an upper '
            'resolution statement, not proof of instantaneous physical recovery'),
    }


def main():
    if OUT.exists():
        print('[recovery] exists; refusing overwrite'); return 1
    content = current_content()
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, HASH_FIELD: content_hash(content)}
    with OUT.open('x') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    print('[recovery] by fault:', {k: v['max_span_ticks'] for k, v in content['by_fault'].items()})
    print('[recovery] cooldown:', content['recommended_phase8_cooldown_ticks'])
    print('[recovery] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
