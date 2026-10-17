#!/usr/bin/env python3
"""
diag_gd4cl_c1.py — Chẩn đoán vì sao detector kẹt ở mức act trong C1 lần 2 (sai lệch 5).

KHÔNG phải thí nghiệm, không ghi results/report. Chạy lại đúng 3 lượt đầu của C1 (cùng seed
20260921, cùng thứ tự: stop_in_probe, h1_srv2, h3_srv1) bằng chính run_one của
run_gd4cl_c1.py, rồi sau lượt thứ ba theo dõi thêm vài phút. Mỗi giây ghi những cột detector
thấy vượt biên (giá trị, biên dưới, biên trên), k_indicator, k_rate, excess, residual và tốc
độ của các host. Sau mỗi lượt chụp danh sách tiến trình iperf và log iperf trong /tmp.

  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u scripts/diag_gd4cl_c1.py

Ra: logs/gd4cl_diag/<thời điểm>/ (ticks.jsonl, ps_*.txt, iperf_*.log, tom_tat.json).
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from gd4cl_common import live21_class, upper_bounds_bps  # noqa: E402
from phase8_ab_common import TwinSampler, bind_send, require_clean  # noqa: E402
from run_phase8_c1_control import CLIENTS, SERVERS, hard_cleanup, scenarios  # noqa: E402
from run_gd4cl_c1 import SEED, run_one  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402

N_TRIALS = 3
WATCH_AFTER_S = 300
HOST_COLS = re.compile(r'^host-(h1|h2|h3|srv1|srv2)\.traffic\.(txRate|rxRate)$')


def hook_scorer(runner, out_path: Path, phase: dict):
    """Bọc scorer.observe để ghi mỗi giây những gì detector thấy."""
    scorer = runner.scorer
    original = scorer.observe
    model = scorer.model
    cols = list(model.families['primary'])
    low, high, _ = model._vec['primary']
    fh = out_path.open('a', encoding='utf-8')

    def observe(snapshot):
        reading = original(snapshot)
        try:
            row = {'t': round(time.time(), 2), 'phase': phase.get('name'),
                   'status': reading.status, 'act': reading.act,
                   'suspect': reading.suspect, 'k_indicator': reading.k_indicator,
                   'k_rate': reading.k_rate, 'excess': reading.excess,
                   'cons_r_max': reading.cons_r_max, 'cons_switch': reading.cons_switch,
                   'cons_alarm': reading.cons_alarm, 'cause': reading.cause}
            frame = scorer.frame_of(snapshot)
            for column in cols:
                if column not in frame.columns:
                    frame[column] = float('nan')
            values = model._matrix(frame, cols)[0]
            index = {c: i for i, c in enumerate(cols)}
            row['violating'] = [
                {'col': c, 'value': float(values[index[c]]), 'low': float(low[index[c]]),
                 'high': float(high[index[c]])}
                for c in reading.violating if c in index]
            row['hosts'] = {c: (None if frame[c].isna().iloc[0] else float(frame[c].iloc[0]))
                            for c in frame.columns if HOST_COLS.match(c)}
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
            fh.flush()
        except Exception as exc:  # chẩn đoán không được làm hỏng detector
            fh.write(json.dumps({'t': time.time(), 'hook_error': repr(exc)}) + '\n')
            fh.flush()
        return reading

    scorer.observe = observe
    return fh


def snapshot_processes(out_dir: Path, tag: str) -> None:
    ps = subprocess.run(['ps', '-eo', 'pid,etimes,args'], capture_output=True, text=True).stdout
    lines = [line for line in ps.splitlines() if 'iperf' in line and 'diag_gd4cl' not in line]
    (out_dir / ('ps_%s.txt' % tag)).write_text('\n'.join(lines) + '\n')
    for log in Path('/tmp').glob('iperf_*.log'):
        shutil.copy2(log, out_dir / ('%s_%s' % (tag, log.name)))
    for log in Path('/tmp').glob('flood_*.log'):
        shutil.copy2(log, out_dir / ('%s_%s' % (tag, log.name)))


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = ROOT / 'logs/gd4cl_diag' / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    specs, reps, flood_s = scenarios()
    rng = random.Random(SEED)
    plan = []
    for _ in range(reps):
        block = list(specs)
        rng.shuffle(block)
        plan += block
    plan = plan[:N_TRIALS]
    phase = {'name': 'start'}
    summary = {'plan': plan, 'trials': [], 'clean_checks': []}
    Live21 = live21_class()
    with Live21(N_TRIALS * 400 + WATCH_AFTER_S + 600) as live:
        upper = upper_bounds_bps(live.release)
        detector = live.start_detector()
        fh = hook_scorer(detector, out_dir / 'ticks.jsonl', phase)
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,), name='twin-sse',
                         daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published('normal', timeout_s=120)
        sampler = TwinSampler(twin, hosts=CLIENTS + SERVERS).start()
        snapshot_processes(out_dir, 'truoc')
        try:
            for index, name in enumerate(plan):
                phase['name'] = '%02d_%s' % (index, name)
                row = run_one(live, twin, detector, out_dir, name, specs[name], flood_s,
                              rng, index, upper)
                summary['trials'].append({k: row.get(k) for k in
                                          ('index', 'scenario', 'outcome', 'inject_links',
                                           'detail')})
                print('[diag] %02d %-14s -> %s' % (index, name, row['outcome']), flush=True)
                snapshot_processes(out_dir, 'sau_%02d' % index)
            phase['name'] = 'sau_cung'
            ok, detail = hard_cleanup(live, twin, 'diag')
            summary['clean_checks'].append({'after': 'hard_cleanup', 'ok': ok, 'detail': detail})
            print('[diag] hard_cleanup ->', ok, detail, flush=True)
            snapshot_processes(out_dir, 'sau_cleanup')
            deadline = time.monotonic() + WATCH_AFTER_S
            while time.monotonic() < deadline:
                ok, detail = require_clean(live, twin, timeout_s=30)
                summary['clean_checks'].append({'t': time.time(), 'ok': ok, 'detail': detail})
                print('[diag] require_clean ->', ok, detail, flush=True)
                if ok:
                    break
            snapshot_processes(out_dir, 'cuoi')
        finally:
            sampler.stop()
            stop_sse.set()
            fh.close()
    (out_dir / 'tom_tat.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print('[diag] xong ->', out_dir, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
