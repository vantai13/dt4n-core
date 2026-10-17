#!/usr/bin/env python3
"""Render the live manifest and partial snapshot counts; never accept partial runs."""
import argparse
import datetime
import html
import json
import re
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.root
    contract=json.loads((root/'results/report/experiment_matrix.json').read_text())
    path=root/'results/report/ml_dataset_manifest.json'
    manifest=json.loads(path.read_text()) if path.exists() else {'runs':{}}
    rows=[];active=[];runtime_bad=[]
    for rid in contract['execution_order']:
        outcome=manifest['runs'].get(rid,{})
        partial=root/'data/phase5/raw'/f'{rid}.jsonl.partial'
        n=sum(1 for _ in partial.open()) if partial.exists() else outcome.get('checks',{}).get('n_snapshots','—')
        status=outcome.get('status','chưa chạy')
        log=root/'logs'/f'ml_gen_{rid}.log'
        if outcome.get('status')=='ok' and log.exists() and re.search(r'\b(?:ERROR|CRITICAL)\b|Traceback',log.read_text()):
            status='cần chạy lại: ERROR log';runtime_bad.append(rid)
        if partial.exists():status='đang thu';active.append(f'{rid}: {n} snapshot')
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (rid,status,n,outcome.get('checks',{}).get('max_separation','—')) )+'</tr>')
    title=f"Lesson 5.4: {manifest.get('n_runs_ok',0)}/18 run qua gate thu; {len(runtime_bad)} run có ERROR log; {manifest.get('n_runs_failed',0)} run hỏng"
    body='<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>'+title+'</title><style>body{font:16px system-ui;margin:32px}td,th{padding:8px;border-bottom:1px solid #ddd}table{border-collapse:collapse}</style><h1>'+title+'</h1><p>'+str(datetime.datetime.now(datetime.timezone.utc))+'</p><p>Complete: '+str(manifest.get('complete',False))+'</p><table><tr><th>Run</th><th>Trạng thái</th><th>Snapshot</th><th>Separation</th></tr>'+''.join(rows)+'</table>'
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(body)
    print(title+' | '+'; '.join(active),flush=True)

if __name__=='__main__':main()
