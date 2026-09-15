import subprocess,os,time,socket
from pathlib import Path
root=Path.cwd(); env=dict(os.environ,PYTHONPATH=str(root))
commands=[('phase1_config5',['-m','mininet.run_phase1','--scenario','idle','--clients','5','--bw-bottleneck','2','--delay','5ms','--duration','3','--log-path','logs/snapshots_config5.jsonl','--pretty-log-path','logs/phase1_config5.log'],'results/report/topology_config5.json'),('acceptance',['scripts/run_acceptance.py'],'ditto/topology_spec.json')]
for name,args,spec in (commands[-1:] if os.environ.get("DT4N_RESUME_ACCEPTANCE")=="1" else commands):
 cenv=dict(env,DT4N_TOPOLOGY_SPEC=spec)
 with open('logs/controller_'+name+'.log','w') as f:
  c=subprocess.Popen(['/home/ubuntu/miniforge3/envs/sdn_net/bin/ryu-manager','mininet.controller_static','--ofp-tcp-listen-port','6653'],env=cenv,stdout=f,stderr=subprocess.STDOUT)
  try:
   for _ in range(50):
    try:
     with socket.create_connection(('127.0.0.1',6653),timeout=.2): break
    except OSError: time.sleep(.2)
   else: raise RuntimeError('controller did not start')
   with open('logs/'+name+'_stdout.log','w') as log:
    cmd=['sudo','-n','env','PYTHONPATH='+str(root),'DT4N_NAMESPACE=org.dt4n.core','DT4N_RESUME_ACCEPTANCE='+os.environ.get('DT4N_RESUME_ACCEPTANCE','0'),'/usr/bin/python3']+args
    print('RUN',name,flush=True); p=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT); print('EXIT',name,p.returncode,flush=True)
    if p.returncode: raise RuntimeError(name+' failed')
  finally:
   c.terminate(); c.wait()
