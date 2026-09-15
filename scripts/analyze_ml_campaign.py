#!/usr/bin/env python3
"""Re-audit accepted campaign observations using actual event labels.

Usage: python -m scripts.analyze_ml_campaign --root /path/to/collection
Pilot reports are preserved. Raw data are required, not replaced by hashes.
"""
import argparse
import json
import re
from pathlib import Path
import pandas as pd
from ml import campaign as C
from ml.flatten import load_jsonl
from ml.audit import audit_features, kept_features
from ml.missing import apply_policy, assert_no_fabricated_zero_in_loss, missing_reasons, rate_fabrication_audit


def analyze(root):
    contract=C.load_contract(root/'results/report/experiment_matrix.json')
    integrity=C.check_contract_integrity(contract)
    manifest=json.loads((root/'results/report/ml_dataset_manifest.json').read_text())
    if not manifest['complete'] or manifest['n_runs_ok']!=18:
        raise ValueError('Audit requires all 18 accepted runs')
    frames=[];sources={};logs={};quality=[];sidecar_windows={};non_warmup_invalid=[]
    for record in contract['runs']:
        rid=record['run_id'];paths=C.run_paths(rid,root)
        side=json.loads(paths['meta'].read_text())
        if side['record']!=record or side['design_content_sha256']!=integrity['stored'] or side['checks']['passed'] is not True or C.sha256_file(paths['final'])!=side['sha256'] or manifest['runs'][rid]['sha256']!=side['sha256']:
            raise ValueError('Raw/sidecar/manifest mismatch: '+rid)
        df=load_jsonl(paths['final'])
        if set(df.run_id)!={rid} or set(df.design_content_sha256)!={integrity['stored']} or set(df.git_hash)!={side['collection_provenance']['git_hash']} or df.source_dirty.any():
            raise ValueError('Embedded collection identity/provenance mismatch: '+rid)
        df['is_fault']=C.labels_from_events(len(df),side['events']);frames.append(df)
        sources[rid]={'sha256':side['sha256'],'n_snapshots':len(df),'collection_provenance':side['collection_provenance']}
        lines=paths['log'].read_text().splitlines()
        logs[rid]=C.runtime_error_count('\n'.join(lines))
        sidecar_windows[rid]={k:v for k,v in side['checks'].items() if 'invalid_fraction_' in k}
        measured=df.loc[df.tick>=contract['constants']['warmup_ticks']]
        for col in [c for c in measured if c.endswith('.traffic.qdiscValid')]:
            for _,row in measured.loc[~measured[col].eq(True)].iterrows():
                non_warmup_invalid.append({'run_id':rid,'tick':int(row.tick),'link':col.split('.')[0],'reason':row[col.replace('qdiscValid','qdiscReason')],'is_fault':int(row.is_fault)})
        for window,group in measured.groupby(measured.is_fault.map({0:'background',1:'fault'})):
            for flag in ('qdiscValid','rateValid'):
                cols=[c for c in df if c.endswith('.traffic.'+flag)]
                valid=group[cols].eq(True);quality.append({'run_id':rid,'window':window,'flag':flag,'invalid':int((~valid).to_numpy().sum()),'total':int(valid.size)})
    df=pd.concat(frames,ignore_index=True,sort=False)
    assert_no_fabricated_zero_in_loss(df)
    clean,policy=apply_policy(df,warmup_ticks=contract['constants']['warmup_ticks'])
    audit=audit_features(clean,fault_col='is_fault')
    out=root/'results/report';out.mkdir(parents=True,exist_ok=True)
    audit.to_csv(out/'campaign_feature_audit.csv',index=False)
    states={c:int(clean[c].nunique()) for c in clean if c.endswith('.status.state_up')}
    summary={'n_kept_auc_dist_gt_0_5':int(((audit.quyet_dinh=='GIU') & (audit.auc_dist>.5)).sum()),'dataset':'18 accepted campaign runs; point-wise event labels; warmup removed', 'n_raw_snapshots':len(df),'n_snapshots':len(clean),'n_columns':len(clean.columns),'by_decision':{k:int(v) for k,v in audit.quyet_dinh.value_counts().items()},'kept':kept_features(audit),'state_up_nunique':states,'sources':sources,'warning':'Descriptive in-sample audit; repeated ticks/links are dependent; no held-out model score.'}
    summary['pilot_global_auc_gate_passed']=summary['n_kept_auc_dist_gt_0_5']>=5
    summary['global_auc_assessment']='Pilot global AUC threshold is not met on point-wise mixed faults. Per-run intervention signal gates pass; no detector performance is claimed.'
    loss=[c for c in df if c.endswith('.traffic.lossPct')]
    aggregated_quality=pd.DataFrame(quality).groupby(['window','flag'])[['invalid','total']].sum().reset_index()
    aggregated_quality['fraction_invalid']=aggregated_quality.invalid/aggregated_quality.total
    missing={'non_warmup_invalid_events':non_warmup_invalid,'window_rule':'Warmup excluded from quality fractions; background includes pre-inject and post-revert. Sidecar baseline/fault fractions are also retained.','by_sidecar_baseline_fault':sidecar_windows,'aggregate_by_actual_event_window':aggregated_quality.to_dict(orient='records'),'n_raw_snapshots':len(df),'total_pct_loss_cells_missing':float(100*df[loss].isna().to_numpy().sum()/df[loss].size),'policy_applied':policy,'rate_fabrication_channel_b':rate_fabrication_audit(df),'by_reason':missing_reasons(df).to_dict(orient='records'),'by_actual_event_window':quality,'interpretation':'Compare fault/background rates after accounting for warmup and counter reset reasons. Association alone does not prove MNAR.'}
    gates={'complete':manifest['complete'],'18_runs_ok':manifest['n_runs_ok']==18,'no_runtime_error_in_run_logs':not any(logs.values()),'base_rate_10_to_40pct':.1<=manifest['base_rate']['base_rate_measured']<=.4,'all_fault_signals_ge_1':all(manifest['runs'][r['run_id']]['checks']['max_separation']>=1 for r in contract['runs'] if r['fault']),'normal_links_stay_up':all(manifest['runs'][r['run_id']]['checks']['no_unexpected_down'] for r in contract['runs'] if not r['fault']),'source_clean':all(not v['collection_provenance']['source_dirty'] for v in sources.values())}
    plot_campaign(out,contract,manifest,clean,audit,quality)
    receipt={'gates':gates,'passed':all(gates.values()),'run_log_errors':logs,'base_rate':manifest['base_rate'],'label_convention':C.LABEL_CONVENTION,'contract_integrity':integrity,'n_raw_snapshots':len(df),'n_after_warmup':len(clean),'state_up_variable_columns':[c for c,n in states.items() if n>1]}
    for name,data in [('campaign_feature_audit_summary.json',summary),('campaign_missing_analysis.json',missing),('campaign_acceptance.json',receipt)]:C.atomic_json(out/name,data)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if receipt['passed'] else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=C.ROOT)
    return analyze(parser.parse_args().root.resolve())



