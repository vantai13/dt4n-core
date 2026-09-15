import json
from types import SimpleNamespace

import pytest
from bridge.collector import parse_qdisc_stats, qdisc_interval
from mininet import traffic
from rl import scenarios
from bridge.adapter import _wrap_properties


def test_invalid_qdisc_clears_stale_loss_in_merge_patch():
    wrapped = _wrap_properties({'traffic': {'qdiscValid': False, 'lossPct': None}})
    assert 'lossPct' in wrapped['traffic']['properties']
    assert wrapped['traffic']['properties']['lossPct'] is None


def test_parent_drops_are_not_counted_twice():
    stats = parse_qdisc_stats(json.dumps([
        {'kind': 'htb', 'handle': '5:', 'root': True, 'drops': 10, 'packets': 90},
        {'kind': 'netem', 'handle': '10:', 'parent': '5:1', 'drops': 10, 'packets': 90},
    ]))
    assert stats['drops'] == 10
    assert stats['packets'] == 90
    assert parse_qdisc_stats('Cannot find device') is None
    assert parse_qdisc_stats('[]') is None


def test_bidirectional_loss_uses_queue_packets_and_invalidates_resets():
    def row(drops, packets):
        return {'signature': [('netem', '10:', '5:1')], 'drops': drops, 'packets': packets}
    old = {'a': row(10, 100), 'b': row(0, 100)}
    new = {'a': row(30, 180), 'b': row(0, 200)}
    result = qdisc_interval(new, old)
    assert result['lossPct'] == 10.0  # 20 / (80 + 100 + 20)
    assert result['qdiscDropDelta'] == 20
    assert qdisc_interval({'a': None, 'b': new['b']}, old)['lossPct'] is None
    assert qdisc_interval(new, None)['qdiscReason'] == 'warmup'
    assert qdisc_interval(old, new)['qdiscReason'] == 'counter_reset'


@pytest.mark.parametrize('scenario,rate,udp', [('normal', '2M', False), ('flood', '50M', True)])
def test_profiles_cover_all_clients_and_both_servers(monkeypatch, scenario, rate, udp):
    hosts = {name: SimpleNamespace(name=name, IP=lambda ip=ip: ip)
             for name, ip in [('h1','10.0.0.1'),('h2','10.0.0.2'),('h3','10.0.0.3'),
                              ('srv1','10.0.0.4'),('srv2','10.0.0.5')]}
    net = SimpleNamespace(hosts=list(hosts.values()), get=hosts.__getitem__)
    commands = []
    monkeypatch.setattr(traffic, 'run_host_shell', lambda host, cmd: commands.append((host.name, cmd)))
    monkeypatch.setattr(traffic.time, 'sleep', lambda _: None)
    traffic.start_background_load(net, scenario=scenario, duration=10)
    clients = [(name, cmd) for name, cmd in commands if 'iperf -c' in cmd and name.startswith('h')]
    assert len(clients) == 3
    assert {name for name, _ in clients} == {'h1', 'h2', 'h3'}
    assert '10.0.0.5' in dict(clients)['h2']
    assert all(f'-b {rate}' in cmd and ('-u' in cmd) == udp for _, cmd in clients)
    assert any(name == 'srv1' and 'iperf -c 10.0.0.5' in cmd for name, cmd in commands)


def test_injection_does_not_use_interactive_host_shell(monkeypatch):
    commands = []
    hosts = {name: SimpleNamespace(name=name, IP=lambda: '10.0.0.4') for name in ['h1', 'srv1']}
    net = SimpleNamespace(get=hosts.__getitem__)
    monkeypatch.setattr(scenarios, 'run_host_shell', lambda host, cmd: commands.append((host.name, cmd)))
    monkeypatch.setattr(scenarios.time, 'sleep', lambda _: None)
    flood = scenarios.TrafficFlood('h1', 'srv1', 50)
    flood.apply(net)
    flood.revert(net)
    assert not flood._applied
    assert any('iperf -c' in cmd for _, cmd in commands)
    assert any('[i]perf' in cmd for _, cmd in commands)
