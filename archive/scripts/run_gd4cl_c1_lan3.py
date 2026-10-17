#!/usr/bin/env python3
"""
run_gd4cl_c1_lan3.py — C1 lần 3: như run_gd4cl_c1.py, thêm khởi động lại tải nền trước mỗi lượt.

Lý do (results/gd4/deviation_6_tai_nen.md): khi máy khách flood bị giới hạn 7 Mbps, luồng UDP
flood của chính nó chiếm hết phần băng thông còn lại, luồng TCP nền của máy đó hết thời gian
chờ ("write failed: Connection timed out") và iperf thoát. Bộ tạo tải không bật lại, nên các
lượt sau chạy trên một mạng thiếu luồng nền. Với detector 2.1, h1 và h3 không gửi làm khoảng
18 cột tốc độ nằm dưới biên, sát ngưỡng K = 18, và ở C1 lần 2 đã làm detector kẹt ở act.

Thay đổi DUY NHẤT: trước hard_cleanup của mỗi lượt, gọi lại start_profile_background (cùng
tham số như lúc dựng môi trường) để mọi lượt bắt đầu với đủ ba luồng TCP và luồng UDP
srv1 -> srv2. Detector, luật chọn ứng viên, kịch bản, seed, thứ tự và cách chấm giữ nguyên
(gọi lại run_one và main của run_gd4cl_c1.py). Mỗi lượt ghi thêm số tiến trình iperf client
còn sống trước và sau khi khởi động lại.

  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u scripts/run_gd4cl_c1_lan3.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import run_gd4cl_c1 as base  # noqa: E402

BACKGROUND = dict(scenario='normal', normal_rate='2M', server_bg_rate=2.0,
                  duration=6 * 3600)
EXPECTED_CLIENTS = 4          # h1, h2, h3 TCP và srv1 -> srv2 UDP
_original_run_one = base.run_one


def iperf_clients() -> list[str]:
    ps = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True).stdout
    return sorted(line for line in ps.splitlines()
                  if line.startswith('iperf -c') and '-p 5003' not in line)


def run_one_fresh(live, twin, detector, audit_dir, name, spec, flood_s, rng, index, upper):
    before = iperf_clients()
    with live.env.net_lock:
        live.env.start_profile_background(**BACKGROUND)
    time.sleep(2.0)
    after = iperf_clients()
    row = _original_run_one(live, twin, detector, audit_dir, name, spec, flood_s, rng,
                            index, upper)
    row['background_restart'] = {'clients_before': len(before), 'clients_after': len(after),
                                 'expected': EXPECTED_CLIENTS, 'after': after}
    return row


if __name__ == '__main__':
    base.run_one = run_one_fresh
    sys.exit(base.main())
