import os
import socket
import subprocess
import time
from pathlib import Path
root = Path(__file__).resolve().parents[1]
os.chdir(root)
env = dict(os.environ, PYTHONPATH=str(root), DT4N_NAMESPACE='org.dt4n.core')
with open('logs/ml_controller.log','w') as f:
    controller = subprocess.Popen(['/home/ubuntu/miniforge3/envs/sdn_net/bin/ryu-manager',
                                   'mininet.controller_static','--ofp-tcp-listen-port','6653'],
                                  env=env, stdout=f, stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            try:
                with socket.create_connection(('127.0.0.1',6653),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('Controller did not start')
        cmd = ['sudo','-n','env',f'PYTHONPATH={root}','DT4N_NAMESPACE=org.dt4n.core',
               '/usr/bin/python3','scripts/run_ml_preflight.py']
        with open('logs/ml_preflight_stdout.log','w') as log:
            result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        print('EXIT ml_preflight',result.returncode,flush=True)
        raise SystemExit(result.returncode)
    finally:
        controller.terminate()
        controller.wait()
