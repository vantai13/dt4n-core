#!/usr/bin/env python3
"""Freeze Phase 6.6 ablation predictions before any A1-A3 execution."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C
from ml.detectors import iforest as F

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_ablation_prereg.json'
SENSITIVITY = REPORT / 'phase6_sensitivity.json'
NOISE_AUC = REPORT / 'phase6_noise_auc.json'
COMPARISON = REPORT / 'phase6_comparison.json'
HASH_FIELD = 'prereg_content_sha256'


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _verified(path):
    document = json.loads(path.read_text())
    if content_hash(document['content']) != document['content_sha256']:
        raise RuntimeError('%s bi sua' % path.name)
    return document


def current_content():
    sensitivity = _verified(SENSITIVITY)
    noise = _verified(NOISE_AUC)
    comparison = _verified(COMPARISON)
    return {
        'prereg_id': 'DT4N-P6-ABLATION-PREREG-v1',
        'written_before_running_any_A1_A3_ablation': True,
        'knowledge_state': {
            'original_phase6_test_results_seen': True,
            'A4_mask_sensitivity_seen': True,
            'A1_A2_A3_results_seen': False,
            'purpose': 'exploratory mechanism tests; no reopening H1-H5',
        },
        'bound_to': {
            'sensitivity_content_sha256': sensitivity['content_sha256'],
            'noise_auc_content_sha256': noise['content_sha256'],
            'comparison_content_sha256': comparison['content_sha256'],
        },
        'fixed_protocol': {
            'seeds': list(F.SEEDS), 'n_estimators': F.N_ESTIMATORS,
            'max_samples': F.PRIMARY_MAX_SAMPLES,
            'max_features': F.MAX_FEATURES, 'bootstrap': F.BOOTSTRAP,
            'contamination': F.CONTAMINATION, 'q': F.PRIMARY_Q,
            'threshold': 'strictly below train q=0.01, fitted per seed/ablation',
            'mask': 'eval_primary; unknown -> no alarm and positive unknown -> FN',
            'metrics': 'same ml.metrics API; recall and FPR always together',
            'comparison': 'paired seeds 0..4; no seed substitution',
        },
        'note_on_plan_divergence': (
            "The original PHASE_6 plan expected recall to decrease after "
            "dropping d1. That prediction predates the measured tail inversion. "
            "A1 records the opposite mechanism-derived prediction without "
            "editing or hiding the original expectation."),
        'ablations': {
            'A1_drop_delta': {
                'definition': (
                    'IF on the 36 non-d1 frozen features, including agg.*; '
                    'drop all 36 d1.* features'),
                'mechanism': (
                    'valid N-vary transitions own the registered lower tail; '
                    'removing d1 should move q=0.01 upward and expose stable faults'),
                'prediction_recall_q01': 'mean five-seed recall increases from 0.13% to >30%',
                'prediction_unknown': (
                    'unknown_negative 18 -> 8; unknown_positive 8 -> 4; '
                    'recall ceiling 0.950 -> 0.975'),
                'prediction_fpr_control': 'decreases from registered IF mean 3.90%',
                'refutation': 'mean recall <=5% OR unknown_negative !=8',
            },
            'A2_rolling_window3': {
                'definition': (
                    'IF uses frozen raw+d1 plus causal ma3 features from '
                    'load_split(use_rolling=True, window=3). Envelope replaces '
                    'each of its 71 channels by its causal trailing-3 mean, '
                    'refitting fold preprocessing, bounds, K and E on train only.'),
                'mechanism': (
                    'smoothing should reduce normal transient peaks but also '
                    'smooth fault onset and reduce coverage'),
                'prediction': (
                    'IF recall increases; rolling-envelope FPR decreases; '
                    'median detected delay of both increases by >=1 tick; '
                    'coverage decreases by about 6%'),
                'refutation': 'delay does not increase for either detector',
            },
            'A3_raw_no_agg': {
                'definition': (
                    'IF on 34 frozen non-d1, non-agg link/host features; '
                    'drop d1.* and the two agg.rate_absz_* features'),
                'why_separate_from_A1': (
                    'A1 retains the only IF aggregate channels normalized by '
                    'train link statistics; A3 isolates their contribution'),
                'prediction': 'mean recall A3 is lower than A1',
                'refutation': 'mean recall A3 >= mean recall A1',
            },
            'A4_mask_sensitivity': {
                'status': 'completed before this prereg',
                'artifact_sha256': sensitivity['content_sha256'],
                'result': (
                    'envelope recall changes +1.9 to +2.6 points; excess FPR '
                    '5.35% -> 3.38%; dual FPR 0.47% -> 0%; control FPR remains 0%'),
                'conclusion': (
                    'recall conclusion is robust; all-negative FPR depends on '
                    'transition convention; control FPR is invariant'),
            },
        },
        'deviation_policy': (
            'do not edit this file; record implementation deviations and all '
            'refutations in phase6_ablations.json'),
    }


def main():
    if OUT.exists():
        print('[ablation-prereg] exists; refusing overwrite'); return 1
    content = current_content()
    git_hash = subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=C.ROOT, text=True).strip()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'written_from_git': git_hash, 'content': content,
        HASH_FIELD: content_hash(content),
    }
    with OUT.open('x') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    print('[ablation-prereg] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
