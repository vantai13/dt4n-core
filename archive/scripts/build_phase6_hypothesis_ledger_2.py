#!/usr/bin/env python3
"""Append-only decision ledger for train-CV IF evidence before test scoring."""
import json
from datetime import datetime, timezone

from ml.campaign import ROOT, canonical_json, sha256_bytes
from ml.detectors import iforest as F

REPORT = ROOT / 'results/report'
OUT = REPORT / 'phase6_hypothesis_ledger_2.json'
LEDGER_1 = REPORT / 'phase6_hypothesis_ledger.json'
CV = REPORT / 'phase6_iforest_cv.json'
PREREG = REPORT / 'phase6_prereg.json'
HASH_FIELD = 'ledger_content_sha256'
VARY_FOLD = 'normal_varying|vary'


def content_hash(value):
    return sha256_bytes(canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sealed_sources():
    one, cv, prereg = _read(LEDGER_1), _read(CV), _read(PREREG)
    if content_hash(one['content']) != one[HASH_FIELD]:
        raise ValueError('so quyet dinh 1 bi sua')
    if content_hash(cv['content']) != cv['content_sha256']:
        raise ValueError('CV IF bi sua')
    if content_hash(prereg['content']) != prereg['prereg_content_sha256']:
        raise ValueError('ban dang ky bi sua')
    if cv['content']['ledger_content_sha256'] != one[HASH_FIELD]:
        raise ValueError('CV khong tro ve so quyet dinh 1 dang co')
    if not cv['content']['is_full_registered_grid']:
        raise ValueError('CV chay luoi rut gon, khong dung de phan quyet')
    return {'ledger_1': one, 'cv': cv, 'prereg': prereg}


def mean_alarm_rate_by_fold(cv_content, q):
    out = {}
    for fold in cv_content['folds']:
        rates = [row['alarm_rate_by_q'][str(q)]['alarm_rate']
                 for row in fold['per_seed'].values()]
        out[fold['held_out_config']] = {
            'mean': sum(rates) / len(rates), 'min': min(rates),
            'max': max(rates), 'n_seeds': len(rates)}
    return out


def decide_h4_iforest_clause(src):
    rates = mean_alarm_rate_by_fold(src['cv']['content'], F.PRIMARY_Q)
    vary = rates[VARY_FOLD]
    others = {key: value for key, value in rates.items() if key != VARY_FOLD}
    highest = max(others, key=lambda key: others[key]['mean'])
    holds = vary['mean'] > others[highest]['mean']
    return ('supported' if holds else 'refuted'), {
        'metric': 'mean over 5 seeds of held-out alarm rate at q=0.01',
        'by_fold': rates, 'vary_fold_mean': vary['mean'],
        'vary_fold_seed_range': [vary['min'], vary['max']],
        'highest_other_fold': highest,
        'highest_other_mean': others[highest]['mean'], 'clause_holds': holds,
        'holds_for_every_seed': vary['min'] > others[highest]['max']}


def current_content():
    src = sealed_sources(); cv = src['cv']['content']
    one = src['ledger_1']['content']['hypotheses']['H4']
    status, evidence = decide_h4_iforest_clause(src)
    ownership = cv['tail_ownership']['0']
    dynamics = cv['dynamics_profile']
    vary_mean = evidence['vary_fold_mean'] * 100
    lo, hi = [x * 100 for x in evidence['vary_fold_seed_range']]
    return {
        'ledger_id': 'DT4N-P6-HYPOTHESIS-LEDGER-v2',
        'append_only_after': src['ledger_1'][HASH_FIELD],
        'bound_to': {'iforest_cv_content_sha256': src['cv']['content_sha256'],
                     'prereg_content_sha256': src['prereg']['prereg_content_sha256']},
        'timing_and_knowledge': {
            'iforest_fitted_on_campaign_train': True,
            'iforest_campaign_test_scores_seen': False},
        'h4_clause_analysis': {
            'overall_status_unchanged': one['status'],
            'why_unchanged': ('the registered refutation condition is "another fold has a '
                              'strictly higher rate for EITHER detector"; the envelope half '
                              'already triggered it, so no IF evidence can reverse the overall decision'),
            'envelope_clause': 'refuted (fold normal|1 87.29% > fold vary 78.81%)',
            'iforest_clause': status, 'iforest_evidence': evidence,
            'reading': ('the envelope count is driven by how OFTEN a bound is crossed; '
                        'the IF score by how FAR a row lies from the training manifold')},
        'predictions_recorded_before_test': {
            'fpr_direction': ('FPR on C-vary is expected to exceed FPR on C-load2M; '
                              'this is a direction, not a magnitude'),
            'fpr_magnitude_warning': (
                'the %.2f%% held-out alarm rate on the vary fold must NOT be read as a '
                'prediction of test FPR on C-vary. The vary fold is a counterfactual in '
                'which N-vary training runs are removed. The test model is trained on all '
                'four configs including vary; this predicts Phase 7 behavior for a profile '
                'absent from training. Seed range %.2f%% to %.2f%%.' % (vary_mean, lo, hi)),
            'threshold_ownership': (
                'the bottom q of full-train scores is owned by %s; benign load dynamics '
                'sets the threshold, so recall is expected lowest on milder throughput '
                'faults, particularly degrade' % ownership['tail_dominated_by']),
            'dynamics_not_only_level': (
                'p95 max|d1| is %.1f on varying versus %.1f on fixed configs (factor %s); '
                'the vary fold extrapolates in dynamics as well as level' %
                (dynamics['p95_max_abs_d1_varying_config'] or float('nan'),
                 dynamics['p95_max_abs_d1_fixed_configs'],
                 dynamics['dynamics_extrapolation_factor'])),
            'no_tuning': 'q, seeds, max_samples, columns and hyperparameters remain registered'},
    }


def main():
    if OUT.exists():
        print('[ledger2] exists; refusing overwrite'); return 1
    content = current_content()
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, HASH_FIELD: content_hash(content)}
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2); handle.write('\n')
    h4 = content['h4_clause_analysis']
    print('[ledger2] H4 overall:', h4['overall_status_unchanged'])
    print('[ledger2] H4 IF clause:', h4['iforest_clause'])
    print('[ledger2] every seed:', h4['iforest_evidence']['holds_for_every_seed'])
    print('[ledger2] SHA:', document[HASH_FIELD]); return 0


if __name__ == '__main__':
    raise SystemExit(main())
