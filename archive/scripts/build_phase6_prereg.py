#!/usr/bin/env python3
"""Lesson 6.1 — Sinh BẢN ĐĂNG KÝ TRƯỚC (pre-registration) cho Phase 6.

VÌ SAO LÀ SCRIPT, KHÔNG GÕ TAY JSON:
    Con số (160 dương, trần recall 95%...) được DẪN XUẤT từ manifest đã commit,
    không gõ lại bằng tay. Gõ tay = một cơ hội để lệch với dữ liệu thật.

VÌ SAO TỪ CHỐI GHI ĐÈ:
    Bản đăng ký chỉ có giá trị nếu nó KHÔNG ĐỔI sau khi thấy kết quả.
    Muốn sửa -> viết AMENDMENT (file mới, có lý do, có ngày), không sửa bản gốc.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ml.campaign import ROOT, canonical_json, sha256_bytes, sha256_file

PREREG_ID = 'DT4N-P6-PREREG-v1'
OUT = ROOT / 'results/report/phase6_prereg.json'
SPLIT_MANIFEST = ROOT / 'results/report/ml_dataset_split_manifest.json'
GROUND_TRUTH = ROOT / 'results/report/ground_truth.json'
MISSING = ROOT / 'results/report/campaign_missing_analysis.json'
HASH_FIELD = 'prereg_content_sha256'


# ---------------------------------------------------------------------------
# 1. HASH — chỉ băm phần QUYẾT ĐỊNH ('content'), không băm thời điểm ghi
# ---------------------------------------------------------------------------
def content_hash(content: dict) -> str:
    return sha256_bytes(canonical_json(content).encode('utf-8'))


# ---------------------------------------------------------------------------
# 2. FACTS — dẫn xuất từ file đã commit, kèm kiểm tra chéo
# ---------------------------------------------------------------------------
def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def derive_facts(split_m: dict, gt: dict, missing: dict) -> dict:
    tests = [t for t in gt['tables'] if t['split'] == 'test']
    pos = sum(t['counts']['primary_fault_ticks'] for t in tests)
    neg = sum(t['counts']['primary_normal_ticks'] for t in tests)
    neg_control = sum(t['counts']['primary_normal_ticks'] for t in tests if t['group'] == 'C')
    if pos + neg != split_m['shape']['n_test_rows']:
        raise ValueError('ground_truth va split manifest lech so dong test')
    if pos != split_m['base_rate']['primary']['anomalous']:
        raise ValueError('so tick duong lech manifest')

    env_cols = set(split_m['envelope_feature_names'])
    # IF: 'unjudgeable_rows' duoc tinh tren dung 72 cot IF
    if_unknown = {(r['run_id'], r['tick']): r['is_fault'] for r in split_m['unjudgeable_rows']}
    # Envelope: dong co o thieu o bat ky cot envelope nao
    env_unknown = {(e['run_id'], e['tick']): e['is_fault']
                   for e in missing['non_warmup_invalid_events']
                   if any(c.startswith(e['link'] + '.') for c in env_cols)}
    env_unknown.update({(r['run_id'], r['tick']): r['is_fault']
                        for r in split_m['unjudgeable_rows']
                        if env_cols & set(r['missing_features'])})
    if len(env_unknown) != split_m['envelope_test_rows_with_missing']:
        raise ValueError('khong tai lap duoc tap dong envelope thieu')
    # Hybrid (luat OR tren detector PHAN DUOC): unknown khi CA HAI unknown
    hyb_unknown = {k: v for k, v in env_unknown.items() if k in if_unknown}

    keyed_truth = {(t['run_id'],tick): y for t in tests for tick,y,mask in zip(t['ticks'],t['y'],t['eval_primary']) if mask == 1}
    for unknown in (if_unknown,env_unknown):
        if any(key not in keyed_truth or keyed_truth[key] != y for key,y in unknown.items()):
            raise ValueError('unknown keys/labels disagree with ground truth')
    if len(if_unknown) != split_m['unjudgeable_test_ticks']['total']:
        raise ValueError('IF unknown count mismatch')

    def summary(unknown: dict) -> dict:
        n_pos = int(sum(unknown.values()))
        return {'n_unknown': len(unknown), 'n_unknown_positive': n_pos,
                'n_unknown_negative': len(unknown) - n_pos,
                'recall_ceiling': round((pos - n_pos) / pos, 4),
                'free_true_negatives': len(unknown) - n_pos,
                'unknown_keys': sorted([list(k) for k in unknown])}

    return {
        'n_train_rows_if': split_m['shape']['n_train_rows'],
        'n_train_rows_envelope': split_m['envelope_fit_train_rows'],
        'n_test_rows': split_m['shape']['n_test_rows'],
        'n_positive': pos, 'n_negative': neg,
        'n_negative_control_runs': neg_control,
        'n_negative_in_fault_runs': neg - neg_control,
        'always_normal_accuracy': round(neg / (pos + neg), 4),
        'n_if_features': len(split_m['feature_names']),
        'n_envelope_columns': len(env_cols),
        'n_envelope_only_columns': split_m['n_envelope_only_columns'],
        'n_envelope_if_overlap': split_m['n_envelope_if_overlap'],
        'unknown': {'iforest': summary(if_unknown),
                    'envelope': summary(env_unknown),
                    'hybrid_or': summary(hyb_unknown)},
    }


# ---------------------------------------------------------------------------
# 3. CÁC QUYẾT ĐỊNH — mọi bậc tự do phải ĐÓNG ở đây
# ---------------------------------------------------------------------------
QUANTILES = [0.005, 0.01, 0.02, 0.05]
SEEDS = [0, 1, 2, 3, 4]

METRICS = {
    'forbidden': ['accuracy', 'point_adjust_as_primary', 'best_threshold_on_test'],
    'primary_mask': 'eval_primary (warmup only)',
    'secondary_mask': 'eval_sensitivity (onset 2 / recovery 2)',
    'unknown_policy': 'unknown -> no alarm; y=1 -> FN; unknown counts reported per detector',
    'always_report_together': ['recall', 'FPR'],
    'recall_reported_with_ceiling': True,
    'fpr_levels': ['FPR_control', 'FPR_in_fault_runs', 'FPR_all', 'FPR_all_judgeable_only'],
    'precision_note': 'base-rate dependent (design 27.12%); not operational precision',
    'delay': {'definition': 'first alarm tick in [inject+1, revert] minus (inject+1)',
              'mask': 'eval_primary', 'undetected': 'censored (None), counted separately',
              'summary': 'median over detected incidents + n_censored; no mean'},
    'uncertainty': {'method': 'cluster bootstrap by run_id, stratified by group (C, F)',
                    'n_boot': 2000, 'rng_seed': 20260916, 'ci': [2.5, 97.5],
                    'per_fault_type': 'no CI (2 runs/type); report per-run values'},
    'comparison_sets': {'primary': 'all 590 rows, same mask, same metric code',
                        'secondary': 'rows judgeable by BOTH detectors'},
}

DECISION_RULES = {
    'iforest': {'score': 'score_samples (lower = more anomalous)',
                'alarm': 'score < quantile(train_scores, q)',
                'quantiles': QUANTILES, 'primary_q': 0.01,
                'never_use': ['predict()', 'decision_function offset',
                              'contamination derived from test']},
    'envelope': {'primary': 'k > K, k = strict bound violations over 71 columns',
                 'K_rule': 'K = max held-out k over GroupKFold(config_id, n_splits=4)',
                 'secondary': 'excess > E, E = max held-out excess, range floor = campaign.SEPARATION_FLOOR',
                 'cv_refit': 'each fold refits link_stats, selection, bounds on fold-train only'},
    'hybrid_or': {'rule': 'alarm iff any JUDGEABLE member alarms; unknown iff all members unknown',
                  'iforest_member': 'primary config, evaluated per seed'},
}

DETECTORS = {
    'iforest': {'n_estimators': 300, 'max_samples': [256, 1.0], 'primary_max_samples': 256,
                'max_features': 1.0, 'bootstrap': False, 'contamination': 'auto',
                'seeds': SEEDS, 'report': 'mean, std, min, max over seeds'},
    'envelope': {'columns': 'split manifest envelope_feature_names (71)', 'bounds': 'strict min/max of fold-train'},
    'random_noise_control': {'what': 'IF on N(0,1) matrix of train shape, same pipeline', 'seeds': SEEDS},
}

HYPOTHESES = [
    {'id': 'H1', 'kind': 'confirmatory',
     'claim': 'On the 2 admin_down runs, envelope recall >= IF recall (mean over seeds, primary config).',
     'mechanism': 'state_up/links_down constant on train -> only envelope sees them; link-s1-s2 rates reach 0 in train (min=0) so rate-only view is ambiguous there.',
     'refuted_if': 'envelope recall < IF mean recall on admin_down (pooled 40 ticks).'},
    {'id': 'H2', 'kind': 'confirmatory_single_run',
     'claim': 'On F-degrade-s2-s3: envelope delay = 1 tick, every primary IF seed delay = 2 ticks, loss-only envelope delay in [9, 11].',
     'mechanism': 'tick 21 unknown for both (counter_reset); tick 22 unknown for IF only (d1 NaN); full envelope contains link-s2-s3.txRate with train band [268256, 271142] B/s; lossPct first crosses at tick 31.',
     'refuted_if': 'envelope delay is not 1, any primary IF seed delay is not 2, or loss-only delay is outside [9,11]; censored also refutes.',
     'caveat': 'n = 1 run: an observation, not a statistical test.'},
    {'id': 'H3', 'kind': 'confirmatory',
     'claim': 'IF-only positive ticks (caught by IF, missed by envelope) >= 8 (5% of 160) in >= 4 of 5 seeds.',
     'mechanism': 'degrade s1-s2 has no loss witness and wide train rate bands may hide a low-intensity shift; IF has d1.* and multivariate combinations.',
     'refuted_if': 'IF-only ticks < 8 in >= 2 seeds.',
     'note': 'recall_hybrid >= max(recall_env, recall_IF) is a TAUTOLOGY of the OR rule, not a hypothesis.'},
    {'id': 'H4', 'kind': 'confirmatory_train_cv',
     'claim': 'Among 4 config folds, the held-out vary fold has the highest held-out alarm rate for BOTH envelope (share of rows with k>0) and IF (q=0.01).',
     'mechanism': 'SCHEDULE_A contains 5 Mbps and +/-3..4 Mbps steps; fixed configs stop at 4 Mbps with no steps -> extrapolation. 4M fold is covered by vary -> interpolation.',
     'refuted_if': 'another fold has a strictly higher rate for either detector.'},
    {'id': 'H5', 'kind': 'confirmatory',
     'claim': 'FPR on C-vary > FPR on C-load2M for both detectors.',
     'mechanism': 'SCHEDULE_B has a 1->5 Mbps step (+4) absent from SCHEDULE_A (max +3); C-load2M equals a train config.',
     'refuted_if': 'FPR(C-vary) <= FPR(C-load2M) for either detector.'},
]

# Close details that otherwise admit incompatible implementations in Phase 6.
METRICS['precision_note'] += '; may compare descriptively on this fixed test, not extrapolate to deployment'
METRICS['unknown_policy'] += '; y=0 operational no-alarm counted TN, explicitly called operational TN rather than a normal judgement'
METRICS['zero_denominator'] = 'undefined metric is None with denominator/count reported; no zero substitution'
METRICS['seed_summary'] = 'mean, sample std(ddof=1), min, max over five fixed seeds; bootstrap CI computed per seed, not pooled seed rows'
METRICS['uncertainty']['resampling'] = 'sample 2 C and 8 F run_ids independently with replacement, preserve all rows/tick order, recompute ratios per seed; detectors not refitted'
METRICS['uncertainty']['undefined_replicates'] = 'omit undefined ratios and report valid replicate count; all undefined => CI None'
METRICS['fpr_denominators'] = 'control118; fault-run normal312; all430; judgeable negatives detector-specific (IF412/env426); secondary common-judgeable uses identical rows'
DECISION_RULES['iforest']['quantile_method'] = 'numpy.quantile(method=linear) on finite train scores; equality to threshold => no alarm'
DECISION_RULES['envelope']['cv_protocol'] = 'GroupKFold(4, shuffle=False) on normal config_id; refit all preprocessing and selection on fold-train; drop warmup then deltas per run; calibrate max finite k across judgeable validation rows; refit final bounds on all472 normal rows; save learned K in new Phase6 model artifact, never edit Phase5 K=0 manifest'
DECISION_RULES['envelope']['secondary_formula'] = 'excess = sum_j max(lo_j-x_j, x_j-hi_j, 0)/max(hi_j-lo_j, floor_j); unknown iff any selected x_j missing; E=max excess on judgeable fold-validation rows; alarm strictly excess>E'
DECISION_RULES['envelope']['floors'] = {'rxRate':10000.0,'txRate':10000.0,'lossPct':0.1,'state_up':0.01,'all_other_registered_columns':1.0}
DECISION_RULES['envelope']['calibration_failure'] = 'stop if any fold has no judgeable calibration row; report calibration counts, no fallback K'
DETECTORS['loss_only_ablation'] = {'columns':'only 8 raw link-*.traffic.lossPct columns from full envelope; exclude drop/state/rate/aggregate', 'rule':'refit loss-only bounds/K independently in normal4fold CV; unknown if any of8missing; primary mask'}
DETECTORS['random_noise_control'] = {'what':'IF on independent synthetic Gaussian matrices464x72train and590x72test, apply campaign IF unknown mask for equal coverage; no feature selection on test noise', 'seeds':SEEDS,'rng_rule':'default_rng(10000+seed), draw train then test; IF primary config/q=0.01; report as synthetic control, not a trained campaign detector'}
for h in HYPOTHESES:
    h['comparison_config'] = 'primary mask, max_samples256, q0.01; IF mean five seeds unless hypothesis specifies each seed'
HYPOTHESES[3]['comparison_config'] = 'held-out normal folds; envelope uncalibrated k>0 alarm rate, IF mean five primary-seed alarm rates; vary ties for highest allowed'
HYPOTHESES[4]['comparison_config'] = 'operational FPR on all59ticks of each C run; IF mean five primary-seed FPR; judgeable-only FPR reported separately'


RUN_PREDICTIONS = [
 {'run_id':'C-load2M-s2001-r1','envelope':'lower FPR than C-vary, narrow rate bands may still trigger','iforest':'lower FPR than C-vary; not guaranteed near q','delay':'not applicable: normal control','confidence':'moderate'},
 {'run_id':'C-vary-s2002-r1','envelope':'higher FPR than C-load2M','iforest':'higher FPR than C-load2M around untrained load steps','delay':'not applicable: normal control','confidence':'moderate'},
 {'run_id':'F-admin_down-s1-s2-s3001-r1','envelope':'recall >= IF expected; calibrated K can suppress small violation counts','iforest':'rate zero may be familiar in train','delay':'0 expected for envelope; IF may be censored','confidence':'low: K not yet calibrated'},
 {'run_id':'F-admin_down-s1-s3-s3002-r1','envelope':'relatively high recall expected if K permits state violation counts','iforest':'relatively high recall from unfamiliar zero rates','delay':'0 / 0 expected','confidence':'moderate'},
 {'run_id':'F-degrade-s1-s2-s3003-r1','envelope':'low recall expected; wide normal load envelope','iforest':'low to moderate recall; temporal/multivariate changes may help','delay':'censoring possible for both','confidence':'low'},
 {'run_id':'F-degrade-s2-s3-s3004-r1','envelope':'relatively high recall expected from narrow fixed-background rate band','iforest':'relatively high recall expected, subject to fitted train threshold','delay':'1 / 2 expected; loss-only 9..11','confidence':'low to moderate: structural minima do not guarantee threshold crossing'},
 {'run_id':'F-flood-h1_to_srv1-s3005-r1','envelope':'relatively high recall expected from loss/rate violations','iforest':'relatively high recall expected from rates','delay':'0 / 0 expected','confidence':'moderate'},
 {'run_id':'F-flood-h2_to_srv2-s3006-r1','envelope':'relatively high recall expected from loss/rate violations','iforest':'relatively high recall expected from rates','delay':'0 / 0 expected','confidence':'moderate'},
 {'run_id':'F-shift-s1-s2-s3007-r1','envelope':'relatively high recall expected','iforest':'relatively high recall expected','delay':'1 / 2 expected because of missing features','confidence':'moderate'},
 {'run_id':'F-shift-s1-s3-s3008-r1','envelope':'relatively high recall expected','iforest':'relatively high recall expected','delay':'1 / 2 expected because of missing features','confidence':'moderate'},
]


PRIOR_KNOWLEDGE = [
    'Phase 5 inspected TEST signals: max_separation, witness onset, counter_reset ticks.',
    'Envelope bounds/statistics already fitted on campaign normal train in Phase 5; no campaign IF fitted and no campaign detector predictions/scores evaluated on test. Synthetic IF blindness experiments were run.',
    'Hypotheses are about DETECTOR behaviour; they are not blind to test DATA.',
]

DEVIATION_POLICY = {
    'original_file': 'never edited after commit',
    'amendment': 'results/report/phase6_prereg_amendment_<n>.json with reason, date, prereg SHA, and whether test results were seen',
    'reporting': 'every deviation listed in final Phase 6 report',
}


def build_content(facts: dict, bound_to: dict) -> dict:
    return {'prereg_id': PREREG_ID, 'bound_to': bound_to, 'prior_knowledge': PRIOR_KNOWLEDGE,
            'facts': facts, 'metrics': METRICS, 'decision_rules': DECISION_RULES,
            'detectors': DETECTORS, 'hypotheses': HYPOTHESES, 'run_predictions': RUN_PREDICTIONS,
            'deviation_policy': DEVIATION_POLICY}


def current_content(root: Path = ROOT) -> dict:
    split_path = root / 'results/report/ml_dataset_split_manifest.json'
    gt_path = root / 'results/report/ground_truth.json'
    missing_path = root / 'results/report/campaign_missing_analysis.json'
    split_m = _read(split_path)
    facts = derive_facts(split_m, _read(gt_path), _read(missing_path))
    bound_to = {'dataset_version': split_m['dataset_version'],
                'label_convention_id': split_m['label_convention_id'],
                'design_content_sha256': split_m['design_content_sha256'],
                'split_manifest_sha256': sha256_file(split_path),
                'ground_truth_sha256': sha256_file(gt_path),
                'missing_report_sha256': sha256_file(missing_path),
                'dataset_source_sha256': split_m['source_sha256']}
    return build_content(facts, bound_to)


def _git(*args) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main() -> int:
    if OUT.exists():
        print('[prereg] DA TON TAI -> khong ghi de. Muon doi: viet amendment.')
        return 1
    content = current_content()
    doc = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'written_from_git': _git('rev-parse', 'HEAD'),
           'content': content, HASH_FIELD: content_hash(content)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('x', encoding='utf-8') as out:
        out.write(json.dumps(doc, indent=2, ensure_ascii=False) + '\n')
    u = content['facts']['unknown']
    print('[prereg] SHA  :', doc[HASH_FIELD])
    print('[prereg] tran recall IF/env/hybrid: %.4f / %.4f / %.4f' % (
        u['iforest']['recall_ceiling'], u['envelope']['recall_ceiling'], u['hybrid_or']['recall_ceiling']))
    print('[prereg] accuracy mo hinh ngu     :', content['facts']['always_normal_accuracy'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
