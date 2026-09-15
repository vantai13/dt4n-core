#!/usr/bin/env python3
"""
measure_command_latency.py - Do COMMAND LATENCY end-to-end (Phase 4, Lesson 4.5).

Dinh nghia:
  t_click      = luc GUI message lenh qua Ditto.
  t_confirmed  = luc POLL thay twin state == ket qua mong doi.
  latency      = t_confirmed - t_click.

Day la do vong kin: message routing -> Command Agent thuc thi -> Sync Agent
observe trang thai that -> PATCH Ditto -> poll thay twin doi. Khong do rieng
response tuc thi, vi response do chi la bien nhan, khong phai ket qua mang.
"""

import time
import random
import uuid
from contextlib import nullcontext

import requests

from bridge.ditto_common import (DITTO_BASE_URL, DITTO_AUTH, NAMESPACE,
                                 make_thing_id_link, HTTP_TIMEOUT)
from measurements.measure_latency import poll_until_state
from measurements.stats import summarize, format_report

CONTROLLER = '%s:controller' % NAMESPACE
SETTLE_TIME = 2.0


def send_command(subject, target, params=None):
    """Gui 1 message lenh. Tra t_click ngay truoc khi POST.

    timeout=0 matches the dashboard's fire-and-forget transport. HTTP admission
    is not execution confirmation: the caller still polls the twin. A positive
    timeout additionally waits for a correlated reply which this SSE/outbox
    transport does not implement.
    """
    url = '%s/things/%s/inbox/messages/%s?timeout=0' % (
        DITTO_BASE_URL, CONTROLLER, subject)
    body = {'target': target}
    if params:
        body.update(params)
    headers = {
        'Content-Type': 'application/json',
        'correlation-id': str(uuid.uuid4()),
    }

    t_click = time.monotonic()
    try:
        requests.post(url, json=body, headers=headers, auth=DITTO_AUTH,
                      timeout=HTTP_TIMEOUT)
    except requests.exceptions.RequestException:
        # Response tuc thi khong phai doi tuong do. Neu message da toi Ditto,
        # poll ben duoi van la nguon xac nhan ket qua that.
        pass
    return t_click


def measure_command(net, h='h1', s='s1', n_trials=20, net_lock=None,
                    phase_period=0.0, seed=20260916):
    """Do command latency qua Ditto message n_trials lan."""
    link_tid = make_thing_id_link(h, s)
    latencies = []
    rng = random.Random(seed)

    for i in range(n_trials):
        # Reset truc tiep de dua link ve baseline nhanh, roi doi twin len 'up'.
        lock = net_lock if net_lock is not None else nullcontext()
        with lock:
            net.configLinkStatus(h, s, 'up')
        if poll_until_state(link_tid, 'up', timeout=5) is None:
            print('Trial %d: TIMEOUT (reset up chưa được xác nhận)' % (i + 1))
            continue
        time.sleep(SETTLE_TIME + rng.uniform(0, phase_period))

        t_click = send_command('disableLink', link_tid)
        t_confirmed = poll_until_state(link_tid, 'down', timeout=8)

        if t_confirmed is None:
            print('Trial %d: TIMEOUT (twin khong phan anh)' % (i + 1))
            continue

        lat = t_confirmed - t_click
        latencies.append(lat)
        print('Trial %2d: %.0f ms' % (i + 1, lat * 1000))

    lock = net_lock if net_lock is not None else nullcontext()
    with lock:
        net.configLinkStatus(h, s, 'up')
    return latencies


def main(net, n_trials=20, h='h1', s='s1', net_lock=None,
         phase_period=0.0, seed=20260916):
    print('Do command latency end-to-end: disableLink %s-%s, n=%d trials...'
          % (h, s, n_trials))
    lats = measure_command(net, h=h, s=s, n_trials=n_trials,
                           net_lock=net_lock, phase_period=phase_period, seed=seed)
    stats = summarize(lats)
    print('\n' + format_report(stats, label='(disableLink)',
                               title='Command Latency'))
    if stats and stats['max_ms'] < 2000:
        print('Dat target <2s o moi mau.')
    elif stats:
        print('Co mau vuot 2s (max=%.0fms) - can phan tich outlier.'
              % stats['max_ms'])
    if stats is not None:
        stats["latencies_sec"] = lats
        stats["trials_requested"] = n_trials
        stats["timeouts"] = n_trials - len(lats)
        stats["phase_period_s"] = phase_period
        stats["seed"] = seed
        stats["phase_mode"] = 'randomized_settle' if phase_period > 0 else 'fixed_settle'
    return stats
