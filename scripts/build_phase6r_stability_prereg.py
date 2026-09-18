#!/usr/bin/env python3
"""Đăng ký phạm vi 6R.6 trước mọi phép đo stability hoặc R-O replay."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6r_stability_prereg.json'
ALLOWED_DIRTY = {
    'scripts/build_phase6r_stability_prereg.py',
    'results/report/phase6r_stability_prereg.json',
}
FROZEN_CODE = ('ml/serve.py', 'ml/serve_fast.py', 'ml/fsm.py', 'ml/model.py')


def receipt(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding='utf-8'))


def content_sha(name: str) -> str:
    return receipt(name)['content_sha256']


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
        raise RuntimeError('commit source truoc khi dang ky 6R.6: %s' % illegal)
    head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=C.ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    return {'head': head, 'dirty_files': dirty}


def build_content() -> dict:
    slo = receipt('phase6r_slo.json')
    amendment_6 = receipt('phase6r_amendment_6.json')
    manifest_path = REPORT / 'phase6r_rcampaign_manifest.json'
    manifest = receipt(manifest_path.name)
    manifest_sha = C.sha256_file(manifest_path)
    pinned = amendment_6['content']['pinned_receipt_sha256'][
        'results/report/phase6r_rcampaign_manifest.json']
    if manifest_sha != pinned:
        raise RuntimeError('manifest da drift sau amendment 6')
    if manifest.get('complete') is not True or manifest.get('labels_opened') is not False:
        raise RuntimeError('R-campaign receipt khong o trang thai sealed-complete')

    targets = {row['id']: row['target'] for row in slo['content']['slo']}
    return {
        'prereg_id': 'DT4N-P6R-STABILITY',
        'lesson': '6R.6',
        'amends': {
            'slo_content_sha256': slo['content_sha256'],
            'amendment_6_content_sha256': amendment_6['content_sha256'],
            'rcampaign_manifest_file_sha256': manifest_sha,
        },
        'git': git_state(),
        'code_sha256': {
            path: C.sha256_file(C.ROOT / path) for path in FROZEN_CODE
        },
        'planned_implementation': {
            'not_yet_created_at_registration': [
                'ml/replay_guard.py',
                'ml/payload.py',
                'scripts/measure_phase6r_latency.py',
                'scripts/soak_phase6r_detector.py',
            ],
            'pinning_rule': ('hash new implementation in the final stability receipt; '
                             'frozen scorer/FSM/model code must keep the hashes above'),
        },
        'scope_correction': {
            'source_of_authority': 'phase6r_slo.json + amendment 4 + amendment 6',
            'reason': ('PHASE_6R.md predates the sealed SLO table and amendment 6. '
                       'Its old checklist would expose protected R-S estimands and '
                       'non-repeatable R-N acceptance outcomes in 6R.6.'),
            'closed_here': ['S4b', 'S5', 'S6', 'S8', 'S9', 'S11', 'S13'],
            'deferred_to_6R7': ['S1', 'S2', 'S3', 'S4', 'S7', 'S10'],
            'deferred_to_phase7': ['S12'],
            'moved_out_of_6R6_vs_plan': {
                'S3': 'MTBFA shares the protected S2 false-alarm estimate',
                'S10': 'R-N is non-repeatable acceptance data',
            },
        },
        'sealed_thresholds': {
            'S4_budget': targets['S4'],
            'S4b_debounce_ceiling': targets['S4b'],
            'S5_latency_p95': targets['S5'],
            'S6_rss_growth_30min': targets['S6'],
            'S8_missing_to_unknown': targets['S8'],
            'S9_restart_policy': targets['S9'],
            'S11_controller_act_entries': targets['S11'],
            'S13_payload_traceability': targets['S13'],
        },
        'data_sources': {
            'S4b': {'source': 'pure derivation from sealed S4/S5', 'reads_data': False},
            'S5': {
                'source': 'R-S',
                'emits': ['n', 'n_warmup_excluded', 'cold_start_ms', 'mean_ms',
                          'p50_ms', 'p95_ms', 'p99_ms', 'max_ms'],
                'forbidden': ('per-tick latency series, tick indices, and any '
                              'Reading or Transition field'),
            },
            'S6': {
                'source': 'R-S',
                'emits': ['resource-only RSS time series', 'delta_rss_kib',
                          'second_half_slope_kib_per_min', 'n_error'],
                'forbidden': 'Reading/Transition fields, labels, alarm counts',
            },
            'S8': {
                'source': 'R-O2 replay on R-S',
                'emits': 'aggregate boolean-only',
                'firewall': 'amendment 6 public_output_contract',
            },
            'S9': {
                'source': 'R-O1 replay on R-S',
                'emits': 'aggregate boolean-only',
                'firewall': 'amendment 6 public_output_contract',
            },
            'S11': {
                'source': ['RO-ctl_admin_down-s1-s2-s4301-r1',
                           'RO-ctl_admin_down-s1-s2-s4302-r2'],
                'emits': ['n_act_entries_in_window', 'n_suppressed_ticks',
                          'blast_radius', 'suppression_cause_seen', 'passed'],
                'note': 'R-O3 is separate from R-S and carries no S2/S3 estimate',
            },
            'S13': {'source': 'unit test only', 'reads_data': False},
        },
        'measurement_protocol': {
            'S5': {
                'clock': 'time.monotonic',
                'measures': 'scorer.observe() + DetectorFSM.step()',
                'implementations': ['OnlineScorer', 'FastOnlineScorer'],
                'warmup_excluded_per_run': 20,
                'cold_start_reported_separately': True,
                'source_runs': ['RS-soak2M-s4001-r1', 'RS-soak2M-s4002-r2',
                                'RS-soak2M-s4003-r3'],
            },
            'S6': {
                'measurement_of_record': '1800 ticks at 1 Hz (30 minutes)',
                'supplement': 'accelerated 10794 ticks',
                'rss_source': '/proc/self/statm resident pages',
                'sample_every_sec': 30,
            },
            'R_O': {
                'restart_ticks': [600, 1800, 3000],
                'gap_ticks': [600, 1800, 3000],
                'gap_length_snapshots': 5,
                'public_result_granularity': 'one aggregate boolean per sealed field',
            },
        },
        'predictions': {
            'P_S5': ('FastOnlineScorer p95 <= 50 ms; reference OnlineScorer may '
                     'exceed the budget because it builds pandas objects per tick'),
            'P_S6': '30-minute RSS delta <= 1 MiB and second-half curve is flat',
            'P_S8': 'PASS: every registered 5-snapshot gap maps to unknown(cause=gap)',
            'P_S9': ('PASS: first snapshot is warming_up; no act before n_act scored; '
                     'no normal before a scored result'),
            'P_S11': ('PASS: zero act entries in the intervention window, with '
                      'nonzero suppressed ticks required for mechanism evidence'),
        },
        'timing_and_knowledge': {
            'measured_any_6R6_stability_slo_yet': False,
            'prior_6R5B_tick_metrology_exists': True,
            'labels_opened': False,
            'r_set_acceptance_opened': False,
            'R_O_replay_run': False,
        },
        'deviation_policy': ('immutable after commit; sealed SLO thresholds may not '
                             'be loosened after observing stability results'),
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def main() -> int:
    if OUT.exists():
        raise SystemExit('da dang ky roi; khong sinh lai (xem deviation_policy)')
    content = build_content()
    document = {
        'content': content,
        'content_sha256': C.sha256_bytes(
            C.canonical_json(content).encode('utf-8')),
    }
    C.atomic_json(OUT, document)
    print('[6R.6 prereg] content_sha256 =', document['content_sha256'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
