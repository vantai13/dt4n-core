#!/usr/bin/env python3
"""Automated per-hop command-flow measurement.

Run inside mininet.run_sync so it can use the live Mininet `net` object. The
script sends Ditto commands exactly like the dashboard path, waits for the twin
to reflect the expected state, and prints hop-by-hop timing from
logs/command_flow.log.
"""

import os
import time
import uuid
from contextlib import nullcontext
from pathlib import Path

import requests

from bridge.ditto_common import (
    DITTO_BASE_URL, DITTO_AUTH, NAMESPACE, HTTP_TIMEOUT, make_thing_id_link,
)
from bridge.flow_log import FLOW_LOG_PATH, flow_event
from measurements.stats import summarize, format_report
from measurements.trace_latency import (
    read_events, group_events, metrics_for_group, fmt_ms, short_target,
)


CONTROLLER = '%s:controller' % NAMESPACE
COMMAND_ACK_TIMEOUT_SECONDS = 0
REFLECTION_TIMEOUT_SECONDS = 20
POLL_INTERVAL = 0.2
SETTLE_SECONDS = 1.0
DEFAULT_REPORT_PATH = 'logs/command_flow_measure.log'


class ReportWriter:
    """Write measurement output to terminal and a plain text report file."""

    def __init__(self, path):
        self.path = path
        self.file = None
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.file = open(path, 'w', encoding='utf-8')
            try:
                os.chmod(path, 0o666)
            except OSError:
                pass

    def line(self, text=''):
        print(text)
        if self.file:
            self.file.write(text + '\n')
            self.file.flush()

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def bool_str(value):
    return 'true' if value else 'false'


def expected_for_subject(subject):
    if subject == 'disableLink':
        return 'down'
    if subject == 'enableLink':
        return 'up'
    return None


def twin_state(thing_id):
    url = '%s/things/%s/features/status/properties/state' % (
        DITTO_BASE_URL, thing_id)
    try:
        r = requests.get(url, auth=DITTO_AUTH, timeout=2)
        if r.status_code == 200:
            return r.json()
        return 'http-%d' % r.status_code
    except requests.exceptions.RequestException as e:
        return 'error:%s' % type(e).__name__


def wait_twin_state(thing_id, expected, timeout):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = twin_state(thing_id)
        if last == expected:
            return True, last
        time.sleep(POLL_INTERVAL)
    return False, last


def resolve_link(net, h, s):
    want = {h, s}
    for link in net.links:
        a = link.intf1.node.name
        b = link.intf2.node.name
        if {a, b} == want:
            return link
    return None


def link_runtime_status(net, h, s, net_lock=None):
    lock = net_lock if net_lock is not None else nullcontext()
    with lock:
        link = resolve_link(net, h, s)
        if link is None:
            return 'link %s-%s not found' % (h, s)

        rows = []
        for intf in (link.intf1, link.intf2):
            try:
                out = intf.ifconfig()
                first = out.splitlines()[0].strip() if out else ''
                rows.append('%s:%s' % (intf.name, 'UP' if 'UP' in out else 'DOWN'))
                if first:
                    rows[-1] += ' [%s]' % first[:80]
            except Exception as e:
                rows.append('%s:error:%s' % (intf.name, type(e).__name__))
        return '; '.join(rows)


def reset_link_up(net, h, s, thing_id, net_lock=None, timeout=8):
    lock = net_lock if net_lock is not None else nullcontext()
    with lock:
        net.configLinkStatus(h, s, 'up')
    ok, state = wait_twin_state(thing_id, 'up', timeout)
    return ok, state


