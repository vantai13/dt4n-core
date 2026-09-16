#!/usr/bin/env python3
"""Exploratory post-freeze IF tail and hybrid diagnostics."""
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from ml.campaign import ROOT, canonical_json, sha256_bytes, sha256_file

REPORT=ROOT/'results/report'; OUT=REPORT/'phase6_iforest_posthoc_diag.json'
ENV=REPORT/'phase6_envelope.json'; IF=REPORT/'phase6_iforest.json'
ENV_TICKS=REPORT/'phase6_envelope_ticks.csv'; IF_TICKS=REPORT/'phase6_iforest_ticks.csv'
LEDGER3=REPORT/'phase6_hypothesis_ledger_3.json'; HASH_FIELD='content_sha256'
def content_hash(x): return sha256_bytes(canonical_json(x).encode())
def _read(p): return json.loads(p.read_text())


def sealed_inputs():
    env,ifo,l3=_read(ENV),_read(IF),_read(LEDGER3)
    for doc,field,name in ((env,'content_sha256','env'),(ifo,'content_sha256','if'),(l3,'ledger_content_sha256','ledger3')):
        if content_hash(doc['content'])!=doc[field]: raise ValueError(name+' bi sua')
    if env['content']['ticks_csv_sha256']!=sha256_file(ENV_TICKS): raise ValueError('env ticks bi sua')
    if ifo['content']['ticks_csv_sha256']!=sha256_file(IF_TICKS): raise ValueError('if ticks bi sua')
    return env,ifo,l3


def common_frame():
    left=pd.read_csv(ENV_TICKS)[['run_id','tick','y','k','excess','judgeable71','alarm_primary_k','alarm_secondary_excess']]
    right=pd.read_csv(IF_TICKS)[['run_id','tick','score','judgeable','alarm_q01']]
    merged=left.merge(right,on=['run_id','tick'],validate='one_to_one')
    merged['neg_score']=-merged['score']; return merged


def statistic_table(merged,n_pos,n_neg):
    judged=merged[merged.judgeable71 & merged.judgeable]
    out={}
    for name,series in (('envelope_excess',judged.excess),('envelope_count_k',judged.k.astype(float)),('iforest_neg_score',judged.neg_score)):
        rows=[{'threshold':float(t),'recall':float(((judged.y==1)&(series>t)).sum()/n_pos),
               'fpr':float(((judged.y==0)&(series>t)).sum()/n_neg)} for t in np.unique(series)]
        best=max(rows,key=lambda x:x['recall']-x['fpr'])
        benign=float(series[judged.y==0].max()); fault=float(series[judged.y==1].max())
        out[name]={'auc':float(roc_auc_score(judged.y,series)),'benign_extreme':benign,
          'fault_extreme':fault,'fault_tail_exceeds_benign_tail':fault>benign,
          'oracle_best_by_youden_j':best,'youden_j':round(best['recall']-best['fpr'],4)}
    return {'n_rows_judgeable_by_both':len(judged),'statistics':out}


def operation_table(merged,n_pos,n_neg):
    common=merged.judgeable71 & merged.judgeable
    alarms={'envelope_count_only':merged.alarm_primary_k.astype(bool)&common,
      'envelope_excess_only':merged.alarm_secondary_excess.astype(bool)&common,
      'iforest_only':merged.alarm_q01.astype(bool)&common}
    alarms['excess_OR_iforest']=alarms['envelope_excess_only']|alarms['iforest_only']
    alarms['excess_AND_iforest']=alarms['envelope_excess_only']&alarms['iforest_only']
    out={}
    for name,a in alarms.items():
        tp=int((a&merged.y.eq(1)).sum());fp=int((a&merged.y.eq(0)).sum())
        out[name]={'recall':tp/n_pos,'fpr':fp/n_neg,'tp':tp,'fp':fp}
    out['iforest_unique_true_positives']=int((alarms['iforest_only']&~alarms['envelope_excess_only']&merged.y.eq(1)).sum())
    out['added_false_positives']=int((alarms['iforest_only']&~alarms['envelope_excess_only']&merged.y.eq(0)).sum())
    return out


def current_content():
    env,ifo,l3=sealed_inputs(); merged=common_frame(); n_pos=int(merged.y.sum());n_neg=len(merged)-n_pos
    threshold=ifo['content']['configs']['256']['per_seed']['0']['by_q']['0.01']['threshold']
    judged=merged[merged.judgeable71&merged.judgeable]
    fault_min=float(judged.loc[judged.y.eq(1),'score'].min())
    return {'diagnostic_id':'DT4N-P6-IF-POSTHOC-v1','status':'EXPLORATORY POST-FREEZE',
      'uses_test_labels':True,'authorises_no_change_to':['detector','threshold','hypothesis','column set'],
      'bound_to':{'ledger_3_content_sha256':l3['ledger_content_sha256'],'iforest_test_content_sha256':ifo['content_sha256']},
      'common_comparison':statistic_table(merged,n_pos,n_neg),
      'registered_if_threshold':{'threshold':threshold,'fault_score_min':fault_min,
        'threshold_below_every_fault_score':threshold<fault_min,'gap':fault_min-threshold},
      'operating_point_and_hybrid':operation_table(merged,n_pos,n_neg)}


def main():
    if OUT.exists(): print('[diag-if] exists; refusing overwrite');return 1
    content=current_content();doc={'written_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'content':content,HASH_FIELD:content_hash(content)}
    with OUT.open('x') as f:json.dump(doc,f,indent=2);f.write('\n')
    for n,r in content['common_comparison']['statistics'].items():print('[diag]',n,'AUC=%.4f J=%.3f'%(r['auc'],r['youden_j']))
    op=content['operating_point_and_hybrid'];print('[diag] IF-only TP=',op['iforest_unique_true_positives'],'added FP=',op['added_false_positives'])
    print('[diag] SHA:',doc[HASH_FIELD]);return 0


if __name__=='__main__':raise SystemExit(main())
