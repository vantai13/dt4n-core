#!/usr/bin/env python3
"""Collect new, separately named live evidence before ML; never overwrite v1."""
import contextlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import requests
from bridge.collector import Collector
from bridge.ditto_common import DITTO_BASE_URL, DITTO_AUTH, make_thing_id_link, NAMESPACE
from bridge import command_agent
from measurements.measure_latency import main as latency, poll_until_state
from measurements.measure_command_latency import main as command_latency
from mininet.env_runner import EnvRunner
from mininet.run_sync import configure_file_logging
from mininet import traffic
from rl.scenarios import TrafficFlood

out = Path('results/report')
configure_file_logging('logs/ml_preflight_runtime.log')
events = []
original_parse = command_agent.parse_message_event

def capture(*args, **kwargs):
    parsed = original_parse(*args, **kwargs)
    if parsed:
        events.append({k: parsed.get(k) for k in ['subject','correlation_id','correlation_source','raw']})
    return parsed
command_agent.parse_message_event = capture

def save(name, data):
    (out / name).write_text(json.dumps(data, indent=2, ensure_ascii=False))

r = EnvRunner(policy_path='ditto/policy_core_lab.json', sync_period=1,
              clients=3, do_pingall=True, hard_every=0, mininet_log_level='info')
try:
    r.start()
    for scenario in ['normal', 'flood']:
        print('START dataset', scenario, flush=True)
        r.start_profile_background(scenario=scenario, duration=75,
                                   normal_rate='2M', rate='50M', server_bg_rate=2)
        time.sleep(3)
        col = Collector(r.net, interval=1, net_lock=r.net_lock,
                        log_path=f'logs/ml_{scenario}_v2.jsonl',
                        pretty_log_path=f'logs/ml_{scenario}_v2.log', overwrite=True)
        col.run(duration=60)
        if scenario == 'flood':
            raw = {}
            for node, iface in [('h1','h1-eth0'), ('s1','s1-eth1')]:
                raw[iface] = traffic.run_host_shell(r.net.get(node), f'tc -s qdisc show dev {iface}')
            save('ml_qdisc_flood_raw.json', raw)
        reports = {h.name: traffic.run_host_shell(h, f'cat /tmp/iperf_cli_{h.name}.log')
                   for h in r.net.hosts if h.name.startswith('h')}
        save(f'ml_{scenario}_iperf.json', reports)
        traffic.stop_all_iperf(*r.net.hosts)
        print('DONE dataset', scenario, flush=True)
    print('START injection while sync active', flush=True)
    r.start_profile_background(scenario='normal', duration=45)
    fault = TrafficFlood('h1', 'srv1', 50)
    try:
        with r.net_lock:
            fault.apply(r.net)
        Collector(r.net, interval=1, net_lock=r.net_lock,
                  log_path='logs/ml_injection_v2.jsonl', pretty_log_path=None,
                  overwrite=True).run(duration=30)
    finally:
        with r.net_lock:
            fault.revert(r.net)
        traffic.stop_all_iperf(*r.net.hosts)
    r.start_server_background(rate_mbps=2, duration=400)
    time.sleep(3)
    for name, func in [('latency_up_randomized',latency),('latency_command_randomized',command_latency)]:
        print('START', name, flush=True)
        with open(f'logs/{name}.log','w') as f, contextlib.redirect_stdout(f):
            result = func(r.net, n_trials=30, net_lock=r.net_lock, phase_period=1,
                          seed=20260915)
        save(name+'.json', {'ok':result is not None and result['timeouts']==0,
                           'result':result,
                           'load_profile':'srv1->srv2 UDP 2M; clients idle',
                           'collector_version':'qdisc_v2'})
        print('DONE', name, flush=True)
    print('START timeout=3 probe', flush=True)
    probes = []
    target = make_thing_id_link('h1','s1')
    for include_payload_cid in [False, True]:
        with r.net_lock:
            r.net.configLinkStatus('h1','s1','up')
        assert poll_until_state(target,'up',timeout=8) is not None
        cid = str(uuid.uuid4()); body = {'target':target}
        if include_payload_cid: body['clientCorrelationId'] = cid
        start_event = len(events); started = time.monotonic()
        resp = requests.post(f'{DITTO_BASE_URL}/things/{NAMESPACE}:controller/inbox/messages/disableLink?timeout=3',
                             json=body, headers={'correlation-id':cid}, auth=DITTO_AUTH, timeout=10)
        reflected = poll_until_state(target,'down',timeout=8)
        probes.append({'payload_correlation_id':include_payload_cid,'correlation_id':cid,
                       'http_status':resp.status_code,'http_body':resp.text,
                       'http_elapsed_s':round(time.monotonic()-started,3),
                       'reflected_down':reflected is not None,'received_sse':events[start_event:]})
    save('command_ack_timeout3.json', probes)
    with r.net_lock:
        r.net.configLinkStatus('h1','s1','up')
    assert poll_until_state(target,'up',timeout=8) is not None
    env = dict(os.environ, DT4N_LIVE_COMMAND_TESTS='1')
    with open('logs/ml_security_live.log','w') as f:
        test = subprocess.run(['.venv/bin/python','-m','pytest','test/test_command_security.py','-v',
                               '--junitxml=results/report/ml_security_live.xml'], env=env,
                              stdout=f, stderr=subprocess.STDOUT)
    save('ml_security_live.json', {'exit_code':test.returncode})
    if test.returncode: raise RuntimeError('live security tests failed')
    with r.net_lock:
        r.net.configLinkStatus('h1','s1','up')
    assert poll_until_state(target,'up',timeout=8) is not None
    save('ml_preflight_completed.json', {'ok':True,'namespace':NAMESPACE,'period_s':1,
                                        'normal_rate_per_client':'2M TCP','flood_rate_per_client':'50M UDP'})
finally:
    r.close()
print('ALL DONE',flush=True)
