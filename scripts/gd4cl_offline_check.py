#!/usr/bin/env python3
"""
gd4cl_offline_check.py — Kiểm offline luật chọn ứng viên theo chiều trên dữ liệu đã có.

Chạy detector 2.1 (FastOnlineScorer, như lượt chấm) trên mọi run của tập phát triển và tập
nghiệm thu. Ở mỗi giây detector cho tín hiệu cần hành động (dual), lấy tập máy khách có cột
vượt biên (như evidence.affected) và đếm máy khách còn lại khi không lọc và khi lọc theo
chiều (chỉ giữ máy khách có txRate trong chính ảnh chụp cao hơn biên trên).
Đây là xấp xỉ: controller thật đọc trạng thái FSM đã công bố và tốc độ từ twin.

    python3 scripts/gd4cl_offline_check.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gd4cl_common import CLIENTS, RELEASE_21, directional_filter, upper_bounds_bps  # noqa: E402

from ml import campaign as C  # noqa: E402
from ml.blast_radius import entity_of  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from ml.serve_fast import FastOnlineScorer  # noqa: E402

OUT = C.ROOT / 'results/report/gd4cl_offline_check.json'
PREFIX = 'org.dt4n:host-'
SETS = {
    'phase5_test': (C.ROOT / 'results/report/experiment_matrix.json', C.ROOT / 'data/phase5/raw',
                    lambda r: r['split'] == 'test'),
    'gd4r': (C.ROOT / 'results/report/gd4r_contract.json', C.ROOT / 'data/phase5/gd4r/raw',
             lambda r: r['group'] in ('RD', 'RC', 'RN')),
}


def culprit_of(record: dict):
    if record.get('fault') == 'flood':
        return record['fault_target'].split('->')[0]
    return None


def outcome(cands: tuple, culprit) -> str:
    if not cands:
        return 'khong_ung_vien'
    if len(cands) > 1:
        return 'nhieu_ung_vien'
    return 'dung_thu_pham' if cands[0] == culprit else 'sai_may'


def check_run(release, upper, path: Path, culprit) -> dict:
    scorer = FastOnlineScorer(release.model,
                              expected_collector_version=release.content['collector_version'],
                              conservation=release.conservation, conservation_mode='shadow')
    roles = {c: 'client' for c in CLIENTS}
    old, new = Counter(), Counter()
    for snap in C.read_snapshots(path):
        reading = scorer.observe(snap)
        if reading.tick is None or not reading.act:
            continue
        affected = sorted({PREFIX + e.replace('host-', '') for e in
                           {entity_of(c) for c in reading.violating} - {None}
                           if e.startswith('host-')})
        tx = {}
        for c in CLIENTS:
            traffic = ((snap['things'].get('host-' + c) or {}).get('features') or {}) \
                .get('traffic') or {}
            if traffic.get('rateValid') is True:
                tx[c] = float(traffic.get('txRate'))
        old_c = tuple(sorted(a[len(PREFIX):] for a in affected
                             if a[len(PREFIX):] in roles))
        kept, _ = directional_filter(affected, roles, tx, upper)
        new_c = tuple(sorted(a[len(PREFIX):] for a in kept if a[len(PREFIX):] in roles))
        old[outcome(old_c, culprit)] += 1
        new[outcome(new_c, culprit)] += 1
    return {'act_ticks': sum(old.values()), 'old_rule': dict(old), 'directional': dict(new)}


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    release = DetectorRelease.load(C.ROOT / RELEASE_21)
    upper = upper_bounds_bps(release)
    content = {'release': release.version,
               'upper_bounds_mbps': {c: round(v * 8 / 1e6, 3) for c, v in upper.items()},
               'note': ('Xấp xỉ offline theo từng giây có tín hiệu dual; controller thật dùng '
                        'trạng thái FSM đã công bố và tốc độ trên twin.'),
               'runs': {}}
    for name, (contract_path, raw, keep) in SETS.items():
        contract = json.loads(Path(contract_path).read_text())
        for record in contract['runs']:
            if not keep(record):
                continue
            path = raw / (record['run_id'] + '.jsonl')
            if not path.exists():
                continue
            row = check_run(release, upper, path, culprit_of(record))
            row.update({'set': name, 'fault': record.get('fault'),
                        'target': record.get('fault_target'), 'culprit': culprit_of(record)})
            content['runs'][record['run_id']] = row
    content['written_at_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    C.atomic_json(OUT, {'content': content, 'content_sha256': C.sha256_bytes(
        C.canonical_json(content).encode('utf-8'))})
    print('biên trên (Mbps):', content['upper_bounds_mbps'])
    for rid, r in content['runs'].items():
        if r['act_ticks']:
            print('%-38s %-10s act %2d | cũ %-60s | theo chiều %s' % (
                rid[:38], r['fault'], r['act_ticks'], r['old_rule'], r['directional']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
