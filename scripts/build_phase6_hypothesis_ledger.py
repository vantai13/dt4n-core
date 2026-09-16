#!/usr/bin/env python3
"""Freeze envelope-only hypothesis decisions before any campaign IF fit."""
import json
from datetime import datetime, timezone

from ml.campaign import ROOT, canonical_json, sha256_bytes

REPORT = ROOT / 'results/report'
OUT = REPORT / 'phase6_hypothesis_ledger.json'
PREREG = REPORT / 'phase6_prereg.json'
AM1 = REPORT / 'phase6_prereg_amendment_1.json'
AM2 = REPORT / 'phase6_prereg_amendment_2.json'
CV = REPORT / 'phase6_envelope_cv.json'
TEST = REPORT / 'phase6_envelope.json'
HASH_FIELD = 'ledger_content_sha256'

DEGRADE_RUN = 'F-degrade-s2-s3-s3004-r1'
VARY_FOLD = 'normal_varying|vary'
LOSS_ONLY_DELAY_RANGE = (9, 11)


def content_hash(value):
    return sha256_bytes(canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sealed_sources():
    prereg = _read(PREREG)
    amendment1, amendment2 = _read(AM1), _read(AM2)
    cv, test = _read(CV), _read(TEST)
    checks = {
        'prereg': content_hash(prereg['content']) == prereg['prereg_content_sha256'],
        'amendment_1': content_hash(amendment1['content']) == amendment1['amendment_content_sha256'],
        'amendment_2': content_hash(amendment2['content']) == amendment2['amendment_content_sha256'],
        'envelope_cv': content_hash(cv['content']) == cv['content_sha256'],
        'envelope_test': content_hash(test['content']) == test['content_sha256'],
    }
    broken = sorted(name for name, ok in checks.items() if not ok)
    if broken:
        raise ValueError('nguon bi sua sau khi ky: %s' % broken)
    chain = [
        test['content']['cv_content_sha256'] == cv['content_sha256'],
        test['content']['prereg_content_sha256'] == prereg['prereg_content_sha256'],
        cv['content']['amendment2_content_sha256'] == amendment2['amendment_content_sha256'],
        amendment2['content']['amendment_1_content_sha256'] == amendment1['amendment_content_sha256'],
        amendment1['content']['amends_prereg_content_sha256'] == prereg['prereg_content_sha256'],
    ]
    if not all(chain):
        raise ValueError('chuoi tham chieu artifact bi dut')
    return {'prereg': prereg, 'amendment_1': amendment1,
            'amendment_2': amendment2, 'cv': cv, 'test': test}


def decide_h2(src):
    variants = src['test']['content']['variants']
    envelope_delay = variants['primary_k']['delay']['per_run'][DEGRADE_RUN]
    loss_delay = variants['ablation_loss_only']['delay']['per_run'][DEGRADE_RUN]
    lo, hi = LOSS_ONLY_DELAY_RANGE
    clause_envelope = envelope_delay == 1
    clause_loss = loss_delay is not None and lo <= loss_delay <= hi
    evidence = {
        'run': DEGRADE_RUN,
        'envelope_primary_delay': envelope_delay,
        'envelope_primary_censored': envelope_delay is None,
        'clause_envelope_delay_eq_1_holds': clause_envelope,
        'loss_only_delay': loss_delay,
        'loss_only_range_registered': list(LOSS_ONLY_DELAY_RANGE),
        'clause_loss_only_in_range_holds': clause_loss,
        'iforest_per_seed_delay': None,
    }
    status = 'pending' if clause_envelope else 'refuted'
    return status, evidence, (
        'Clause envelope delay = 1 bi bac bo: detector primary bi CENSORED tren run nay '
        '(khong bao dong trong toan cua so loi) vi K=31 chan. Dieu kien dang ky ghi ro '
        '"censored also refutes", va H2 la lien ket AND, nen H2 BI BAC BO ma khong can IF. '
        'Clause loss-only delay = 10 nam trong [9,11] DUOC XAC NHAN va xac nhan dung co che '
        'onset cua lossPct (xuat hien tu tick 31, tuc 10 tick sau inject).')


def decide_h4(src):
    folds = src['cv']['content']['folds']
    rates = {fold['held_out_config']:
             fold['families']['primary']['share_k_gt_0'] for fold in folds}
    vary = rates[VARY_FOLD]
    others = {key: value for key, value in rates.items() if key != VARY_FOLD}
    highest = max(others, key=others.get)
    refuted = others[highest] > vary
    evidence = {
        'metric': 'share of judgeable held-out rows with primary k>0 (amendment 2)',
        'envelope_share_k_gt_0_by_fold': rates,
        'vary_fold_share': vary,
        'highest_other_fold': highest,
        'highest_other_share': others[highest],
        'strictly_higher_than_vary': refuted,
        'iforest_alarm_rate_by_fold': None,
    }
    return ('refuted' if refuted else 'pending'), evidence, (
        'Fold 1 Mbps dat 87.29% > fold vary 78.81%. Dieu kien dang ky: "another fold has a '
        'strictly higher rate for EITHER detector" => H4 BI BAC BO bang bang chung envelope, '
        'khong can IF. Co che da khai bao truoc CV o amendment 2: voi nhieu iid, mot diem moi '
        'roi ngoai min/max cua n diem fit voi xac suat 2/(n+1), nen fold tai thap co the co '
        'k>0 ma khong can ngoai suy ve muc tai. Tach ro: K=31 den tu fold vary (do SO LUONG '
        'kenh vuot dong thoi lon nhat), con TAN SO vuot cao nhat o fold 1M. Hai dai luong khac '
        'nhau; H4 dang ky theo TAN SO.')


def decide_h5(src):
    per_run = src['test']['content']['variants']['primary_k']['fpr']['per_control_run']
    vary = per_run['C-vary-s2002-r1']['fpr']
    load2m = per_run['C-load2M-s2001-r1']['fpr']
    refuted = vary <= load2m
    evidence = {
        'envelope_primary_fpr_C_vary': vary,
        'envelope_primary_fpr_C_load2M': load2m,
        'envelope_clause_refutes': refuted,
        'iforest_fpr_C_vary': None,
        'iforest_fpr_C_load2M': None,
    }
    return ('refuted' if refuted else 'pending'), evidence, (
        'Ca hai run doi chung cho FPR = 0.0 voi detector primary, nen khong co bang chung '
        'nao rang C-vary kho hon C-load2M. Dieu kien dang ky: "FPR(C-vary) <= FPR(C-load2M) '
        'for EITHER detector" => H5 BI BAC BO. Luu y dien giai: FPR=0 o day la he qua cua '
        'K=31 chan het, KHONG phai bang chung rang envelope tong quat tot sang tai chua thay; '
        'bang chung ve dieu do nam o CV (fold 1M va vary), va no noi nguoc lai.')


def decide_h1(src):
    pooled = src['test']['content']['variants']['primary_k']['by_fault']['admin_down']['pooled']
    return 'pending', {
        'envelope_primary_recall_admin_down': pooled['recall'],
        'envelope_primary_tp': pooled['tp'],
        'envelope_primary_n_positive': pooled['n_positive'],
        'iforest_recall_admin_down': None,
    }, ('Chot truoc: envelope primary recall = 0.0 tren admin_down. H1 chi bi bac bo '
        'neu IF recall > 0. Khi bao cao, PHAI tach: bac bo H1 la ve NGUONG K chan, '
        'khong phai ve kenh — bang chung la secondary_dual dat recall 1.0 tren '
        'admin_down trong khi ablation loss_only dat 0.0, tuc kenh state_up CO tin hieu.')


def decide_h3(src):
    scores = src['test']['content']['variants']['primary_k']['scores']
    return 'pending', {
        'registered_comparator': 'envelope primary count (k > K)',
        'envelope_primary_tp': scores['tp'],
        'envelope_primary_fn': scores['fn'],
        'envelope_primary_recall': scores['recall'],
        'iforest_only_ticks_per_seed': None,
    }, ('CANH BAO TRIVIAL CONFIRMATION, chot truoc khi chay IF: comparator da dang ky '
        '(envelope primary) co recall 0.0, tuc no bo sot TAT CA 160 tick duong. Vi vay '
        '"IF-only ticks" = "moi tick IF bat duoc", va H3 gan nhu chac chan duoc xac nhan '
        'KHONG phai vi tinh bu tru ma vi comparator da sap. Quy uoc bao cao chot tu gio: '
        '(a) CONFIRMATORY dung dinh nghia da dang ky, kem cau nay; (b) DESCRIPTIVE lap lai '
        'voi comparator = secondary_excess (da dang ky o amendment 1, truoc khi thay test). '
        'Khong duoc thay (b) vao cho (a).')


DECIDERS = {'H1': decide_h1, 'H2': decide_h2, 'H3': decide_h3,
            'H4': decide_h4, 'H5': decide_h5}


def current_content():
    src = sealed_sources()
    registered = {row['id']: row for row in src['prereg']['content']['hypotheses']}
    if set(registered) != set(DECIDERS):
        raise ValueError('so gia thuyet lech prereg: %s' % sorted(registered))
    entries = {}
    for name, decide in sorted(DECIDERS.items()):
        status, evidence, note = decide(src)
        row = registered[name]
        entries[name] = {
            'registered_kind': row['kind'],
            'registered_claim': row['claim'],
            'registered_mechanism': row['mechanism'],
            'registered_refutation': row['refuted_if'],
            'status': status,
            'decided_by': ('envelope_evidence_only' if status == 'refuted'
                           else 'requires_iforest'),
            'evidence': evidence,
            'note': note,
        }
    return {
        'ledger_id': 'DT4N-P6-HYPOTHESIS-LEDGER-v1',
        'purpose': ('Freeze hypothesis decisions that envelope evidence alone already '
                    'settles, BEFORE any Isolation Forest fit on campaign train data.'),
        'decision_rule': ('status is derived from the registered refutation condition '
                          'applied to sealed artifacts; no condition is reinterpreted, '
                          'no hypothesis is amended, no threshold is changed'),
        'bound_to': {
            'prereg_content_sha256': src['prereg']['prereg_content_sha256'],
            'amendment_1_content_sha256': src['amendment_1']['amendment_content_sha256'],
            'amendment_2_content_sha256': src['amendment_2']['amendment_content_sha256'],
            'envelope_cv_content_sha256': src['cv']['content_sha256'],
            'envelope_test_content_sha256': src['test']['content_sha256'],
        },
        'timing_and_knowledge': {
            'iforest_fitted_on_campaign_train': False,
            'iforest_campaign_test_scores_seen': False,
            'envelope_campaign_test_scores_seen': True,
        },
        'hypotheses': entries,
        'summary': {
            'refuted': sorted(k for k, v in entries.items() if v['status'] == 'refuted'),
            'pending': sorted(k for k, v in entries.items() if v['status'] == 'pending'),
        },
    }


def main():
    if OUT.exists():
        print('[ledger] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        HASH_FIELD: content_hash(content),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    for name, row in sorted(content['hypotheses'].items()):
        print('[ledger] %s -> %-8s (%s)' % (name, row['status'], row['decided_by']))
    print('[ledger] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
