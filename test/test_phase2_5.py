#!/usr/bin/env python3
"""Pure-logic tests for Phase 2.5 reconciliation and verification helpers."""

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ensure_requests_module():
    try:
        import requests  # noqa: F401
        return
    except ImportError:
        pass

    class Timeout(Exception):
        pass

    class ConnectionError(Exception):
        pass

    class RequestException(Exception):
        pass

    fake_requests = types.ModuleType('requests')
    fake_requests.exceptions = types.SimpleNamespace(
        Timeout=Timeout,
        ConnectionError=ConnectionError,
        RequestException=RequestException,
    )
    fake_requests.Session = lambda: types.SimpleNamespace(auth=None)
    sys.modules['requests'] = fake_requests


ensure_requests_module()

from bridge.sync_agent import build_full_changes, should_reconcile  # noqa: E402
from bridge.differ import diff_features  # noqa: E402
from bridge.adapter import collector_to_things  # noqa: E402
from bridge.health import compute_health_state  # noqa: E402
from bridge.verify import values_match  # noqa: E402
from bridge.bootstrap import entities_from_net, entities_from_spec  # noqa: E402
import bridge.command_agent as command_agent_mod  # noqa: E402
from bridge.command_agent import handle_command, parse_message_event  # noqa: E402
import bridge.collector as collector_mod  # noqa: E402
from bridge.collector import Collector, run_host_namespace_command  # noqa: E402
from bridge.ditto_common import NAMESPACE, POLICY_ID, make_thing_id_path  # noqa: E402


passed = failed = 0


def check(name, cond):
    global passed, failed
    print(('  PASS ' if cond else '  FAIL ') + name)
    if cond:
        passed += 1
    else:
        failed += 1


print('== TEST 1: reconciliation cadence ==')
check('cycle 0 reconcile khi every=30', should_reconcile(0, 30) is True)
check('cycle 1 không reconcile', should_reconcile(1, 30) is False)
check('cycle 30 reconcile', should_reconcile(30, 30) is True)
check('every=0 tắt reconcile', should_reconcile(30, 0) is False)

print('\n== TEST 2: full changes gửi toàn bộ features ==')
things = {
    'org.dt4n:host-h1': {
        'features': {
            'status': {'properties': {'state': 'up'}},
            'traffic': {'properties': {'rxBytes': 10, 'txBytes': 20}},
        },
    },
    'org.dt4n:empty': {'features': {}},
}
full = build_full_changes(things)
check('chỉ Thing có features được gửi', set(full) == {'org.dt4n:host-h1'})
check('status được giữ nguyên', full['org.dt4n:host-h1']['features']['status']['properties']['state'] == 'up')
check('traffic được giữ nguyên', full['org.dt4n:host-h1']['features']['traffic']['properties']['txBytes'] == 20)

print('\n== TEST 3: values_match tolerance ==')
check('chuỗi khớp tuyệt đối', values_match('up', 'up') is True)
check('chuỗi lệch là fail', values_match('up', 'down') is False)
check('bool không bị True == 1 đánh lừa', values_match(True, 1) is False)
check('float lệch nhỏ tuyệt đối vẫn pass', values_match(100.0, 100.4, tol_abs=1.0) is True)
check('float lệch trong 5% vẫn pass', values_match(1000.0, 1040.0, tol_pct=5.0, tol_abs=1.0) is True)
check('float lệch quá tolerance fail', values_match(1000.0, 1100.0, tol_pct=5.0, tol_abs=1.0) is False)
check('ground truth 0 dùng tolerance tuyệt đối', values_match(0.0, 0.5, tol_abs=1.0) is True)

print('\n== TEST 4: bootstrap sinh controller Thing ==')
spec_entities = entities_from_spec(str(ROOT / 'ditto/topology_spec.json'))
controllers = [e for e in spec_entities if e.get('kind') == 'controller']
paths = [e for e in spec_entities if e.get('kind') == 'path']
check('entities_from_spec có đúng 1 controller', len(controllers) == 1)
if controllers:
    controller = controllers[0]
    check('controller thingId đúng namespace',
          controller['thing_id'] == '%s:controller' % NAMESPACE)
    check('controller dùng default policy',
          controller['body'].get('policyId') == POLICY_ID)
    check('controller type là command-sink',
          controller['body'].get('attributes', {}).get('type') == 'controller'
          and controller['body'].get('attributes', {}).get('role') == 'command-sink')
check('entities_from_spec có path h1->srv1',
      any(e['thing_id'] == '%s:path-h1-srv1' % NAMESPACE for e in paths))
check('path Thing là type=path, không phải link',
      paths and paths[0]['body'].get('attributes', {}).get('type') == 'path')
