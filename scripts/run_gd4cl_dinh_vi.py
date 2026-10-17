#!/usr/bin/env python3
"""
run_gd4cl_dinh_vi.py — Phép thử định vị của vòng kín (Mục 5.7): 4 kịch bản x 5 lượt.

Dùng run_one và main của run_gd4cl_c1.py (detector 2.1, luật chọn ứng viên theo chiều, bốn
kịch bản, seed 20260921, cách chấm theo results/report/gd4cl_prereg.json), cộng hai bước
chuẩn bị giữa các lượt để mọi lượt bắt đầu từ cùng một trạng thái:
  - Tải nền được khởi động lại tới khi đủ 4 tiến trình iperf client (h1, h2, h3 TCP và
    srv1 -> srv2 UDP) và cả ba máy khách gửi ít nhất 1,5 Mbps trên twin trong 3 giây liên
    tiếp (tối đa 5 lần thử).
  - Nếu Ditto không khỏe hoặc MongoDB dùng từ 95% trần bộ nhớ, MongoDB được khởi động lại
    trước lượt kế tiếp (không bao giờ giữa một lượt) và sự kiện được ghi vào dòng của lượt.

  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u scripts/run_gd4cl_dinh_vi.py

Trên một bản clone đã có results/report/gd4cl_c1.json, dùng scripts/chay_vong_kin.sh c1.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import phase8_infra_health as health  # noqa: E402
import run_gd4cl_c1 as base  # noqa: E402
from gd4cl_common import twin_client_tx  # noqa: E402

BACKGROUND = dict(scenario='normal', normal_rate='2M', server_bg_rate=2.0,
                  duration=6 * 3600)
EXPECTED_CLIENTS = 4               # h1, h2, h3 TCP và srv1 -> srv2 UDP
MIN_CLIENT_BPS = 1.5e6 / 8         # 1,5 Mbps tính bằng byte/s
READY_TIMEOUT_S = 45
MAX_BACKGROUND_TRIES = 5
MONGO_RESTART_FRACTION = 0.95
HEALTH_WAIT_S = 240

_original_run_one = base.run_one
_pending_recoveries: list[dict] = []


def iperf_clients() -> list[str]:
    ps = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True).stdout
    return sorted(line for line in ps.splitlines()
                  if line.startswith('iperf -c') and '-p 5003' not in line)


def clients_sending(twin) -> bool:
    tx = twin_client_tx(twin)
    return all(tx.get(c, 0.0) >= MIN_CLIENT_BPS for c in ('h1', 'h2', 'h3'))


def ensure_background(live, twin) -> dict:
    tries = []
    for attempt in range(1, MAX_BACKGROUND_TRIES + 1):
        with live.env.net_lock:
            live.env.start_profile_background(**BACKGROUND)
        time.sleep(3.0)
        clients = iperf_clients()
        ok_rate, calm = False, 0
        if len(clients) >= EXPECTED_CLIENTS:
            deadline = time.monotonic() + READY_TIMEOUT_S
            while time.monotonic() < deadline:
                calm = calm + 1 if clients_sending(twin) else 0
                if calm >= 3:
                    ok_rate = True
                    break
                time.sleep(1.0)
        tries.append({'attempt': attempt, 'clients': len(clients), 'sending': ok_rate})
        if ok_rate and len(iperf_clients()) >= EXPECTED_CLIENTS:
            return {'ok': True, 'tries': tries}
    return {'ok': False, 'tries': tries}


def check_with_recovery(raise_on_fail=False) -> dict:
    report = health.check(raise_on_fail=False)
    fraction = report.get('mongo_fraction')
    if report['healthy'] and (fraction is None or fraction < MONGO_RESTART_FRACTION):
        return report
    event = {'before': report, 'at': time.time()}
    subprocess.run(['docker', 'restart', health.mongo_container()],
                   capture_output=True, text=True, timeout=120, check=False)
    deadline = time.monotonic() + HEALTH_WAIT_S
    after = report
    while time.monotonic() < deadline:
        time.sleep(5.0)
        after = health.check(raise_on_fail=False)
        if after['healthy']:
            break
    event['after'] = after
    _pending_recoveries.append(event)
    print('[dinh-vi] khởi động lại MongoDB: %s -> %s' % (
        report.get('mongo_fraction'), after.get('mongo_fraction')), flush=True)
    return after


def run_one_ready(live, twin, detector, audit_dir, name, spec, flood_s, rng, index, upper):
    recoveries = list(_pending_recoveries)
    _pending_recoveries.clear()
    background = ensure_background(live, twin)
    print('[dinh-vi] %02d tải nền: %s' % (index, background), flush=True)
    if not background['ok']:
        return {'scenario': name, 'index': index, 'outcome': 'aborted',
                'detail': {'background': background}, 'infra_recovery': recoveries}
    row = _original_run_one(live, twin, detector, audit_dir, name, spec, flood_s, rng,
                            index, upper)
    row['background_ready'] = background
    row['infra_recovery'] = recoveries
    return row


if __name__ == '__main__':
    base.run_one = run_one_ready
    base.infra_check = check_with_recovery
    sys.exit(base.main())
