#!/usr/bin/env python3
"""Print per-hop command latency from logs/command_flow.log.

This script analyzes a manual dashboard command, for example Disable Link. It
joins command events by correlation-id, then joins Sync Agent events by target
because the observe loop is independent and intentionally has no command cid.
"""

import argparse
import datetime as dt
import re
from pathlib import Path


DEFAULT_LOG = Path('logs/command_flow.log')
TIMESTAMP_RE = re.compile(r'^\[([\d-]+ [\d:.]+)\]')
FIELD_RE = re.compile(r'(?P<key>[A-Za-z_][\w-]*)=(?P<value>[^\s\]]*)')

STAGES = {
    'CLICK': 'click',
    'DITTO_RESPONSE': 'ditto_response',
    'UI_ACK': 'ui_ack',
    'WAIT_STATE': 'wait',
    'RECEIVE': 'agent_receive',
    'LOCK_WAIT': 'lock_wait',
    'EXECUTE_DONE': 'exec_done',
    'STATE_DETECTED': 'detect',
    'STATE_PUSHED': 'push',
    'STATE_OK_AFTER_RESYNC': 'ui_resync',
    'STATE_TIMEOUT': 'ui_timeout',
    'STATE_OK': 'ui',
}


def expected_for_subject(subject):
    if subject == 'disableLink':
        return 'down'
    if subject == 'enableLink':
        return 'up'
    if subject == 'disableHost':
        return 'down'
    if subject == 'enableHost':
        return 'up'
    return None


def parse_timestamp(line):
    match = TIMESTAMP_RE.match(line)
    if not match:
        return None
    return dt.datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S.%f')


def fields(line):
    return {m.group('key'): m.group('value') for m in FIELD_RE.finditer(line)}


def event_stage(line):
    for marker, stage in STAGES.items():
        if marker in line:
            return stage
    return None


def read_events(path):
    events = []
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        stage = event_stage(line)
        if not stage:
            continue
        timestamp = parse_timestamp(line)
        row = fields(line)
        target = row.get('target', '-')
        if not timestamp:
            continue
        if stage in ('detect', 'push') and (not target or target == '-'):
            continue
        events.append({
            'time': timestamp,
            'stage': stage,
            'target': target,
            'cid': row.get('cid'),
            'subject': row.get('subject'),
            'expect': row.get('expect'),
            'http': row.get('http'),
            'timed_out': row.get('timedOut'),
            'wait_ms': row.get('waitMs'),
            'detail': row.get('detail'),
            'line': line,
        })
    return sorted(events, key=lambda e: e['time'])


def group_events(events, window_seconds):
    by_cid = {}
    groups = []

    for event in events:
        stage = event['stage']
        cid = event.get('cid')

        if cid and cid != '-' and stage not in ('detect', 'push'):
            group = by_cid.get(cid)
            if group is None:
                group = {'cid': cid, 'target': event['target']}
                by_cid[cid] = group
                groups.append(group)
            if event['target'] != '-':
                group['target'] = event['target']
            subject = event.get('subject')
            if subject and subject != '-':
                group['subject'] = subject
                expected = expected_for_subject(subject)
                if expected:
                    group['expect'] = expected
            if event.get('expect'):
                group['expect'] = event.get('expect')
            if stage not in group:
                group[stage] = event['time']
            if stage == 'ditto_response':
                group['http'] = event.get('http')
                group['timed_out'] = event.get('timed_out')
            if stage == 'lock_wait':
                try:
                    group['lock_wait_ms'] = int(float(event.get('wait_ms')))
                except (TypeError, ValueError):
                    pass
            continue

        if stage in ('detect', 'push'):
            for group in reversed(groups):
                exec_done = group.get('exec_done')
                if group.get('target') != event['target'] or exec_done is None:
                    continue
                ui_done = (group.get('ui') or group.get('ui_resync')
                           or group.get('ui_timeout'))
                if ui_done is not None and event['time'] > ui_done:
                    continue
                expected = group.get('expect')
                if expected and event.get('detail') != expected:
                    continue
                if stage in group:
                    continue
                age = (event['time'] - exec_done).total_seconds()
                if 0 <= age <= window_seconds:
                    group[stage] = event['time']
                    break

    return groups


def duration_ms(start, end):
    if start is None or end is None:
        return None
    return int(round((end - start).total_seconds() * 1000))


def fmt_ms(value):
    return '   --  ' if value is None else f'{value:6d}'


def short_target(target):
    return target.split(':', 1)[-1]


def metrics_for_group(group):
    ui_stage = 'ui'
    if 'ui_resync' in group:
        ui_stage = 'ui_resync'
    elif 'ui_timeout' in group:
        ui_stage = 'ui_timeout'

    click_time = group.get('click')
    receive_time = group.get('agent_receive')
    exec_time = group.get('exec_done')
    detect_time = group.get('detect')
    push_time = group.get('push')
    ui_time = group.get(ui_stage)
    response_time = group.get('ditto_response')

    note = ''
    if ui_stage == 'ui_resync':
        note = 'RESYNC'
    elif ui_stage == 'ui_timeout':
        note = 'TIMEOUT'
    elif group.get('timed_out') == 'true' or group.get('http') == '408':
        note = 'Ditto response timeout'
    elif receive_time is None:
        note = 'missing AGENT RECEIVE'
    elif exec_time is None:
        note = 'missing EXECUTE_DONE'
    elif detect_time is None:
        note = 'missing STATE_DETECTED'
    elif push_time is None:
        note = 'missing STATE_PUSHED'
    elif ui_time is None:
        note = 'missing UI reflection'

    return {
        'subject': group.get('subject', '-'),
        'target': group.get('target', '-'),
        'expect': group.get('expect', '-'),
        'ack_ms': duration_ms(click_time, response_time),
        'route_ms': duration_ms(click_time, receive_time),
        'lock_wait_ms': group.get('lock_wait_ms'),
        'exec_ms': duration_ms(receive_time, exec_time),
        'detect_ms': duration_ms(exec_time, detect_time),
        'push_ms': duration_ms(detect_time, push_time),
        'ui_ms': duration_ms(push_time, ui_time),
        'total_ms': duration_ms(click_time or exec_time, ui_time),
        'note': note,
    }


def print_table(groups, limit):
    complete = [g for g in groups if 'click' in g or 'exec_done' in g]
    rows = complete[-limit:] if limit else complete
    print('cmd          target                 ack   route   lock   exec  detect  push   ui    total  note')
    print('-' * 108)
    for group in rows:
        m = metrics_for_group(group)

        print('%-12s %-22s %s %s %s %s %s %s %s  %s' % (
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
            m['note'],
        ))


def main():
    parser = argparse.ArgumentParser(
        description='Analyze per-hop latency from logs/command_flow.log')
    parser.add_argument('--log', default=str(DEFAULT_LOG),
                        help='path to command_flow.log')
    parser.add_argument('--limit', type=int, default=12,
                        help='number of newest command groups to print; 0 = all')
    parser.add_argument('--window', type=float, default=30.0,
                        help='seconds after EXECUTE_DONE used to join related events')
    args = parser.parse_args()

    path = Path(args.log)
    if not path.exists():
        raise SystemExit('Log file not found: %s' % path)

    groups = group_events(read_events(path), args.window)
    if not groups:
        raise SystemExit('No EXECUTE_DONE events found in %s' % path)
    print_table(groups, args.limit)


if __name__ == '__main__':
    main()
