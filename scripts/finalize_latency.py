import json,re
from pathlib import Path
for name in ['latency_up','latency_command']:
 p=Path('results/report')/(name+'.json')
 if not p.exists():continue
 d=json.loads(p.read_text());s=d.get('result')
 if not isinstance(s,dict):continue
 raw=(Path('logs')/(name+'.log')).read_text()
 samples=[int(v) for v in re.findall(r'^Trial\s+\d+:\s+(\d+)\s+ms',raw,re.M)]
 s['trials_requested']=30;s['timeouts']=len(re.findall(r'^Trial\s+\d+:\s+TIMEOUT',raw,re.M));s['samples_ms_rounded']=samples
 s['sample_precision_note']='Per-trial values transcribed from terminal rounded to ms; p50/p95 use full precision collected during run.'
 t=p.with_suffix('.json.tmp');t.write_text(json.dumps(d,indent=2,ensure_ascii=False));t.replace(p)
