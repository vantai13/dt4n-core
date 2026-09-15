#!/usr/bin/env python3
"""
measure_latency.py — Đo SYNC LATENCY (Lesson 2.4 Phần 5). Chạy cùng net + Ditto.

ĐỊNH NGHĨA (Phần 5.1 - phải chính xác, hội đồng sẽ truy):
  t_event     = lúc GỌI lệnh link down trên Mininet.
  t_reflected = lúc POLL Ditto thấy state == 'down'.
  latency = t_reflected - t_event.
  BAO GỒM: chu kỳ polling + collect + PATCH + propagation Ditto.
  -> với polling 1s, latency thực trong khoảng [0,1s]+overhead -> target <2s hợp lý.

CÁCH ĐO (Phần 5.2):
  - Poll Ditto với interval NHỎ (50ms) -> không tự thêm trễ đáng kể vào số đo.
  - Dùng time.monotonic() (KHÔNG time.time() - NTP nhảy lùi -> số âm).
  - Reset link 'up' + chờ đồng bộ TRƯỚC mỗi trial (tránh mẫu nhiễu).
"""

import time
import random
from contextlib import nullcontext

import requests

from bridge.ditto_common import (DITTO_BASE_URL, DITTO_AUTH,
                                 make_thing_id_link, HTTP_TIMEOUT)
from measurements.stats import summarize, format_report

POLL_INTERVAL = 0.05      # 50ms - đủ mịn để không thêm trễ đáng kể vào số đo
SETTLE_TIME   = 2.0       # giây chờ twin ổn định giữa các trial


def poll_until_state(thing_id, expected, timeout=5.0):
    """Poll Ditto đến khi state == expected. Trả t_reflected (monotonic) hoặc None."""
    url = '%s/things/%s/features/status/properties/state' % (DITTO_BASE_URL, thing_id)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, auth=DITTO_AUTH, timeout=1)
            # endpoint property trả về giá trị JSON thuần, vd chuỗi "down"
            if r.status_code == 200 and r.json() == expected:
                return time.monotonic()
        except requests.exceptions.RequestException:
            pass
        time.sleep(POLL_INTERVAL)
    return None


def measure_link_down(net, h='h1', s='s1', n_trials=50, net_lock=None,
                      phase_period=0.0, seed=20260915):
    """Đo latency sự kiện link down n_trials lần. Trả list latency (giây)."""
    link_tid = make_thing_id_link(h, s)
    latencies = []
    rng = random.Random(seed)

    for i in range(n_trials):
        # --- reset: đảm bảo link up + twin đã đồng bộ 'up' (tránh nhiễu) ---
        lock = net_lock if net_lock is not None else nullcontext()
        with lock:
            net.configLinkStatus(h, s, 'up')
        if poll_until_state(link_tid, 'up', timeout=5) is None:
            print('Trial %d: TIMEOUT (reset up chưa được xác nhận)' % (i + 1))
            continue
        time.sleep(SETTLE_TIME + rng.uniform(0, phase_period))

        # --- inject sự kiện + bấm giờ ---
        t_event = time.monotonic()
        lock = net_lock if net_lock is not None else nullcontext()
        with lock:
            net.configLinkStatus(h, s, 'down')
        t_reflected = poll_until_state(link_tid, 'down', timeout=5)

        if t_reflected is None:
            print('Trial %d: TIMEOUT (twin không phản ánh)' % (i + 1))
            continue
        lat = t_reflected - t_event
        latencies.append(lat)
        print('Trial %2d: %.0f ms' % (i + 1, lat * 1000))

    # khôi phục link
    lock = net_lock if net_lock is not None else nullcontext()
    with lock:
        net.configLinkStatus(h, s, 'up')
    return latencies


def main(net, n_trials=50, h='h1', s='s1', net_lock=None,
         phase_period=0.0, seed=20260915):
    print('Đo sync latency: link %s-%s down, n=%d trials...' % (h, s, n_trials))
    lats = measure_link_down(net, h=h, s=s, n_trials=n_trials,
                             net_lock=net_lock, phase_period=phase_period, seed=seed)
    stats = summarize(lats)
    print('\n' + format_report(stats, label='(link-down)'))
    # kiểm target
    if stats and stats['max_ms'] < 2000:
        print('✅ Đạt target <2s ở MỌI mẫu.')
    elif stats:
        print('⚠ Có mẫu vượt 2s (max=%.0fms) — phân tích outlier.' % stats['max_ms'])
    if stats is not None:
        stats["latencies_sec"] = lats
        stats["trials_requested"] = n_trials
        stats["timeouts"] = n_trials - len(lats)
        stats["phase_period_s"] = phase_period
        stats["seed"] = seed
        stats["phase_mode"] = 'randomized_settle' if phase_period > 0 else 'fixed_settle'
    return stats
