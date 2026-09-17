#!/usr/bin/env python3
"""R-campaign runtime: InterventionLog, luật chạy lại và manifest."""
from __future__ import annotations

import json

from ml import campaign as C
from ml.blast_radius import Routing, radius

INSTRUMENT_GATES = {
    'tick_count_ok', 'event_ticks_ok', 'events_complete',
    'no_unexpected_down', 'runtime_log_ok', 'collection_exception',
    'environment_exception',
}
MAX_ATTEMPTS = 2


def targets_for(record: dict) -> dict:
    """Cùng luật với revert_targets của amendment 2."""
    parameters, fault = record['fault_parameters'], record['fault']
    if fault in ('admin_down', 'degrade'):
        return {'links': [parameters['link_key']], 'flows': []}
    if fault == 'flood':
        return {'links': [], 'flows': [[parameters['src'], parameters['dst']]]}
    if fault == 'shift':
        return {'links': [parameters['link_key']],
                'flows': [[parameters['flood_src'], parameters['flood_dst']]]}
    raise ValueError('fault chua ho tro: %s' % fault)


class InterventionRecorder:
    def __init__(self, record: dict,
                 routing_path=C.ROOT / 'ditto/routing_table.json'):
        self.record = record
        self.policy = record.get('intervention') or {
            'actor': None, 'log_inject': False, 'log_revert': False}
        if self.policy['log_inject'] and self.policy['actor'] != 'controller':
            raise ValueError('inject chi duoc ghi log khi actor=controller')
        self.routing = Routing.load(routing_path) if record.get('fault') else None
        self.items: list[dict] = []

    def should_log(self, kind: str) -> bool:
        return (bool(self.record.get('fault')) and
                bool(self.policy.get('log_' + kind)))

    def record_before_apply(self, kind: str, t_wall: float,
                            tick: int) -> dict | None:
        if not self.should_log(kind):
            return None
        targets = targets_for(self.record)
        item = {
            'id': '%s:%s' % (self.record['run_id'], kind),
            't_start': float(t_wall),
            'tick': int(tick),
            'actor': self.policy['actor'],
            'action': '%s:%s' % (kind, self.record['fault']),
            'targets': targets,
            'blast_radius': sorted(radius(self.routing, targets)),
            'routing_sha256': self.routing.sha256,
        }
        if any(existing['id'] == item['id'] for existing in self.items):
            raise ValueError('intervention id trung (append-only): %s' % item['id'])
        self.items.append(item)
        return item


def attempts_so_far(paths: dict) -> int:
    """Đếm lần thử thất bại đang nằm trong quarantine và các bản archive."""
    qdir = paths['quarantine_meta'].parent
    if not qdir.exists():
        return 0
    stem = paths['quarantine_meta'].name[:-len('.meta.json')]
    archived = list(qdir.glob(stem + '.meta.attempt-*.json'))
    return len(archived) + int(paths['quarantine_meta'].exists())


def rerun_allowed(paths: dict) -> tuple[bool, str]:
    """Chỉ chạy lại lỗi dụng cụ, tối đa MAX_ATTEMPTS lần cho mỗi ô."""
    attempts = attempts_so_far(paths)
    if attempts >= MAX_ATTEMPTS:
        return False, 'da thu %d lan (toi da %d)' % (attempts, MAX_ATTEMPTS)
    if paths['quarantine_meta'].exists():
        sidecar = json.loads(paths['quarantine_meta'].read_text(encoding='utf-8'))
        failed = set(sidecar.get('checks', {}).get('failed_gates', []))
        outcome = failed - INSTRUMENT_GATES
        if outcome:
            return False, 'lan truoc truot gate KET CUC %s: cam chay lai' % sorted(outcome)
    return True, 'cho phep (lan thu %d)' % (attempts + 1)


def build_manifest(contract, outcomes, collection_provenance, integrity,
                   started_utc, finished_utc) -> dict:
    expected = {record['run_id'] for record in contract['runs']}
    if not set(outcomes) <= expected:
        raise ValueError('manifest co run ngoai hop dong')
    ok = sorted(run_id for run_id, outcome in outcomes.items()
                if outcome.get('status') == 'ok' and
                outcome.get('checks', {}).get('passed') is True)
    by_group = {}
    for record in contract['runs']:
        group = by_group.setdefault(record['group'], {'expected': 0, 'ok': 0})
        group['expected'] += 1
        group['ok'] += record['run_id'] in ok
    return {
        'campaign': contract['campaign_id'],
        'design_content_sha256': contract['design_content_sha256'],
        'contract_integrity': integrity,
        'collection_provenance': collection_provenance,
        'started_utc': started_utc,
        'finished_utc': finished_utc,
        'n_runs_expected': len(expected),
        'n_runs_ok': len(ok),
        'n_runs_failed': len(outcomes) - len(ok),
        'runs_not_attempted': sorted(expected - set(outcomes)),
        'by_group': by_group,
        'complete': set(ok) == expected and integrity.get('match') is True,
        'runs': outcomes,
        'labels_opened': False,
        'note': 'R-set: khong tinh recall/FPR o day; nghiem thu mo o 6R.7',
    }
