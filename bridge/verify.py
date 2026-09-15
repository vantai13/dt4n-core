#!/usr/bin/env python3
"""
verify.py — Nghiệm thu tính đúng đắn của twin (Lesson 2.5). LỚP 2.

Đo các khía cạnh chính:
  - completeness: Mininet có bao nhiêu thực thể, Ditto có đủ bấy nhiêu Thing?
  - accuracy: trạng thái link trong Ditto có khớp ground truth Mininet không?
  - consistency: accuracy có giữ ổn theo thời gian không?
  - event fidelity: link down/up có được twin bắt lại không?

Ground truth ở đây đọc trực tiếp từ Mininet/link interface, không dùng lại
collector snapshot của sync agent để tránh "kiểm tra bằng chính mình".
"""

import json
import logging
import os
import time
from contextlib import nullcontext

import requests

from bridge.ditto_common import (
    DITTO_BASE_URL, DITTO_AUTH, NAMESPACE, HTTP_TIMEOUT,
    make_thing_id_host, make_thing_id_switch, make_thing_id_link,
)

log = logging.getLogger('verify')


def values_match(gt, twin, tol_pct=5.0, tol_abs=1.0):
    """So sánh có tolerance cho số; chuỗi/bool phải khớp tuyệt đối."""
    if isinstance(gt, bool) or isinstance(twin, bool):
        return isinstance(gt, bool) and isinstance(twin, bool) and gt == twin
    if gt == twin:
        return True
    if not isinstance(gt, (int, float)) or not isinstance(twin, (int, float)):
        return gt == twin
    if abs(gt - twin) < tol_abs:
        return True
    if gt == 0:
        return abs(twin) < tol_abs
    return abs(gt - twin) / abs(gt) < tol_pct / 100.0