check('make_thing_id_path không sort hai đầu',
      make_thing_id_path('h1', 'srv1') != make_thing_id_path('srv1', 'h1'))


class _FakeNode:
    def __init__(self, name, ip='10.0.0.1'):
        self.name = name
        self._ip = ip

    def IP(self):
        return self._ip


class _FakeIntf:
    def __init__(self, node, name=None):
        self.node = node
        self.name = name or '%s-eth0' % node.name


class _FakeLink:
    def __init__(self, a, b):
        self.intf1 = _FakeIntf(a, '%s-eth0' % a.name)
        self.intf2 = _FakeIntf(b, '%s-eth0' % b.name)


host = _FakeNode('h1')
switch = _FakeNode('s1')
fake_net = types.SimpleNamespace(
    hosts=[host],
    switches=[switch],
    links=[_FakeLink(host, switch)],
)
net_entities = entities_from_net(fake_net)
check('entities_from_net có đúng 1 controller',
      len([e for e in net_entities if e.get('kind') == 'controller']) == 1)
check('entities_from_net có path probe',
      len([e for e in net_entities if e.get('kind') == 'path']) == 1)

print('\n== TEST 4b: adapter path + tSource ==')
snapshot = {
    'timestamp': 'unused',
    't_source': 1000.1234,
    'things': {
        'host-h1': {
            'attributes': {'type': 'host', 'role': 'client'},
            'features': {'status': {'state': 'up'}},
        },
        'path-h1-srv1': {
            'attributes': {'type': 'path', 'src': 'h1', 'dst': 'srv1'},
            'features': {'quality': {'latency_ms': 1.2, 'packetLoss_pct': 0.0}},
            't_source': 1001.5678,
        },
    },
}
things = collector_to_things(snapshot)
host_tid = '%s:host-h1' % NAMESPACE
path_tid = '%s:path-h1-srv1' % NAMESPACE
check('adapter gắn meta.tSource cho host từ snapshot fallback',
      things[host_tid]['features']['meta']['properties']['tSource'] == 1000.1234)
check('adapter không vứt path Thing nữa',
      path_tid in things)
check('adapter dùng tSource riêng của path',
      things[path_tid]['features']['meta']['properties']['tSource'] == 1001.5678)
check('adapter giữ quality của path',
      things[path_tid]['features']['quality']['properties']['latency_ms'] == 1.2)

print('\n== TEST 4c: meta không giết delta sync ==')
prev_features = {
    'status': {'properties': {'state': 'up'}},
    'meta': {'properties': {'tSource': 100.0}},
}
now_only_meta = {
    'status': {'properties': {'state': 'up'}},
    'meta': {'properties': {'tSource': 101.0}},
}
check('chỉ meta đổi -> không sinh delta',
      diff_features(now_only_meta, prev_features) == {})
now_real_change = {
    'status': {'properties': {'state': 'down'}},
    'meta': {'properties': {'tSource': 101.0}},
}
delta = diff_features(now_real_change, prev_features)
check('status đổi -> có delta status',
      delta.get('status', {}).get('properties', {}).get('state') == 'down')
check('meta đi kèm delta thật',
      delta.get('meta', {}).get('properties', {}).get('tSource') == 101.0)

print('\n== TEST 4d: link health theo utilization ==')
check('link up không traffic -> ok',
      compute_health_state('link', {
          'status': {'state': 'up'},
          'capacity': {'bwMbps': 5},
      }) == 'ok')
check('link util 80% -> warning',
      compute_health_state('link', {
          'status': {'state': 'up'},
          'capacity': {'bwMbps': 5},
          'traffic': {'rxRate': 0, 'txRate': 4_000_000 / 8},
      }) == 'warning')
check('link util 95% -> critical',
      compute_health_state('link', {
          'status': {'state': 'up'},
          'capacity': {'bwMbps': 5},
          'traffic': {'rxRate': 4_750_000 / 8, 'txRate': 0},
      }) == 'critical')

print('\n== TEST 5: command correlation debug fallback ==')
parsed = parse_message_event(
    '{"target":"org.dt4n:link-h1-s1","clientCorrelationId":"cid-ui-1"}',
    event_name='disableLink',
)
check('Command Agent lấy correlation từ payload UI',
      parsed.get('correlation_id') == 'cid-ui-1')
check('Command Agent ghi rõ fallback correlation từ payload',
      parsed.get('correlation_source') == 'payload:clientCorrelationId')
check('subject lấy từ SSE event_name',
      parsed.get('subject') == 'disableLink')
