#!/usr/bin/env python3
"""
gd4_s1s2_excess.py — GĐ4: vì sao envelope bỏ sót sự cố giảm băng thông trên link s1–s2.

Chạy lại detector (bản 2.1 và bản 1.0.0, cùng FastOnlineScorer của lượt chấm) trên năm run
giảm băng thông s1–s2 của tập nghiệm thu gd4r và ghi, cho từng run:
  - excess lớn nhất trong các giây 21–39 (đang có sự cố, trước giây gỡ 40);
  - số giây có cột chỉ báo vượt biên (k_I > 0) trong các giây 21–39;
  - excess ở giây 40 (giây gỡ sự cố) và giây 41;
  - số giây trong 21–40 mà tốc độ gửi của h1, h3 xuống dưới biên dưới;
  - độ rộng vùng bình thường của tốc độ gửi từng máy khách (Mbps).
Chỉ mô tả cơ chế, không đổi kết quả nào của Chương 5.

    python3 scripts/gd4_s1s2_excess.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402
from ml.acceptance_guard import SnapshotReader  # noqa: E402
from ml.flatten import flatten_snapshot  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from ml.serve_fast import FastOnlineScorer  # noqa: E402

OUT = C.ROOT / 'results/report/gd4_s1s2_excess.json'
RAW = C.ROOT / 'data/phase5/gd4r/raw'
RELEASES = {'v21': 'models/detector-release-2.1.0.json', 'v1': 'models/detector-release-1.0.0.json'}
CLIENTS = ('h1', 'h2', 'h3')
INJECT, REVERT = 20, 40


def runs(contract: dict) -> list[dict]:
    return sorted((r for r in contract['runs']
                   if r['group'] == 'RD' and r['fault_target'] == 's1-s2'),
                  key=lambda r: r['run_id'])


def analyse(release: DetectorRelease, record: dict, snapshots: list) -> dict:
    scorer = FastOnlineScorer(release.model,
                              expected_collector_version=release.content['collector_version'],
                              conservation=release.conservation, conservation_mode='shadow')
    bounds = release.model._c['bounds']
    by_tick, below = {}, {c: 0 for c in CLIENTS}
    for snapshot in snapshots:
        reading = scorer.observe(snapshot)
        if reading.tick is None:
            continue
        by_tick[reading.tick] = reading
        if INJECT < reading.tick <= REVERT:
            flat = flatten_snapshot(snapshot)
            for c in CLIENTS:
                column = 'host-%s.traffic.txRate' % c
                value = flat.get(column)
                if isinstance(value, (int, float)) and value < bounds[column]['min']:
                    below[c] += 1
    window = [by_tick[t] for t in range(INJECT + 1, REVERT) if t in by_tick]
    excess = [r.excess for r in window if r.excess is not None]
    return {
        'excess_max_21_39': max(excess) if excess else None,
        'ticks_with_indicator_violation_21_39': sum((r.k_indicator or 0) > 0 for r in window),
        'k_indicator_max_21_39': max((r.k_indicator or 0) for r in window) if window else None,
        'excess_tick_40': by_tick[REVERT].excess if REVERT in by_tick else None,
        'excess_tick_41': by_tick[REVERT + 1].excess if REVERT + 1 in by_tick else None,
        'below_lower_bound_ticks_21_40': below,
        'n_ticks_21_39': len(window),
        'threshold_E': float(release.model._c['thresholds']['primary']['E']),
    }


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    contract = json.loads((C.ROOT / 'results/report/gd4r_contract.json').read_text())
    manifest = json.loads((C.ROOT / 'results/report/gd4r_manifest.json').read_text())
    content = {'note': 'Chỉ mô tả cơ chế bỏ sót trên s1–s2; không đổi kết quả của Chương 5.',
               'runs': {}, 'client_rate_width_mbps': {}}
    for name, path in RELEASES.items():
        release = DetectorRelease.load(C.ROOT / path)
        bounds = release.model._c['bounds']
        content['client_rate_width_mbps'][name] = {
            c: round((bounds['host-%s.traffic.txRate' % c]['max'] -
                      bounds['host-%s.traffic.txRate' % c]['min']) * 8 / 1e6, 3)
            for c in CLIENTS}
        reader = SnapshotReader({k: v['sha256'] for k, v in manifest['runs'].items()})
        for record in runs(contract):
            rid = record['run_id']
            snaps = reader.read_once(rid, RAW / (rid + '.jsonl'))
            content['runs'].setdefault(rid, {})[name] = analyse(release, record, snaps)
    content['written_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    C.atomic_json(OUT, {'content': content, 'content_sha256': C.sha256_bytes(
        C.canonical_json(content).encode('utf-8'))})
    for name in RELEASES:
        print('== %s, E = %.3f, độ rộng vùng tốc độ máy khách (Mbps) %s' % (
            name, next(iter(content['runs'].values()))[name]['threshold_E'],
            content['client_rate_width_mbps'][name]))
        for rid, row in content['runs'].items():
            x = row[name]
            print('%-34s excess max 21-39 %6.2f | giây có chỉ báo %d | excess g40 %6.2f g41 %6.2f'
                  ' | dưới biên dưới 21-40 h1 %2d h3 %2d' % (
                      rid, x['excess_max_21_39'], x['ticks_with_indicator_violation_21_39'],
                      x['excess_tick_40'], x['excess_tick_41'],
                      x['below_lower_bound_ticks_21_40']['h1'],
                      x['below_lower_bound_ticks_21_40']['h3']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
