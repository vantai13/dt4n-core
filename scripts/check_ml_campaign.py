"""Run the three preparation checks; never launch a live campaign."""
import json
import subprocess
from pathlib import Path
from ml.campaign import load_contract, check_contract_integrity, traffic_plan
from mininet.traffic import schedule_segments

ROOT=Path(__file__).resolve().parents[1]


def main():
    contract=load_contract()
    integrity=check_contract_integrity(contract)
    plans={r['run_id']:traffic_plan(r,contract['constants']) for r in contract['runs']}
    sample=next(p for p in plans.values() if p['mode']=='varying')
    elapsed=-contract['constants']['pre_roll_sec']
    timeline=[]
    for rate,duration in schedule_segments(sample['schedule_with_preroll'],sample['iperf_seconds']):
        timeline.append({'start_t_rel':elapsed,'end_t_rel':elapsed+duration,'rate_mbps':rate})
        elapsed+=duration
    probe="""import sys
from ml.campaign import load_contract,contract_hash,traffic_plan,scenario_from_record
c=load_contract()
assert contract_hash(c)==c['design_content_sha256']
for r in c['runs']:
    traffic_plan(r,c['constants']);scenario_from_record(r)
assert not any(m in sys.modules for m in ('numpy','pandas','matplotlib'))
print('System Python: 18 plans/scenarios without numpy/pandas/matplotlib')
"""
    system=subprocess.run(['/usr/bin/python3','-c',probe],cwd=ROOT,capture_output=True,text=True,check=True)
    report={'scope':'Lesson5.4 preparation; no live network launched','integrity':integrity,
        'n_runs':contract['n_runs'],'plans':plans,'example_varying_timeline':timeline,
        'traffic_end_t_rel':elapsed,'covers_recording':elapsed>60,
        'system_python_dependency_check':system.stdout.strip(),
        'raw_policy':'JSONL/partials ignored; sidecars and manifest to be committed after collection'}
    out=ROOT/'results/report/phase54_prechecks.json'
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('Integrity match:',integrity['match'])
    print('Plans:',len(plans),'| iperf duration: 75s | end t_rel:',elapsed)
    print(system.stdout.strip())
    print(out)


if __name__=='__main__':
    main()