parsed_header = parse_message_event(
    '{"headers":{"correlation-id":"cid-header"},"path":"/inbox/messages/disableLink",'
    '"value":{"target":"org.dt4n:link-h1-s1","clientCorrelationId":"cid-body"}}',
    event_name='disableLink',
)
check('Command Agent ưu tiên correlation-id trong headers',
      parsed_header.get('correlation_id') == 'cid-header')
check('Command Agent ghi rõ correlation lấy từ headers',
      parsed_header.get('correlation_source') == 'headers:correlation-id')

print('\n== TEST 6: command SSE raw reader ==')


class _FakeSseResponse:
    encoding = 'utf-8'

    def __init__(self, chunks):
        self.chunks = chunks

    def iter_content(self, chunk_size=1, decode_unicode=True):
        return iter(self.chunks)


sse_lines = list(command_agent_mod._iter_sse_lines(_FakeSseResponse([
    b'event: disableLink\r\n',
    b'data: {"target":"org.dt4n:link-h1-s1"}\r\n\r\n',
])))
check('SSE reader tự tách dòng CRLF và dòng trống kết event',
      sse_lines == [
          'event: disableLink',
          'data: {"target":"org.dt4n:link-h1-s1"}',
          '',
      ])
unicode_event = 'data: {"note":"đã nhận"}\n\n'.encode('utf-8')
split_at = unicode_event.index('đ'.encode('utf-8')) + 1
unicode_lines = list(command_agent_mod._iter_sse_lines(_FakeSseResponse([
    unicode_event[:split_at],
    unicode_event[split_at:],
])))
check('SSE reader giữ đúng UTF-8 khi chunk cắt giữa ký tự',
      unicode_lines == ['data: {"note":"đã nhận"}', ''])

print('\n== TEST 7: enableSwitch chỉ OK khi controller connected ==')


class _FakeController:
    protocol = 'tcp'
    port = 6653

    def IP(self):
        return '127.0.0.1'


class _FakeCommandSwitch(_FakeNode):
    def __init__(self, name, connected_after=1):
        super().__init__(name)
        self.connected_after = connected_after
        self.connected_checks = 0
        self.commands = []
        self.started = False

    def start(self, controllers):
        self.started = True
        self.controllers = controllers

    def connected(self):
        self.connected_checks += 1
        if self.connected_after is None:
            return False
        return self.connected_checks > self.connected_after

    def cmd(self, command):
        self.commands.append(command)
        if command.startswith('ovs-vsctl get-controller'):
            return 'tcp:127.0.0.1:6653\n'
        if command.startswith('ovs-vsctl list-ports'):
            return 's1-eth1\n'
        if command.startswith('ovs-vsctl br-exists'):
            return '0\n'
        return ''


old_timeout = command_agent_mod.SWITCH_CONNECT_TIMEOUT
old_poll = command_agent_mod.SWITCH_CONNECT_POLL
command_agent_mod.SWITCH_CONNECT_TIMEOUT = 0.05
command_agent_mod.SWITCH_CONNECT_POLL = 0.001
try:
    sw_ok = _FakeCommandSwitch('s1', connected_after=1)
    net_ok = types.SimpleNamespace(switches=[sw_ok],
                                   controllers=[_FakeController()])
    ok_result = command_agent_mod.h_enable_switch(
        net_ok, '%s:switch-s1' % NAMESPACE, {})
    check('enableSwitch chờ đến khi connected rồi mới OK',
          ok_result[0] is True and sw_ok.started)
    check('enableSwitch re-attach controller sau start',
          any('set-controller s1 tcp:127.0.0.1:6653' in c
              for c in sw_ok.commands))

    sw_fail = _FakeCommandSwitch('s1', connected_after=None)
    net_fail = types.SimpleNamespace(switches=[sw_fail],
                                     controllers=[_FakeController()])
    fail_result = command_agent_mod.h_enable_switch(
        net_fail, '%s:switch-s1' % NAMESPACE, {})
    check('enableSwitch không báo up nếu controller chưa connected',
          fail_result[0] is False and fail_result[1] == 504)
finally:
    command_agent_mod.SWITCH_CONNECT_TIMEOUT = old_timeout
    command_agent_mod.SWITCH_CONNECT_POLL = old_poll

print('\n== TEST 8: command replay dedup ==')
command_agent_mod.AUDIT_PATH = '/tmp/dt4n_command_agent_audit_test.log'
dup_cid = 'cid-dup-test-phase2-5'
first = handle_command({
    'subject': 'rebootEverything',
    'value': {'target': 'org.dt4n:link-h1-s1'},
    'correlation_id': dup_cid,
})
second = handle_command({
    'subject': 'rebootEverything',
    'value': {'target': 'org.dt4n:link-h1-s1'},
    'correlation_id': dup_cid,
})
check('lần đầu command lạ vẫn bị reject', first[0] is False and first[1] == 400)
check('lần lặp cùng cid trả lại đúng kết quả reject cũ',
      second[0] is False and second[1] == 400)


