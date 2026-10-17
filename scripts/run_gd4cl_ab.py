#!/usr/bin/env python3
"""
run_gd4cl_ab.py — Thí nghiệm A/B của vòng kín (Mục 5.7): bật và tắt controller khi h1 flood.

8 khối x 4 lượt, thứ tự ABBA/BAAB từ seed 20260920. Mỗi lượt h1 flood UDP 47 Mbps tới srv1
trong 120 s; biến chính là tốc độ gửi trung bình của h3 trong [t_flood + 2, t_flood + 122],
h2 (không dùng chung đường với luồng flood) là đối chứng. Nhánh "C" bật controller với
detector-release-2.1.0 và luật chọn ứng viên theo chiều (scripts/gd4cl_common.py), nhánh "B"
tắt controller. Thiết kế và tiêu chí ghi trước khi chạy ở results/report/gd4cl_prereg.json.

Cần root vì Mininet chạy trong tiến trình:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u scripts/run_gd4cl_ab.py --blocks 8
Trên một bản clone đã có results/report/gd4cl_ab.json, dùng scripts/chay_vong_kin.sh ab.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gd4cl_common import DirectionalViewProvider, live21_class, upper_bounds_bps  # noqa: E402
from phase7_live_common import LevelCounter  # noqa: E402
from phase8_ab_common import (  # noqa: E402
    FLOOD_S, PRIMARY_WINDOW, SECONDARY_WINDOW, SETTLE_S, TwinSampler,
    bind_send, block_order, run_trial,
)

from controller.twin_reader import TwinReader  # noqa: E402
from measurements import ab_stats  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / 'results/report/gd4cl_ab.json'
PREREG = 'results/report/gd4cl_prereg.json'
SEED = 20260920            # cùng seed với Phase 8
CONTROLLER_FILES = ('controller/localize.py', 'controller/policy.py', 'controller/runner.py',
                    'controller/twin_reader.py', 'scripts/phase8_ab_common.py',
                    'scripts/gd4cl_common.py')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--blocks', type=int, default=8)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--flood-s', type=float, default=FLOOD_S)
    args = parser.parse_args()
    if OUT.exists():
        print('[gd4cl] đã có receipt, không ghi đè:', OUT)
        return 1
    if not (C.ROOT / PREREG).exists():
        raise SystemExit('Chưa có tiêu chí ghi trước: %s' % PREREG)

    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ('logs/gd4cl_ab/%s'
                          % datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    audit_dir.mkdir(parents=True, exist_ok=True)

    Live21 = live21_class()
    per_trial_s = SETTLE_S + args.flood_s + 45
    budget_s = int(args.blocks * 4 * per_trial_s + 300)
    trials, orders = [], []
    with Live21(budget_s) as live:
        upper = upper_bounds_bps(live.release)
        detector = live.start_detector()
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,),
                         name='twin-sse', daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published('normal', timeout_s=120)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and 'h1-s1' not in twin.observed_bw():
            time.sleep(0.2)
        sampler = TwinSampler(twin).start()
        providers = []

        def factory():
            providers.append(DirectionalViewProvider(twin, upper))
            return providers[-1]

        try:
            for block in range(args.blocks):
                order = ['C' if arm == 'A' else arm for arm in block_order(rng)]
                orders.append(order)
                print('[gd4cl] khối %d: %s' % (block, ''.join(order)), flush=True)
                for index, arm in enumerate(order):
                    n_before = len(providers)
                    row = run_trial(live, twin, sampler, arm, block, index, rng,
                                    detector, audit_dir, view_provider_factory=factory,
                                    flood_s=args.flood_s)
                    if arm == 'C' and len(providers) > n_before:
                        row['directional'] = providers[-1].stats()
                    trials.append(row)
                    print('   b%d i%d %s primary=%s cmds=%s%s' % (
                        block, index, arm,
                        None if row['primary'] is None else round(row['primary'], 3),
                        row['secondary']['n_commands'] if not row['aborted'] else '-',
                        ' ABORTED' if row['aborted'] else ''), flush=True)
        finally:
            sampler.stop()
            stop_sse.set()
        release_version = live.release.version

    valid = [t for t in trials if not t['aborted'] and t['primary'] is not None]
    n_aborted = sum(1 for t in trials if t['aborted'])
    primary = ab_stats.summarise(valid, key='primary', arm_a='C', arm_b='B')
    secondary = {}
    for name in ('h3_window30', 'h2', 'h1', 'srv1_rx'):
        rows = [dict(t, value=t['secondary'][name]) for t in valid
                if t['secondary'][name] is not None]
        secondary[name] = ab_stats.summarise(rows, key='value', arm_a='C', arm_b='B')
    diffs = primary.get('block_diffs') or []
    content = {
        'experiment': 'GĐ4 A/B vòng kín: C (controller, luật theo chiều, detector 2.1) vs B (tắt)',
        'release': release_version,
        'prereg_sha256': C.sha256_file(C.ROOT / PREREG),
        'code_sha256': {p: C.sha256_file(C.ROOT / p) for p in CONTROLLER_FILES},
        'seed': args.seed,
        'block_orders': [''.join(o) for o in orders],
        'primary_window_s': list(PRIMARY_WINDOW),
        'secondary_window_s': list(SECONDARY_WINDOW),
        'n_trials': len(trials),
        'n_aborted': n_aborted,
        'abort_fraction': round(n_aborted / len(trials), 4) if trials else None,
        'measurement_valid': bool(trials) and n_aborted / len(trials) <= 0.20,
        'primary': primary,
        'blocks_c_greater': (sum(1 for d in diffs if d is not None and d > 0)
                             if diffs else None),
        'protection_pass': bool(primary['mean_diff'] is not None
                                and primary['ci95'][0] is not None
                                and primary['ci95'][0] > 0),
        'secondary': secondary,
        'negative_control_h2_ci_contains_zero': bool(
            secondary['h2']['ci95'][0] is not None
            and secondary['h2']['ci95'][0] <= 0 <= secondary['h2']['ci95'][1]),
        'log_counts': counter.counts,
        'trials': trials,
    }
    C.atomic_json(OUT, {
        'content': content,
        'content_sha256': C.sha256_bytes(C.canonical_json(content).encode()),
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    })
    print('wrote', OUT)
    print('primary:', json.dumps(primary, ensure_ascii=False))
    print('bảo vệ:', 'ĐẠT' if content['protection_pass'] else 'KHÔNG ĐẠT',
          '| khối C > B:', content['blocks_c_greater'],
          '| h2 chứa 0:', content['negative_control_h2_ci_contains_zero'],
          '| hủy:', n_aborted, '/', len(trials))
    return 0


if __name__ == '__main__':
    sys.exit(main())
