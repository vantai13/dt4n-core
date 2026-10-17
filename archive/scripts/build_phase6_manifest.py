#!/usr/bin/env python3
"""Build the final SHA-addressed Phase 6 reproducibility manifest."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C
from ml.detectors import iforest as F

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6_manifest.json'
HASH_FIELD = 'manifest_content_sha256'

REGISTRATION_FILES = [
    'results/report/phase6_prereg.json',
    'results/report/phase6_prereg_amendment_1.json',
    'results/report/phase6_prereg_amendment_2.json',
    'results/report/phase6_hypothesis_ledger.json',
    'results/report/phase6_hypothesis_ledger_2.json',
    'results/report/phase6_hypothesis_ledger_3.json',
    'results/report/phase6_ablation_prereg.json',
]

FILES = REGISTRATION_FILES + [
    'results/report/ml_dataset_split_manifest.json',
    'results/report/ground_truth.json',
    'results/report/if_constant_blindness.json',
    'ml/metrics.py', 'ml/detectors/envelope.py', 'ml/detectors/iforest.py',
    'ml/dataset.py', 'ml/features.py',
    'scripts/run_phase6_envelope.py', 'scripts/run_phase6_iforest.py',
    'scripts/run_phase6_ablations.py',
    'results/report/phase6_envelope_cv.json',
    'results/report/phase6_envelope.json',
    'results/report/phase6_iforest_cv.json',
    'results/report/phase6_iforest.json',
    'results/report/phase6_comparison.json',
    'results/report/phase6_sensitivity.json',
    'results/report/phase6_noise_auc.json',
    'results/report/phase6_recovery.json',
    'results/report/phase6_envelope_loro_diag.json',
    'results/report/phase6_envelope_posthoc_diag.json',
    'results/report/phase6_iforest_posthoc_diag.json',
    'results/report/phase6_hybrid_diag.json',
    'results/report/phase6_ablations.json',
    'results/report/phase6_envelope_ticks.csv',
    'results/report/phase6_iforest_ticks.csv',
    'docs/phase-6/01-preregistration.md',
    'docs/phase-6/02-metrics.md',
    'docs/phase-6/03-envelope-baseline.md',
    'docs/phase-6/04-isolation-forest.md',
    'docs/phase-6/05-comparison.md',
    'docs/phase-6/06-error-analysis.md',
    'docs/phase-6/model-card.md',
]


def content_hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _git(*args):
    return subprocess.check_output(['git', *args], cwd=C.ROOT, text=True).strip()


def registration_history():
    out = []
    for relative in REGISTRATION_FILES:
        lines = _git('log', '--diff-filter=A', '--format=%H%x09%cI%x09%s',
                     '--', relative).splitlines()
        if not lines:
            raise RuntimeError('registration file has no add commit: ' + relative)
        commit, timestamp, subject = lines[-1].split('\t', 2)
        out.append({'path': relative, 'commit': commit,
                    'committed_at': timestamp, 'subject': subject})
    return out


def _internal_hash_status(relative):
    if not relative.endswith('.json'):
        return None
    document = json.loads((C.ROOT / relative).read_text())
    candidates = [key for key in document if key.endswith('content_sha256')]
    if 'content' not in document or len(candidates) != 1:
        return None
    key = candidates[0]
    return {'field': key, 'valid': content_hash(document['content']) == document[key]}


def reproduction_receipt():
    hybrid = json.loads((REPORT / 'phase6_hybrid_diag.json').read_text())['content']
    noise = json.loads((REPORT / 'phase6_noise_auc.json').read_text())['content']
    ablations = json.loads((REPORT / 'phase6_ablations.json').read_text())['content']
    return {
        'hybrid_five_seed_exact': hybrid['all_five_seeds_reproduced_exactly'],
        'noise_five_seed_exact': noise['summary']['all_five_noise_arms_reproduced_exactly'],
        'ablation_prereg_sha256': ablations['bound_to']['ablation_prereg_sha256'],
        'file_sha256': {relative: C.sha256_file(C.ROOT / relative)
                        for relative in FILES},
    }


def current_content():
    missing = [relative for relative in FILES if not (C.ROOT / relative).is_file()]
    if missing:
        raise RuntimeError('manifest files missing: %s' % missing)
    dirty = [relative for relative in FILES if _git(
        'status', '--porcelain', '--', relative)]
    if dirty:
        raise RuntimeError('manifest inputs not committed clean: %s' % dirty)
    latest_input_commit = _git('log', '-1', '--format=%H', '--', *FILES)
    internal = {relative: status for relative in FILES
                if (status := _internal_hash_status(relative)) is not None}
    invalid = [relative for relative, status in internal.items()
               if not status['valid']]
    if invalid:
        raise RuntimeError('invalid internal artifact hashes: %s' % invalid)
    phase6_prereg = json.loads((REPORT / 'phase6_prereg.json').read_text())
    uncertainty = phase6_prereg['content']['metrics']['uncertainty']
    receipt = reproduction_receipt()
    if not receipt['hybrid_five_seed_exact'] or not receipt['noise_five_seed_exact']:
        raise RuntimeError('bit-exact reproduction check failed')
    return {
        'manifest_id': 'DT4N-P6-MANIFEST-v1',
        'source_git_hash': latest_input_commit,
        'files': receipt['file_sha256'],
        'internal_json_hash_checks': internal,
        'registration_commit_order': registration_history(),
        'fixed_randomness': {
            'iforest_seeds': list(F.SEEDS),
            'noise_rng_base': F.NOISE_RNG_BASE,
            'bootstrap_rng_seed': uncertainty['rng_seed'],
            'bootstrap_replicates': uncertainty['n_boot'],
        },
        'iforest_hyperparameters': {
            'n_estimators': F.N_ESTIMATORS,
            'max_samples': list(F.MAX_SAMPLES),
            'primary_max_samples': F.PRIMARY_MAX_SAMPLES,
            'max_features': F.MAX_FEATURES, 'bootstrap': F.BOOTSTRAP,
            'contamination': F.CONTAMINATION,
            'quantiles': list(F.QUANTILES), 'primary_q': F.PRIMARY_Q,
        },
        'reproduction_receipt': receipt,
        'canonical_reproduction_sha256': content_hash(receipt),
        'notes': [
            'written_at_utc is excluded from canonical content hash',
            'raw data remains outside git; dataset manifest binds accepted raw hashes',
            'source_git_hash is the latest commit touching a manifest input',
        ],
    }


def main():
    if OUT.exists():
        print('[phase6-manifest] exists; refusing overwrite'); return 1
    content = current_content()
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, HASH_FIELD: content_hash(content)}
    with OUT.open('x') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    print('[phase6-manifest] source:', content['source_git_hash'])
    print('[phase6-manifest] files:', len(content['files']))
    print('[phase6-manifest] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
