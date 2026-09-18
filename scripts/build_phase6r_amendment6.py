#!/usr/bin/env python3
"""Pre-register the R-O/R-S leakage firewall before any R-O replay code exists.

This builder reads only sealed receipts.  It never opens an R-set JSONL file.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6r_amendment_6.json'
ALLOWED_DIRTY = {
    'scripts/build_phase6r_amendment6.py',
    'results/report/phase6r_amendment_6.json',
}


def git_state() -> dict:
    output = subprocess.run(
        ['git', 'status', '--porcelain'], cwd=C.ROOT,
        capture_output=True, text=True, check=True).stdout
    dirty = sorted(line[3:] for line in output.splitlines() if line)
    illegal = [
        path for path in dirty
        if path not in ALLOWED_DIRTY
        and not path.startswith('logs/')
        and path != 'results/report/feature_audit.csv'
    ]
    if illegal:
        raise RuntimeError('commit truoc khi dang ky amendment 6: %s' % illegal)
    head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=C.ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    return {'head': head, 'dirty_files': dirty}


def build_content() -> dict:
    amendment_5 = json.loads(
        (REPORT / 'phase6r_amendment_5.json').read_text(encoding='utf-8'))
    matrix = json.loads(
        (REPORT / 'phase6r_rcampaign_matrix.json').read_text(encoding='utf-8'))
    manifest = json.loads(
        (REPORT / 'phase6r_rcampaign_manifest.json').read_text(encoding='utf-8'))
    if matrix.get('status') != 'collected':
        raise RuntimeError('R-campaign chua duoc danh dau collected')
    if manifest.get('complete') is not True or manifest.get('n_runs_ok') != 25:
        raise RuntimeError('receipt thu thap chua hoan tat')
    if manifest.get('labels_opened') is not False:
        raise RuntimeError('R-set da mo: qua muon de dang ky firewall')
    return {
        'amendment_id': 'DT4N-P6R-AMENDMENT-6',
        'amends': {
            'amendment_5_sha256': amendment_5['content_sha256'],
            'rcampaign_design_sha256': matrix['design_content_sha256'],
        },
        'git': git_state(),
        'pinned_receipt_sha256': {
            'results/report/phase6r_rcampaign_manifest.json':
                C.sha256_file(REPORT / 'phase6r_rcampaign_manifest.json'),
        },
        'timing_and_knowledge': {
            'r_campaign_collected': True,
            'labels_opened': False,
            'raw_snapshot_lines_read_for_this_decision': False,
            'detector_or_fsm_output_read_for_this_decision': False,
            'decision_source': 'structural leakage review of the sealed R-O/R-S plan',
        },
        'threat': {
            'name': 'R-O replay can leak R-S false alarms',
            'mechanism': ('R-O1/R-O2 are repeatable deterministic checks on raw R-S; '
                          'debug state sequences or alarm counts would reveal the same '
                          'false positives later used for S2/S3 acceptance.'),
            'protected_estimands': ['S2 false alarms per hour', 'S3 MTBFA'],
        },
        'decision': {
            'choice': 'A_structural_boolean_firewall',
            'R_S_used_for_S2_S3': [
                'RS-soak2M-s4001-r1',
                'RS-soak2M-s4002-r2',
                'RS-soak2M-s4003-r3',
            ],
            'R_O_replay_source': 'the same three R-S runs at only the sealed checkpoints',
            'restart_ticks': [600, 1800, 3000],
            'gap_ticks': [600, 1800, 3000],
            'gap_length_snapshots': 5,
        },
        'public_output_contract': {
            'R_O1_restart_S9_boolean_fields_only': [
                'first_after_restart_is_warming_up',
                'no_act_before_n_scored',
                'no_normal_before_scored',
                'passed',
            ],
            'R_O2_gap_S8_boolean_fields_only': [
                'first_after_gap_is_unknown_gap',
                'no_unjudgeable_tick_is_normal',
                'passed',
            ],
            'aggregation': ('logical AND across all registered checkpoints and R-S runs; '
                            'no per-run or per-checkpoint result is public'),
        },
        'structural_firewall': {
            'forbidden_outputs': [
                'raw or filtered state sequences',
                'alarm, suspect, or act counts',
                'entity names or per-entity scores',
                'tick indices, timestamps, residuals, and model scores',
                'snapshots or excerpts from snapshots',
            ],
            'forbidden_side_effects': [
                'per-tick stdout/logging',
                'debug dumps derived from R-S',
                'persisting intermediate scorer/FSM output',
            ],
            'debug_rule': ('debug only on synthetic fixtures that contain no R-S values; '
                           'a failure on R-S reveals only the aggregate boolean field name'),
            'implementation_rule': ('R-O harness must expose fixed-schema boolean-only APIs; '
                                    'tests must reject extra output keys and forbidden persistence'),
        },
        'repeat_policy': {
            'allowed': 'repeat the unchanged committed boolean checker on identical sealed inputs',
            'forbidden': ('change scorer/FSM parameters, thresholds, output schema, checkpoints, '
                          'or diagnostics after any R-O replay on R-S'),
            'failure_handling': ('reproduce and fix only with synthetic data; any required semantic '
                                 'change needs a new prospective dataset, not reinterpretation of R-S'),
        },
        'unchanged': [
            'FSM and scorer parameters',
            'S2/S3 definitions and all three hours of R-S exposure',
            'S8/S9 acceptance propositions',
            'R-campaign contract and collection receipt',
        ],
        'deviation_policy': 'bat bien sau commit; implement firewall before first R-O replay',
    }


def main() -> int:
    if OUT.exists():
        print('[6R-A6] da ton tai')
        return 1
    content = build_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        'content_sha256': C.sha256_bytes(
            C.canonical_json(content).encode('utf-8')),
    }
    C.atomic_json(OUT, document)
    print('[6R-A6] content_sha256 =', document['content_sha256'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
