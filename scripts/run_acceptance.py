#!/usr/bin/env python3
"""Real network acceptance; run with system Python as root from repo root."""
import contextlib,json,time,threading,subprocess,os
from pathlib import Path
from types import SimpleNamespace
from mininet.env_runner import EnvRunner
from measurements.measure_latency import main as latency
from measurements.measure_command_latency import main as command
from measurements.measure_command_flow import main as flow
from bridge.verify import run_full_verification,check_accuracy
from mininet.run_sync import configure_file_logging

out=Path('results/report'); out.mkdir(parents=True,exist_ok=True)
def save(name,data):
 (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False))
def stage(name,func):
 print('START',name,flush=True)
 try:
  with open('logs/'+name+'.log','w',buffering=1) as f,contextlib.redirect_stdout(f): result=func()
  save(name+'.json',{'ok':True,'result':result})
 except Exception as e:
  import traceback
  traceback.print_exc(); save(name+'.json',{'ok':False,'error':repr(e)})
 print('DONE',name,flush=True)
configure_file_logging('logs/acceptance_runtime.log',append=False)
r=EnvRunner(policy_path='ditto/policy_core_lab.json',sync_period=1,clients=3,convergence_timeout=8,do_pingall=True,ping_every=20,reconcile_every=30,mininet_log_level='info')
try:
 r.start(); r.start_server_background(rate_mbps=2); time.sleep(3)
 if os.environ.get('DT4N_RESUME_ACCEPTANCE') != '1' or not (out/'latency_up.json').exists(): stage('latency_up',lambda:latency(r.net,n_trials=30,h='h1',s='s1',net_lock=r.net_lock))
 if os.environ.get('DT4N_RESUME_ACCEPTANCE') != '1' or not (out/'latency_command.json').exists(): stage('latency_command',lambda:command(r.net,n_trials=30,h='h1',s='s1',net_lock=r.net_lock))
 if os.environ.get('DT4N_RESUME_ACCEPTANCE') != '1' or not (out/'command_flow.json').exists(): stage('command_flow',lambda:flow(r.net,n_trials=30,h='h1',s='s1',net_lock=r.net_lock,settle=1,reflection_timeout=20,command_timeout=0,reset_log=False,report_path='logs/command_flow_measure.log'))
 stage('verification',lambda:run_full_verification(r.net,SimpleNamespace(long=False,duration=60,verify_interval=5,n_events=20,verify_link='h1-s1',output='docs/phase-2/verify_report.json'),net_lock=r.net_lock))
 def security():
  env=dict(os.environ,DT4N_LIVE_COMMAND_TESTS='1')
  p=subprocess.run(['.venv/bin/python','-m','pytest','test/test_command_security.py','-v','--junitxml=results/report/security_live.xml'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  print(p.stdout); return {'exit_code':p.returncode}
 stage('security_live',security)
 def soak():
  rows=[]; start=time.monotonic(); deadline=start+1800
  while True:
   rss=int(Path('/proc/self/status').read_text().split('VmRSS:')[1].split()[0])
   row={'elapsed_s':round(time.monotonic()-start,2),'rss_kib':rss,'accuracy':check_accuracy(r.net,net_lock=r.net_lock)}; rows.append(row)
   save('soak_progress.json',{'duration_target_s':1800,'complete':False,'samples':rows}); print(json.dumps(row),flush=True)
   remaining=deadline-time.monotonic()
   if remaining<=0: break
   time.sleep(min(60,remaining))
  result={'duration_s':round(time.monotonic()-start,2),'samples':rows,'rss_start_kib':rows[0]['rss_kib'],'rss_end_kib':rows[-1]['rss_kib'],'rss_max_kib':max(x['rss_kib'] for x in rows),'all_state_accuracy_100':all(x['accuracy']['accuracy_rate']==100 for x in rows)}
  save('soak_progress.json',dict(result,complete=True)); return result
 stage('soak_30min',soak)
finally:
 r.close()
print('ALL DONE',flush=True)