class _TrackingLock:
    def __init__(self):
        self.held = False

    def __enter__(self):
        self.held = True

    def __exit__(self, exc_type, exc, tb):
        self.held = False


class _FakeHost(_FakeNode):
    def cmd(self, command):
        iface = '%s-eth0' % self.name
        return """
Inter-| Receive | Transmit
 face |bytes packets errs drop fifo frame compressed multicast|bytes packets
 %s: 1000 1 0 0 0 0 0 0 2000 2
""" % iface


class _FakeSwitch(_FakeNode):
    def connected(self):
        return True


class _FakeNet:
    def __init__(self):
        self.hosts = [_FakeHost('h1'), _FakeHost('srv1', '10.0.0.4')]
        self.switches = [_FakeSwitch('s1')]
        self.links = [_FakeLink(self.hosts[0], self.switches[0])]

    def get(self, name):
        for node in self.hosts + self.switches:
            if node.name == name:
                return node
        raise KeyError(name)


class _PingTrackingCollector(Collector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ping_saw_lock_held = None

    def collect_latency(self, src, dst_ip):
        self.ping_saw_lock_held = self.net_lock.held
        return {'latency_ms': 1.23, 'packet_loss_pct': 0.0}


print('\n== TEST 9: collector v2 không ping trong collect_all ==')
tracking_lock = _TrackingLock()
collector = _PingTrackingCollector(_FakeNet(), ping_every=1,
                                   net_lock=tracking_lock)
snapshot = collector.collect_all()
check('collect_all không gọi collect_latency',
      collector.ping_saw_lock_held is None)
check('snapshot không sinh path quality từ ping',
      'path-h1-srv1' not in snapshot['things'])


print('\n== TEST 10: collector ping không chiếm shell Mininet ==')


class _NamespaceHost:
    name = 'h1'
    pid = 1234

    def __init__(self):
        self.cmd_called = False

    def cmd(self, command):
        self.cmd_called = True
        return 'fallback'


host = _NamespaceHost()
calls = []
orig_run = collector_mod.subprocess.run


def _fake_run(argv, stdout=None, stderr=None, text=None, timeout=None,
              check=None):
    calls.append({
        'argv': argv,
        'timeout': timeout,
        'text': text,
        'check': check,
    })
    return types.SimpleNamespace(
        stdout='1 packets transmitted, 1 received, 0% packet loss\n')


collector_mod.subprocess.run = _fake_run
try:
    out = run_host_namespace_command(host, ['ping', '-c', '1', '10.0.0.1'],
                                     timeout=3)
finally:
    collector_mod.subprocess.run = orig_run

check('dùng mnexec -a <pid> thay vì host.cmd',
      calls and calls[0]['argv'][:3] == ['mnexec', '-a', '1234'])
check('truyền timeout xuống subprocess', calls and calls[0]['timeout'] == 3)
check('không gọi host.cmd khi host có pid', host.cmd_called is False)
check('stdout được trả về để parse ping', 'packet loss' in out)

print('\n' + '=' * 50)
print('KET QUA: %d pass, %d fail' % (passed, failed))


def test_phase2_5_script_checks_passed():
    assert failed == 0


if __name__ == '__main__':
    sys.exit(0 if failed == 0 else 1)


def test_verify_reads_more_than_one_ditto_page(monkeypatch):
    """A twin larger than Ditto's 200-item limit must remain complete."""
    import bridge.verify as verify
    entries = [{'thingId': 'org.test:host-h%d' % i,
                'attributes': {'type': 'host'}, 'features': {}} for i in range(202)]
    calls = []

    def get(url, params, **kwargs):
        calls.append(params['option'])
        payload = ({'items': entries[:200], 'cursor': 'next-page'}
                   if len(calls) == 1 else {'items': entries[200:]})
        return types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: payload)

    monkeypatch.setattr(verify.requests, 'get', get)
    assert set(verify.fetch_all_twin_things()) == {row['thingId'] for row in entries}
    assert calls == ['size(200)', 'size(200),cursor(next-page)']


def test_verify_rejects_repeated_ditto_cursor(monkeypatch):
    """A broken cursor must raise instead of hanging or hiding missing data."""
    import pytest
    import bridge.verify as verify
    response = types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: {'items': [], 'cursor': 'same'})
    monkeypatch.setattr(verify.requests, 'get', lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match='repeated'):
        verify.fetch_all_twin_things()
