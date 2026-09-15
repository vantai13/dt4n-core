#!/usr/bin/env python3
"""
sync_agent.py — Bản cuối Phase 2: delta sync + retry + reconciliation. LỚP 2.

Ba tầng chống lỗi:
  - Delta sync (2.3): gửi phần đổi -> nhanh, tải thấp.
  - Resilience (2.4): retry/backoff trong pusher + graceful degradation.
  - Reconciliation (2.5): định kỳ gửi full state -> vá drift im lặng.
"""

import json
import logging
import os
import time

from bridge.adapter import collector_to_things
from bridge.differ import diff_snapshot, DEFAULT_TOL
from bridge.flow_log import flow_event
from bridge.pusher import patch_thing, make_session

try:
    from bridge.collector import Collector
except ImportError:
    from mininet.collector import Collector

log = logging.getLogger('sync_agent')

FAILURE_ALERT_THRESHOLD = 5   # số chu kỳ hỏng liên tiếp thì cảnh báo to


def build_full_changes(things_now):
    """Full reconciliation patch: gửi toàn bộ features của mọi Thing."""
    return {
        tid: {'features': data.get('features', {})}
        for tid, data in things_now.items()
        if data.get('features')
    }


def should_reconcile(cycle, reconcile_every):
    """True nếu chu kỳ này cần full reconciliation. 0 = tắt."""
    return reconcile_every > 0 and cycle % reconcile_every == 0


def status_state_in(patch):
    """Return the changed status.state from a patch, or None if absent."""
    try:
        return patch['features']['status']['properties']['state']
    except (KeyError, TypeError):
        return None


def run(net, period=1.0, tol=DEFAULT_TOL, log_every=10, max_cycles=None,
        ping_every=20, net_lock=None, stop_event=None, reconcile_every=30,
        measurement_mode=None, cycle_trace_path=None, thing_ids=None):
    """Run delta sync, optionally in an explicitly traced calibration mode.

    ``clean`` forces a full push every cycle; ``prod`` preserves the supplied
    delta/reconciliation settings and only enables measurement metadata.
    """
    if measurement_mode not in (None, 'clean', 'prod'):
        raise ValueError("measurement_mode phai la None, 'clean', hoac 'prod'")
    if measurement_mode == 'clean':
        tol = 0.0
        reconcile_every = 1
    if cycle_trace_path:
        parent = os.path.dirname(os.path.abspath(cycle_trace_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    log.info(
        'Sync Agent start: period=%.3fs, tol=%.3f, ping_every=%d, '
        'reconcile_every=%d, mode=%s',
        period, tol, ping_every, reconcile_every, measurement_mode,
    )

    collector = Collector(net, interval=period, ping_every=ping_every,
                          net_lock=net_lock)
    net.dt4n_collector = collector
    session = make_session()
    prev_things = None
    cycle = 0
    consecutive_failures = 0     # đếm chu kỳ có ÍT NHẤT 1 patch lỗi, liên tiếp
    allowed_thing_ids = None if thing_ids is None else set(thing_ids)

    while (max_cycles is None or cycle < max_cycles) and not (
            stop_event is not None and stop_event.is_set()):
        cycle_start = time.monotonic()
        t_lock_req = time.time()

        # ===== Bước 1: COLLECT (bọc try -> Mininet lỗi không sập agent) =====
        try:
            snapshot = collector.collect_all()
            lock_wait_ms = (
                float(snapshot.get('t_cycle_start', t_lock_req)) - t_lock_req
            ) * 1000.0
            things_now = collector_to_things(snapshot)
            if allowed_thing_ids is not None:
                things_now = {
                    thing_id: body
                    for thing_id, body in things_now.items()
                    if thing_id in allowed_thing_ids
                }
        except Exception as e:
            log.error('Collector lỗi: %s — bỏ qua chu kỳ', e)
            if stop_event is not None:
                stop_event.wait(period)
            else:
                time.sleep(period)
            cycle += 1
            continue

        # ===== Bước 2: DELTA hoặc FULL RECONCILE =====
        is_reconcile = should_reconcile(cycle, reconcile_every)
        if is_reconcile:
            changes = build_full_changes(things_now)
        else:
            changes = diff_snapshot(things_now, prev_things, tol)

        # ===== Bước 3: PUSH từng Thing, cập nhật prev theo CÁCH B =====
        n_ok = n_fail = 0
        if prev_things is None:
            prev_things = {}
        for tid, data in things_now.items():
            patch = changes.get(tid)
            if patch is None:
                # không đổi -> prev đã đúng, giữ nguyên (hoặc set lần đầu)
                prev_things[tid] = data
                continue
            new_state = status_state_in(patch)
            if new_state is not None:
                flow_event('SYNC', 'STATE_DETECTED', target=tid,
                           detail=new_state, cycle=cycle)
            if patch_thing(tid, patch, session=session):
                n_ok += 1
                prev_things[tid] = data        # CHỈ cập nhật prev khi PATCH OK
                if new_state is not None:
                    flow_event('SYNC', 'STATE_PUSHED', target=tid,
                               detail=new_state, cycle=cycle)
            else:
                n_fail += 1
                # KHÔNG cập nhật prev[tid] -> chu kỳ sau diff lại ra changes -> tự retry

        cycle += 1
        elapsed = time.monotonic() - cycle_start

        if cycle_trace_path:
            with open(cycle_trace_path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps({
                    'cycle': cycle,
                    'mode': measurement_mode,
                    'is_reconcile': bool(is_reconcile),
                    'n_ok': n_ok,
                    'n_fail': n_fail,
                    'n_things': len(things_now),
                    'n_pushed': len(changes),
                    'cycle_elapsed_ms': elapsed * 1000.0,
                    'cycle_scan_ms': snapshot.get('cycle_scan_ms'),
                    'lock_wait_ms': lock_wait_ms,
                    'overrun': bool(elapsed > period),
                    't_cycle_start': snapshot.get('t_cycle_start'),
                }, sort_keys=True) + '\n')

        # ===== Bước 4: theo dõi sức khỏe (graceful degradation) =====
        tag = 'RECONCILE' if is_reconcile else 'delta'
        if n_fail > 0:
            consecutive_failures += 1
            log.warning('Cycle #%d [%s]: %d OK, %d lỗi, liên tiếp=%d',
                        cycle, tag, n_ok, n_fail, consecutive_failures)
            if consecutive_failures >= FAILURE_ALERT_THRESHOLD:
                log.error('Lỗi đồng bộ kéo dài — Ditto có thể đang chết. '
                          'Agent VẪN chạy (graceful degradation), sẽ tự lành khi Ditto trở lại.')
        else:
            if consecutive_failures > 0:
                log.info('Đồng bộ hồi phục sau %d chu kỳ lỗi.', consecutive_failures)
            consecutive_failures = 0
            if is_reconcile or cycle % log_every == 0 or n_ok > 0:
                log.info('Cycle #%d [%s]: %d/%d patch, elapsed=%.0fms',
                         cycle, tag, n_ok, n_ok + n_fail, elapsed * 1000)

        if elapsed > period:
            if elapsed > period * 3 or cycle % log_every == 0:
                log.warning('Cycle overran: %.2fs > %.1fs', elapsed, period)
            else:
                log.debug('Cycle overran: %.2fs > %.1fs', elapsed, period)

        sleep_time = max(0, period - elapsed)
        if stop_event is not None:
            stop_event.wait(sleep_time)
        else:
            time.sleep(sleep_time)

    log.info('Sync Agent dừng sau %d chu kỳ.', cycle)