def send_ditto_command(subject, target, correlation_id, timeout_seconds):
    url = '%s/things/%s/inbox/messages/%s?timeout=%s' % (
        DITTO_BASE_URL, CONTROLLER, subject, timeout_seconds)
    body = {
        'target': target,
        'clientCorrelationId': correlation_id,
    }
    headers = {
        'Content-Type': 'application/json',
        'correlation-id': correlation_id,
    }

    state_before = twin_state(target)
    flow_event('MEASURE', 'CLICK', correlation_id, subject, target,
               stateBefore=state_before, params={})
    flow_event('MEASURE', 'SEND', correlation_id, subject, target,
               detail='POST %s' % url, timeout='%ss' % timeout_seconds)

    started = time.monotonic()
    status = None
    response = None
    raw_text = ''
    error = None
    try:
        r = requests.post(url, json=body, headers=headers, auth=DITTO_AUTH,
                          timeout=max(HTTP_TIMEOUT, timeout_seconds + 2))
        status = r.status_code
        raw_text = r.text[:500]
        try:
            response = r.json() if r.text else None
        except ValueError:
            response = None
    except requests.exceptions.RequestException as e:
        error = '%s:%s' % (type(e).__name__, e)

    duration_ms = int(round((time.monotonic() - started) * 1000))
    timed_out = status == 408
    rejected = isinstance(response, dict) and response.get('status') == 'rejected'
    ok = status is not None and 200 <= status < 300 and not rejected

    if error:
        flow_event('MEASURE', 'ERROR', correlation_id, subject, target,
                   level='ERROR', detail=error, durationMs=duration_ms)
    else:
        flow_event('MEASURE', 'DITTO_RESPONSE', correlation_id, subject, target,
                   http=status, timedOut=bool_str(timed_out),
                   rejected=bool_str(rejected), durationMs=duration_ms,
                   rawText=raw_text.replace('\n', ' ')[:200])
    flow_event('MEASURE', 'UI_ACK', correlation_id, subject, target,
               ok=bool_str(ok), timedOut=bool_str(timed_out),
               rejected=bool_str(rejected), http=status or '-')
    return ok, timed_out, rejected, status, error


def wait_for_reflection(subject, target, correlation_id, timeout):
    expected = expected_for_subject(subject)
    if expected is None:
        flow_event('MEASURE', 'STATE_SKIP', correlation_id, subject, target)
        return False, None

    state_now = twin_state(target)
    flow_event('MEASURE', 'WAIT_STATE', correlation_id, subject, target,
               expect=expected, stateNow=state_now, timeoutMs=int(timeout * 1000))
    ok, state = wait_twin_state(target, expected, timeout)
    if ok:
        flow_event('MEASURE', 'STATE_OK', correlation_id, subject, target,
                   expect=expected, state=state)
    else:
        flow_event('MEASURE', 'STATE_TIMEOUT', correlation_id, subject, target,
                   level='WARN', expect=expected, state=state or '-')
    return ok, state


def group_for_cid(correlation_id, window=45):
    path = Path(FLOW_LOG_PATH)
    if not path.exists():
        return None
    groups = group_events(read_events(path), window)
    for group in reversed(groups):
        if group.get('cid') == correlation_id:
            return group
    return None


def print_header(report):
    report.line('trial cmd          target                 ack   route   lock   exec  detect  push   ui    total  result')
    report.line('-' * 115)


def print_result(report, index, subject, group, ok, final_state, runtime):
    if group is None:
        report.line('%5d %-12s %-22s %s %s %s %s %s %s %s %s  %s' % (
            index, subject, '-', fmt_ms(None), fmt_ms(None), fmt_ms(None),
            fmt_ms(None), fmt_ms(None), fmt_ms(None), fmt_ms(None),
            fmt_ms(None),
            'missing trace group'))
        report.line('      runtime: %s | twin=%s' % (runtime, final_state))
        return {}

    m = metrics_for_group(group)
    result = 'OK' if ok else 'TIMEOUT'
    if m['note']:
        result += ' / ' + m['note']
    report.line('%5d %-12s %-22s %s %s %s %s %s %s %s %s  %s' % (
        index,
        m['subject'][:12],
        short_target(m['target'])[:22],
        fmt_ms(m['ack_ms']),
        fmt_ms(m['route_ms']),
        fmt_ms(m['lock_wait_ms']),
        fmt_ms(m['exec_ms']),
        fmt_ms(m['detect_ms']),
        fmt_ms(m['push_ms']),
        fmt_ms(m['ui_ms']),
        fmt_ms(m['total_ms']),
        result,
    ))
    report.line('      runtime: %s | twin=%s expect=%s' %
                (runtime, final_state, m.get('expect')))
    return m