def plot_campaign(out,contract,manifest,df,audit,quality):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ids=contract['execution_order']
    fig,axes=plt.subplots(1,2,figsize=(15,7),gridspec_kw={'width_ratios':[2,1]})
    labels=ids
    axes[0].barh(labels,[manifest['runs'][r]['checks']['n_snapshots'] for r in ids],color=['#c84b45' if '-load' not in r and r.startswith('F-') else '#3579ad' for r in ids])
    axes[0].axvline(60,color='gray',ls='--');axes[0].set_xlabel('Snapshots accepted');axes[0].invert_yaxis();axes[0].tick_params(axis='y',labelsize=8)
    fault=[r for r in ids if r.startswith('F-')]
    axes[1].barh(fault,[manifest['runs'][r]['checks']['max_separation'] for r in fault],color='#c84b45')
    axes[1].axvline(1,color='gray',ls='--');axes[1].set_xscale('log');axes[1].set_xlabel('Measured signal separation (log scale)')
    axes[1].tick_params(axis='y',labelsize=7)
    fig.suptitle('Lesson 5.4: 18 live runs | test fault prevalence '+str(manifest['base_rate']['base_rate_measured']))
    fig.tight_layout();fig.savefig(out/'campaign_results.png',dpi=140);plt.close(fig)
    top=audit[(audit.kind=='numeric') & audit.auc_dist.notna()].nlargest(4,'auc_dist').feature.tolist()
    fig,axes=plt.subplots(1,4,figsize=(16,4));mask=df.is_fault.astype(bool)
    for ax,col in zip(axes,top):
        values=pd.to_numeric(df[col],errors='coerce')
        import numpy as np
        bins=np.histogram_bin_edges(values.dropna(),bins=20)
        for fault,label in [(False,'background'),(True,'fault')]:ax.hist(values[mask==fault].dropna(),bins=bins,alpha=.6,label=label)
        ax.set_title(col,fontsize=8);ax.legend(fontsize=8)
    fig.suptitle('Campaign feature distributions: event labels; warmup removed; descriptive only')
    fig.tight_layout();fig.savefig(out/'campaign_feature_distributions.png',dpi=140);plt.close(fig)

if __name__=='__main__':raise SystemExit(main())
