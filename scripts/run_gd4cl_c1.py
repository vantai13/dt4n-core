#!/usr/bin/env python3
"""
run_gd4cl_c1.py — Phần lõi của phép thử định vị (Mục 5.7), dùng bởi run_gd4cl_dinh_vi.py.

Bốn kịch bản trong results/report/phase8_closure_prereg.json -> E1_c1_control (h3 flood srv1,
h2 flood srv2, h1 flood srv2, dừng flood khi controller đang gỡ thử), 5 lượt mỗi kịch bản,
flood 60 s, thứ tự xáo theo khối từ seed 20260921. Mỗi lượt được xếp vào một trong ba kết cục:
chọn đúng thủ phạm, sai mục tiêu, không hành động. Detector là detector-release-2.1.0 và
controller dùng luật chọn ứng viên theo chiều (scripts/gd4cl_common.py).

Chạy phép thử bằng scripts/run_gd4cl_dinh_vi.py (thêm bước chuẩn bị tải nền giữa các lượt).
"""
from __future__ import annotations

import argparse
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
from phase8_ab_common import SETTLE_S, TwinSampler, bind_send, make_controller  # noqa: E402
from phase8_infra_health import check as infra_check  # noqa: E402
from run_phase8_c1_control import (  # noqa: E402
    CLIENTS, FLOOD_RATE_MBPS, SERVERS, classify_trial, hard_cleanup, scenarios,
)

from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / 'results/report/gd4cl_c1.json'
PREREG = 'results/report/gd4cl_prereg.json'
SEED = 20260921            # cùng seed với Phase 8


def run_one(live, twin, detector, audit_dir, name, spec, flood_s, rng, index, upper):
    ok, detail = hard_cleanup(live, twin, '%s%d' % (name, index))
    if not ok:
        return {'scenario': name, 'index': index, 'outcome': 'aborted', 'detail': detail}
    time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))
    audit_path = audit_dir / ('%02d_%s.jsonl' % (index, name))
    provider = DirectionalViewProvider(twin, upper)
    controller = make_controller(twin, detector, audit_path, view_provider=provider)
    controller.bootstrap_safe_state()
    thread = threading.Thread(target=controller.run_forever, name='control', daemon=True)
    thread.start()
    flood = TrafficFlood(spec['src'], spec['dst'], FLOOD_RATE_MBPS)
    t_flood = time.time()
    stop_offset = None
    with live.env.net_lock:
        flood.apply(live.env.net)
    if name == 'stop_in_probe':
        deadline = time.monotonic() + flood_s + 60
        while time.monotonic() < deadline and controller.cstate.mode != 'PROBING':
            time.sleep(0.05)
        stop_offset = rng.uniform(0.0, 3.0)
        time.sleep(stop_offset)
    else:
        time.sleep(flood_s)
    with live.env.net_lock:
        flood.revert(live.env.net)
    time.sleep(30.0)
    controller.shutdown()
    thread.join(10)
    row = classify_trial(audit_path, spec['culprit'])
    row.update({'scenario': name, 'index': index, 't_flood': t_flood, 'src': spec['src'],
                'dst': spec['dst'], 'culprit': spec['culprit'], 'victim': spec.get('victim'),
                'stop_offset_s': stop_offset, 'directional': provider.stats(),
                'audit': str(audit_path.relative_to(C.ROOT))})
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=SEED)
    args = ap.parse_args()
    if OUT.exists():
        print('đã có receipt, không ghi đè:', OUT)
        return 1
    if not (C.ROOT / PREREG).exists():
        raise SystemExit('Chưa có tiêu chí ghi trước: %s' % PREREG)
    specs, reps, flood_s = scenarios()
    rng = random.Random(args.seed)
    plan = []
    for _ in range(reps):
        block = list(specs)
        rng.shuffle(block)
        plan += block
    health_before = infra_check(raise_on_fail=True)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ('logs/gd4cl_c1/%s'
                          % datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    audit_dir.mkdir(parents=True, exist_ok=True)
    Live21 = live21_class()
    trials = []
    with Live21(int(len(plan) * (SETTLE_S + flood_s + 330) + 600)) as live:
        upper = upper_bounds_bps(live.release)
        detector = live.start_detector()
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,), name='twin-sse',
                         daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published('normal', timeout_s=120)
        sampler = TwinSampler(twin, hosts=CLIENTS + SERVERS).start()
        try:
            for index, name in enumerate(plan):
                health = infra_check(raise_on_fail=False)
                if not health['healthy']:
                    trials.append({'scenario': name, 'index': index, 'outcome': 'aborted',
                                   'detail': {'infra': health}})
                    continue
                row = run_one(live, twin, detector, audit_dir, name, specs[name], flood_s,
                              rng, index, upper)
                trials.append(row)
                print('[gd4cl-c1] %02d %-14s -> %s %s' % (
                    index, name, row['outcome'], row.get('inject_links')), flush=True)
        finally:
            hard_cleanup(live, twin, 'final')
            sampler.stop()
            stop_sse.set()
        release_version = live.release.version
    done = [t for t in trials if t['outcome'] != 'aborted']
    by = {name: {k: sum(1 for t in done if t['scenario'] == name and t['outcome'] == k)
                 for k in ('correct_latch', 'wrong_target', 'silent')} for name in specs}
    n_wrong = sum(v['wrong_target'] for v in by.values())
    n_nonh1_correct = sum(1 for t in done
                          if t['outcome'] == 'correct_latch' and t['culprit'] != 'h1')
    content = {
        'experiment': 'GĐ4 định vị: detector 2.1 + luật chọn ứng viên theo chiều',
        'release': release_version,
        'prereg_sha256': C.sha256_file(C.ROOT / PREREG),
        'policy_sha256': C.sha256_file(C.ROOT / 'controller/policy.py'),
        'localize_sha256': C.sha256_file(C.ROOT / 'controller/localize.py'),
        'gd4cl_common_sha256': C.sha256_file(C.ROOT / 'scripts/gd4cl_common.py'),
        'seed': args.seed,
        'plan': plan,
        'health_before': health_before,
        'n_trials': len(trials),
        'n_aborted': len(trials) - len(done),
        'by_scenario': by,
        'n_wrong_target': n_wrong,
        'n_correct_nonh1_culprit': n_nonh1_correct,
        'localization_pass': n_wrong == 0,
        'broad_scope': n_wrong == 0 and n_nonh1_correct >= 3,
        'log_counts': counter.counts,
        'trials': trials,
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    C.atomic_json(OUT, {'content': content, 'content_sha256': C.sha256_bytes(
        C.canonical_json(content).encode())})
    print('wrote', OUT)
    print('theo kịch bản:', by)
    print('sai mục tiêu:', n_wrong, '| chọn đúng thủ phạm khác h1:', n_nonh1_correct,
          '| định vị:', 'ĐẠT' if n_wrong == 0 else 'KHÔNG ĐẠT')
    return 0


if __name__ == '__main__':
    sys.exit(main())