def print_stage_summaries(report, rows):
    fields = [
        ('ack_ms', 'Ditto Ack'),
        ('route_ms', 'UI/Measure -> Agent'),
        ('lock_wait_ms', 'Agent Lock Wait'),
        ('exec_ms', 'Agent Execute'),
        ('detect_ms', 'Sync Detect'),
        ('push_ms', 'Ditto Patch'),
        ('ui_ms', 'Twin Reflection'),
        ('total_ms', 'Total'),
    ]
    report.line('')
    report.line('=== Hop summaries ===')
    for key, title in fields:
        vals = [r[key] / 1000.0 for r in rows
                if isinstance(r.get(key), int)]
        report.line(format_report(summarize(vals), title=title))


def run_one(report, net, h, s, subject, index, net_lock=None,
            reflection_timeout=REFLECTION_TIMEOUT_SECONDS,
            command_timeout=COMMAND_ACK_TIMEOUT_SECONDS):
    target = make_thing_id_link(h, s)
    cid = str(uuid.uuid4())
    send_ditto_command(subject, target, cid, command_timeout)
    ok, final_state = wait_for_reflection(subject, target, cid,
                                          reflection_timeout)
    # Give file log and Sync Agent a tiny chance to finish writing adjacent lines.
    time.sleep(0.2)
    group = group_for_cid(cid)
    runtime = link_runtime_status(net, h, s, net_lock=net_lock)
    return print_result(report, index, subject, group, ok, final_state, runtime)


def main(net, n_trials=3, h='h1', s='s1', net_lock=None,
         settle=SETTLE_SECONDS, reflection_timeout=REFLECTION_TIMEOUT_SECONDS,
         command_timeout=COMMAND_ACK_TIMEOUT_SECONDS, reset_log=False,
         report_path=DEFAULT_REPORT_PATH):
    target = make_thing_id_link(h, s)
    if reset_log:
        Path(FLOW_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(FLOW_LOG_PATH).write_text('', encoding='utf-8')
        try:
            os.chmod(FLOW_LOG_PATH, 0o666)
        except OSError:
            pass

    report = ReportWriter(report_path)
    try:
        report.line('Automated command-flow measure: link %s-%s, trials=%d' %
                    (h, s, n_trials))
        report.line('Ditto target: %s' % target)
        report.line('Flow log: %s' % FLOW_LOG_PATH)
        report.line('Report log: %s' % report_path)

        baseline_ok, baseline_state = reset_link_up(
            net, h, s, target, net_lock=net_lock)
        report.line('Baseline direct-up: twin=%s ok=%s' %
                    (baseline_state, bool_str(baseline_ok)))
        report.line('Baseline runtime: %s' %
                    link_runtime_status(net, h, s, net_lock=net_lock))
        report.line('')

        rows = []
        print_header(report)
        op_index = 1
        for _ in range(n_trials):
            rows.append(run_one(report, net, h, s, 'disableLink', op_index,
                                net_lock=net_lock,
                                reflection_timeout=reflection_timeout,
                                command_timeout=command_timeout))
            op_index += 1
            time.sleep(settle)
            rows.append(run_one(report, net, h, s, 'enableLink', op_index,
                                net_lock=net_lock,
                                reflection_timeout=reflection_timeout,
                                command_timeout=command_timeout))
            op_index += 1
            time.sleep(settle)

        rows = [r for r in rows if r]
        print_stage_summaries(report, rows)

        baseline_ok, baseline_state = reset_link_up(
            net, h, s, target, net_lock=net_lock)
        report.line('')
        report.line('Final direct-up: twin=%s ok=%s' %
                    (baseline_state, bool_str(baseline_ok)))
        return rows
    finally:
        report.close()
