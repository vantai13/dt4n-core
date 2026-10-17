#!/usr/bin/env python3
"""
kiem_tra_moi_truong.py — Kiểm máy đã đủ điều kiện chạy lại kết quả của báo cáo chưa.

    .venv/bin/python scripts/kiem_tra_moi_truong.py            # chỉ phần offline
    .venv/bin/python scripts/kiem_tra_moi_truong.py --testbed  # thêm phần testbed

Mỗi dòng in ĐẠT hoặc THIẾU kèm cách sửa. Mã thoát 1 nếu có mục THIẾU.
Không sửa gì trên máy.
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

MONGO_MIN_MIB = 1000
results = []


def row(ok: bool, what: str, fix: str = '') -> None:
    results.append(ok)
    print('%-6s %s%s' % ('ĐẠT' if ok else 'THIẾU', what, '' if ok else '\n       -> ' + fix))


def run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def offline() -> None:
    print('== Phần offline (tái lập số liệu, không cần testbed)')
    row(sys.version_info >= (3, 11), 'Python %s' % sys.version.split()[0],
        'dùng Python 3.11 trở lên để tạo .venv')
    in_venv = sys.prefix != sys.base_prefix
    row(in_venv, 'đang chạy trong môi trường ảo (%s)' % sys.prefix,
        'python3 -m venv .venv && .venv/bin/pip install -r requirements-phase6r.lock.v2.txt, '
        'rồi chạy script bằng .venv/bin/python')
    for module in ('numpy', 'pandas', 'sklearn', 'requests', 'matplotlib', 'pytest'):
        try:
            importlib.import_module(module)
            row(True, 'thư viện %s' % module)
        except ImportError:
            row(False, 'thư viện %s' % module,
                '.venv/bin/pip install -r requirements-phase6r.lock.v2.txt')
    for rel in ('models/detector-release-2.1.0.json', 'data/phase5/gd4r/raw',
                'results/report/gd4_acceptance_v21.json'):
        row((ROOT / rel).exists(), 'có %s' % rel, 'clone lại repo đầy đủ (git clone, không dùng --depth)')


def testbed() -> None:
    print('== Phần testbed (Mininet, Ryu, Ditto)')
    row(sys.platform.startswith('linux'), 'hệ điều hành Linux', 'testbed chỉ chạy trên Linux')
    code, _ = run(['sudo', '-n', 'true'])
    row(code == 0, 'sudo không hỏi mật khẩu (sudo -n)',
        'các runner tự gọi sudo -n; thêm quyền NOPASSWD cho người dùng này, hoặc chạy '
        '"sudo -v" ngay trước khi chạy script')
    try:
        import mininet.net  # noqa: F401  (thư mục mininet/ của repo tự nối sang Mininet hệ thống)
        row(True, 'thư viện Mininet')
    except ImportError:
        row(False, 'thư viện Mininet', 'cài Mininet 2.3 cho Python hệ thống (sudo apt install mininet '
            'hoặc mininet/util/install.sh -n)')
    for tool, fix in (('mnexec', 'cài Mininet đầy đủ (có mnexec)'),
                      ('ovs-vsctl', 'sudo apt install openvswitch-switch'),
                      ('iperf', 'sudo apt install iperf (iperf v2)'),
                      ('docker', 'cài Docker Engine và quyền chạy docker')):
        row(shutil.which(tool) is not None, 'lệnh %s' % tool, fix)
    ryu = os.environ.get('DT4N_RYU') or shutil.which('ryu-manager')
    row(bool(ryu) and os.access(ryu, os.X_OK), 'ryu-manager (%s)' % ryu,
        'cài Ryu 4.34 trong một môi trường Python riêng (ví dụ conda env sdn_net, Python 3.9), '
        'rồi export DT4N_RYU=/đường/dẫn/tới/ryu-manager')
    with socket.socket() as s:
        free = s.connect_ex(('127.0.0.1', 6653)) != 0
    row(free, 'cổng 6653 còn trống (chưa có Ryu khác chạy)',
        'dừng Ryu đang chạy hoặc chạy "sudo mn -c" trước')
    try:
        import requests
        from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL
        r = requests.get(DITTO_BASE_URL + '/things?ids=org.dt4n:detector', auth=DITTO_AUTH, timeout=10)
        row(r.status_code in (200, 404), 'Ditto trả lời ở %s (HTTP %s)' % (DITTO_BASE_URL, r.status_code),
            'cp ditto/nginx.htpasswd.example ditto/nginx.htpasswd && (cd ditto && docker compose up -d)')
    except Exception as exc:
        row(False, 'Ditto trả lời (%s)' % type(exc).__name__,
            'cp ditto/nginx.htpasswd.example ditto/nginx.htpasswd && (cd ditto && docker compose up -d)')
    from phase8_infra_health import mongo_container, mongo_memory
    used, limit = mongo_memory()
    row(limit is not None and limit >= MONGO_MIN_MIB,
        'MongoDB %s có trần bộ nhớ %s MiB' % (mongo_container(), limit),
        'cần >= 1 GiB: dựng lại Ditto bằng ditto/docker-compose.yml của repo '
        '(cd ditto && docker compose up -d --force-recreate mongodb), hoặc '
        'docker update --memory 1g --memory-swap 2g <tên container mongodb>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--testbed', action='store_true')
    args = ap.parse_args()
    offline()
    if args.testbed:
        testbed()
    bad = results.count(False)
    print('\n%d mục thiếu.' % bad if bad else '\nĐủ điều kiện.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
