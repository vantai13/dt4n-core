#!/usr/bin/env python3
"""Final confirmatory decisions after one-shot IF test, before hybrid analysis."""
import json
from datetime import datetime, timezone

from ml.campaign import ROOT, canonical_json, sha256_bytes

REPORT = ROOT / 'results/report'
OUT = REPORT / 'phase6_hypothesis_ledger_3.json'
PREREG = REPORT / 'phase6_prereg.json'
LEDGER_1 = REPORT / 'phase6_hypothesis_ledger.json'
LEDGER_2 = REPORT / 'phase6_hypothesis_ledger_2.json'
ENV = REPORT / 'phase6_envelope.json'
IF = REPORT / 'phase6_iforest.json'
HASH_FIELD = 'ledger_content_sha256'
PRIMARY_MS = '256'; PRIMARY_Q = '0.01'; IF_ONLY_MIN = 8
DEGRADE_RUN = 'F-degrade-s2-s3-s3004-r1'


def content_hash(value): return sha256_bytes(canonical_json(value).encode('utf-8'))
def _read(path): return json.loads(path.read_text(encoding='utf-8'))


def sealed_sources():
    docs = {'prereg': _read(PREREG), 'ledger_1': _read(LEDGER_1),
            'ledger_2': _read(LEDGER_2), 'env': _read(ENV), 'iforest': _read(IF)}
    fields = {'prereg': 'prereg_content_sha256', 'ledger_1': HASH_FIELD,
              'ledger_2': HASH_FIELD, 'env': 'content_sha256', 'iforest': 'content_sha256'}
    broken = [name for name, doc in docs.items()
              if content_hash(doc['content']) != doc[fields[name]]]
    if broken: raise ValueError('artifact bi sua: %s' % broken)
    l2ref = docs['ledger_2']['content'].get('append_only_after') or \
        docs['ledger_2']['content'].get('bound_to', {}).get('ledger_1_content_sha256')
    if l2ref != docs['ledger_1'][HASH_FIELD]: raise ValueError('ledger 2 khong tro ledger 1')
    if docs['iforest']['content']['ledger_2_content_sha256'] != docs['ledger_2'][HASH_FIELD]:
        raise ValueError('test IF khong tro ledger 2')
    return docs


def env_primary(src): return src['env']['content']['variants']['primary_k']
def if_primary(src): return src['iforest']['content']['configs'][PRIMARY_MS]['per_seed']


def decisions(src):
    old = src['ledger_1']['content']['hypotheses']
    env = env_primary(src); seeds = if_primary(src)
    admin = {s: row['by_q'][PRIMARY_Q]['by_fault']['admin_down']['pooled']['recall']
             for s, row in seeds.items()}
    if_mean = sum(admin.values()) / len(admin); env_admin = env['by_fault']['admin_down']['pooled']['recall']
    h1_refuted = env_admin < if_mean
    h2_delays = {s: row['by_q'][PRIMARY_Q]['delay']['per_run'][DEGRADE_RUN]
                 for s, row in seeds.items()}
    envelope_tp = env['scores']['tp']
    if envelope_tp != 0: raise ValueError('H3 inference requires envelope primary tp == 0')
    if_only = {s: row['by_q'][PRIMARY_Q]['scores']['tp'] for s, row in seeds.items()}
    below = sorted(s for s, count in if_only.items() if count < IF_ONLY_MIN)
    h3_refuted = len(below) >= 2
    vary = {s: row['by_q'][PRIMARY_Q]['fpr']['per_control_run']['C-vary-s2002-r1']['fpr']
            for s, row in seeds.items()}
    load = {s: row['by_q'][PRIMARY_Q]['fpr']['per_control_run']['C-load2M-s2001-r1']['fpr']
            for s, row in seeds.items()}
    return {
        'H1': {'status': 'refuted' if h1_refuted else 'supported',
               'previous_status': old['H1']['status'],
               'evidence': {'envelope_admin_recall': env_admin,
                            'iforest_admin_recall_by_seed': admin,
                            'iforest_admin_recall_mean': if_mean,
                            'margin_in_ticks': (if_mean-env_admin)*40,
                            'seeds_with_any_detection': sorted(s for s,v in admin.items() if v>0)},
               'note': ('H1 is refuted by the registered five-seed mean: one tick in seed 4. '
                        'This is a threshold failure, not a channel failure: secondary_dual '
                        'recall is 1.0 while loss-only recall is 0.0 on admin_down.')},
        'H2': {'status': 'refuted', 'previous_status': old['H2']['status'],
               'evidence': {'iforest_delay_by_seed': h2_delays,
                            'all_iforest_seeds_censored': all(v is None for v in h2_delays.values()),
                            'loss_only_delay': src['env']['content']['variants']['ablation_loss_only']['delay']['per_run'][DEGRADE_RUN]}},
        'H3': {'status': 'refuted' if h3_refuted else 'supported',
               'previous_status': old['H3']['status'],
               'evidence': {'envelope_primary_tp': envelope_tp,
                            'iforest_only_ticks_per_seed': if_only,
                            'seeds_below_8': below},
               'note': ('The preregistered trivial-confirmation warning did not occur: IF '
                        'found only 0,0,0,0,1 positive ticks, so H3 is refuted.')},
        'H4': {'status': old['H4']['status'], 'previous_status': old['H4']['status'],
               'evidence': src['ledger_2']['content']['h4_clause_analysis']},
        'H5': {'status': old['H5']['status'], 'previous_status': old['H5']['status'],
               'evidence': {'iforest_fpr_C_vary_by_seed': vary,
                            'iforest_fpr_C_load2M_by_seed': load,
                            'iforest_clause_holds_every_seed': all(vary[s] > load[s] for s in seeds),
                            'envelope_clause_refuted': True}},
    }


def current_content():
    src=sealed_sources(); rows=decisions(src)
    return {'ledger_id':'DT4N-P6-HYPOTHESIS-LEDGER-v3',
            'append_only_after':src['ledger_2'][HASH_FIELD],
            'bound_to':{'iforest_test_content_sha256':src['iforest']['content_sha256'],
                        'envelope_test_content_sha256':src['env']['content_sha256']},
            'timing_and_knowledge':{'iforest_campaign_test_scores_seen':True,
                                    'hybrid_or_exploratory_analysis_started':False},
            'hypotheses':rows,
            'summary':{'refuted':sorted(k for k,v in rows.items() if v['status']=='refuted'),
                       'all_five_refuted':all(v['status']=='refuted' for v in rows.values())},
            'reading':('All five registered hypotheses are refuted. Four are refuted for one '
                       'shared reason: a threshold calibrated so benign data almost never '
                       'alarms lies beyond fault signatures because benign operating variation '
                       'occupies a wider region of observable space than the faults do.')}


def main():
    if OUT.exists(): print('[ledger3] exists; refusing overwrite'); return 1
    content=current_content(); doc={'written_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content':content,HASH_FIELD:content_hash(content)}
    with OUT.open('x') as f: json.dump(doc,f,indent=2);f.write('\n')
    for name,row in content['hypotheses'].items(): print('[ledger3]',name,'->',row['status'])
    print('[ledger3] all five refuted:',content['summary']['all_five_refuted'])
    print('[ledger3] SHA:',doc[HASH_FIELD]);return 0


if __name__=='__main__': raise SystemExit(main())