def fetch_all_twin_things():
    """Lấy mọi Thing trong namespace từ Ditto. Trả {thing_id: thing_json}."""
    url = '%s/search/things' % DITTO_BASE_URL
    # Ditto enforces a maximum page size of 200. Follow cursors so
    # completeness never silently treats the first page as the whole twin.
    items = []
    cursor = None
    seen_cursors = set()
    while True:
        option = 'size(200)'
        if cursor:
            option += ',cursor(%s)' % cursor
        params = {'filter': 'like(thingId,"%s:*")' % NAMESPACE, 'option': option}
        r = requests.get(url, params=params, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get('items', []))
        cursor = data.get('cursor')
        if not cursor:
            break
        if cursor in seen_cursors:
            raise RuntimeError('Ditto search repeated a pagination cursor')
        seen_cursors.add(cursor)

    # Ditto search thường trả đủ Thing, nhưng fetch lại nếu thiếu fields quan trọng.
    out = {}
    for item in items:
        tid = item.get('thingId')
        if not tid:
            continue
        if 'attributes' in item and 'features' in item:
            out[tid] = item
            continue
        rr = requests.get('%s/things/%s' % (DITTO_BASE_URL, tid),
                          auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
        if rr.status_code == 200:
            out[tid] = rr.json()
    return out


def fetch_twin_state(thing_id):
    """GET features/status/properties/state của 1 Thing."""
    url = '%s/things/%s/features/status/properties/state' % (DITTO_BASE_URL, thing_id)
    try:
        r = requests.get(url, auth=DITTO_AUTH, timeout=1)
        if r.status_code == 200:
            return r.json()
    except requests.exceptions.RequestException:
        pass
    return None


def _lock_ctx(net_lock):
    return net_lock if net_lock is not None else nullcontext()


def ground_truth_entities(net, net_lock=None):
    """Danh sách thingId kỳ vọng từ topology Mininet thật."""
    with _lock_ctx(net_lock):
        hosts = {make_thing_id_host(h.name) for h in net.hosts}
        switches = {make_thing_id_switch(s.name) for s in net.switches}
        links = set()
        for ln in net.links:
            links.add(make_thing_id_link(ln.intf1.node.name, ln.intf2.node.name))
    return hosts, switches, links


def ground_truth_link_state(link):
    """Đọc trạng thái link trực tiếp từ interface Mininet."""
    up1 = link.intf1.isUp() if hasattr(link.intf1, 'isUp') else True
    up2 = link.intf2.isUp() if hasattr(link.intf2, 'isUp') else True
    return 'up' if up1 and up2 else 'down'


def check_completeness(net, net_lock=None):
    gt_hosts, gt_switches, gt_links = ground_truth_entities(net, net_lock=net_lock)
    twin = fetch_all_twin_things()
    twin_ids = set(twin.keys())

    def cmp(expected, kind):
        actual = {
            tid for tid in twin_ids
            if twin[tid].get('attributes', {}).get('type') == kind
        }
        return {
            'expected': len(expected),
            'actual': len(actual),
            'missing': sorted(expected - actual),
            'extra': sorted(actual - expected),
        }

    return {
        'hosts': cmp(gt_hosts, 'host'),
        'switches': cmp(gt_switches, 'switch'),
        'links': cmp(gt_links, 'link'),
    }


def check_accuracy(net, tol_pct=5.0, tol_abs=1.0, net_lock=None):
    """So state của mọi physical link giữa Mininet và Ditto."""
    twin = fetch_all_twin_things()
    discrepancies = []
    checked = 0
    matched = 0

    with _lock_ctx(net_lock):
        link_rows = [
            (ln.intf1.node.name, ln.intf2.node.name, ground_truth_link_state(ln))
            for ln in net.links
        ]

    for a, b, gt_state in link_rows:
        tid = make_thing_id_link(a, b)
        twin_state = (
            twin.get(tid, {})
            .get('features', {})
            .get('status', {})
            .get('properties', {})
            .get('state')
        )
        checked += 1
        if values_match(gt_state, twin_state, tol_pct=tol_pct, tol_abs=tol_abs):
            matched += 1
        else:
            discrepancies.append({
                'thing': tid,
                'path': 'features/status/properties/state',
                'ground_truth': gt_state,
                'twin': twin_state,
            })

    rate = matched / checked * 100 if checked else 0.0
    return {
        'checked': checked,
        'matched': matched,
        'accuracy_rate': round(rate, 1),
        'discrepancies': discrepancies,
    }


def poll_until_state(thing_id, expected, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fetch_twin_state(thing_id) == expected:
            return time.monotonic()
        time.sleep(interval)
    return None


def check_event_fidelity(net, h='h1', s='s1', n_events=20, settle=3.0,
                         net_lock=None):
    """Gây link down nhiều lần, đếm số lần Ditto phản ánh được."""
    tid = make_thing_id_link(h, s)
    detected = 0
    rows = []

    for i in range(n_events):
        with _lock_ctx(net_lock):
            net.configLinkStatus(h, s, 'up')
        poll_until_state(tid, 'up', timeout=5)
        time.sleep(settle)

        with _lock_ctx(net_lock):
            t_event = time.monotonic()
            net.configLinkStatus(h, s, 'down')
        t_ref = poll_until_state(tid, 'down', timeout=10)

        if t_ref is None:
            rows.append({'i': i + 1, 'detected': False, 'latency_s': None})
            log.warning('Event %d không được bắt trong 10s.', i + 1)
            continue

        detected += 1
        rows.append({
            'i': i + 1,
            'detected': True,
            'latency_s': round(t_ref - t_event, 3),
        })

    with _lock_ctx(net_lock):
        net.configLinkStatus(h, s, 'up')

    return {
        'detected': detected,
        'total': n_events,
        'fidelity_pct': round(detected / n_events * 100, 1) if n_events else 0.0,
        'log': rows,
    }


def check_long_term(net, duration_min=30, interval_min=5, net_lock=None):
    """Lặp lại accuracy theo thời gian để quan sát drift."""
    results = []
    start = time.monotonic()
    end = start + duration_min * 60
    while time.monotonic() < end:
        elapsed_min = (time.monotonic() - start) / 60
        acc = check_accuracy(net, net_lock=net_lock)
        row = {
            'time_min': round(elapsed_min, 1),
            'discrepancies': len(acc['discrepancies']),
            'accuracy_rate': acc['accuracy_rate'],
        }
        results.append(row)
        log.info('t=%.1f phút: %d lệch, accuracy=%.1f%%',
                 elapsed_min, row['discrepancies'], row['accuracy_rate'])
        time.sleep(interval_min * 60)
    return results


def print_summary(report):
    results = report['results']
    print('\n=== TỔNG KẾT NGHIỆM THU TWIN ===\n')

    completeness = results.get('completeness', {})
    for kind in ('hosts', 'switches', 'links'):
        row = completeness.get(kind, {})
        ok = not row.get('missing') and not row.get('extra')
        print('  %s: %d/%d %s' % (
            kind,
            row.get('actual', 0),
            row.get('expected', 0),
            'OK' if ok else 'LECH',
        ))

    accuracy = results.get('accuracy')
    if accuracy:
        print('  accuracy: %.1f%% (%d/%d khop)' % (
            accuracy['accuracy_rate'], accuracy['matched'], accuracy['checked']))

    fidelity = results.get('event_fidelity')
    if fidelity:
        print('  event fidelity: %d/%d (%.1f%%)' % (
            fidelity['detected'], fidelity['total'], fidelity['fidelity_pct']))

    print('\nChi tiet nam trong JSON output.')


def run_full_verification(net, args, net_lock=None):
    """Chạy nghiệm thu. args là argparse/namespace có các field tương ứng."""
    report = {
        'timestamp': time.time(),
        'config': {
            'long': bool(getattr(args, 'long', False)),
            'duration_min': getattr(args, 'duration', None),
            'interval_min': getattr(args, 'verify_interval', None),
            'n_events': getattr(args, 'n_events', None),
            'verify_link': getattr(args, 'verify_link', None),
        },
        'results': {},
    }

    log.info('=== 1. Completeness ===')
    report['results']['completeness'] = check_completeness(net, net_lock=net_lock)

    log.info('=== 2. Accuracy ===')
    report['results']['accuracy'] = check_accuracy(net, net_lock=net_lock)

    report['results']['freshness'] = {
        'note': 'Freshness đo bằng --measure-latency trong run_sync hoặc measurements/measure_latency.py',
    }

    if getattr(args, 'long', False):
        log.info('=== 4. Consistency ===')
        report['results']['consistency'] = check_long_term(
            net,
            duration_min=getattr(args, 'duration', 30),
            interval_min=getattr(args, 'verify_interval', 5),
            net_lock=net_lock,
        )

    link = getattr(args, 'verify_link', 'h1-s1')
    h, s = link.split('-', 1)
    log.info('=== 5. Event Fidelity ===')
    report['results']['event_fidelity'] = check_event_fidelity(
        net,
        h=h,
        s=s,
        n_events=getattr(args, 'n_events', 20),
        net_lock=net_lock,
    )

    output = getattr(args, 'output', 'docs/phase-2/verify_report.json')
    parent = os.path.dirname(os.path.abspath(output))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info('Luu bao cao -> %s', output)
    print_summary(report)
    return report
