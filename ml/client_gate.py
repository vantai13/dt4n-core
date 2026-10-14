#!/usr/bin/env python3
"""
client_gate.py — GĐ2: cổng "mỗi client có thật sự gửi traffic theo kế hoạch không".

VÌ SAO CẦN (lỗi s1008):
  Run train N-vary-s1008-r2 có h1 và h3 KHÔNG gửi byte nào suốt 59 tick, nhưng vẫn
  qua mọi cổng cũ. Cổng cũ đếm tiến trình iperf (7/7) trong soft_reset — TRƯỚC khi
  start_profile tắt iperf và bật lại server theo lịch của run. Nó đo "tiến trình có
  tồn tại lúc kiểm" chứ không đo "dữ liệu đã ghi có traffic không".
  Hệ quả: envelope-1.0.0 học biên dưới txRate(h1) = txRate(h3) = 0 -> client im lặng
  bị coi là bình thường; ngưỡng K = 31 và E = 8.97 cũng do run này đặt.

  (Suy luận, chưa kiểm trực tiếp: trong lịch biến thiên, h1 và h3 cùng gửi tới srv1
   — hai client im lặng đúng là hai client tới srv1 — nên nhiều khả năng iperf server
   trên srv1 không nhận kết nối sau khi được bật lại.)

LUẬT (kiểm trên DỮ LIỆU ĐÃ GHI, không kiểm tiến trình):
  ngưỡng  = RATIO x mức kế hoạch THẤP NHẤT của run (Mbps/client)
  cửa sổ  = các tick sau warmup, trước inject (run normal: cả run)
  đạt     = mọi client có txRate >= ngưỡng ở ít nhất MIN_FRACTION số tick của cửa sổ

  Số liệu Phase 5 để chọn RATIO/MIN_FRACTION (đo trực tiếp trên 18 run):
    17 run khỏe: cả 3 client >= 0.1 Mbps ở 100% tick; thấp nhất 0.84 Mbps (kế hoạch 1 Mbps)
    s1008      : h1, h3 = 0 Mbps ở 100% tick
  -> RATIO 0.5, MIN_FRACTION 0.9 tách hai nhóm với biên rộng ở cả hai phía.

CÁCH CHẠY (không cần Mininet, đọc dữ liệu có sẵn trong repo):
    python3 -m ml.client_gate audit       # áp cổng lên 18 run Phase 5, ghi receipt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CLIENTS = ('h1', 'h2', 'h3')
RATIO = 0.5
MIN_FRACTION = 0.9
AUDIT_OUT = 'results/report/gd2_client_traffic_audit.json'


def planned_min_mbps(record: dict) -> float:
    """Mức tải kế hoạch THẤP NHẤT mỗi client (Mbps): tải cố định hoặc bậc thấp nhất."""
    if record.get('load_mbps_per_client') is not None:
        return float(record['load_mbps_per_client'])
    schedule = record.get('load_schedule') or []
    if not schedule:
        raise ValueError('record không có mức tải kế hoạch: %s' % record.get('run_id'))
    return float(min(rate for _, rate in schedule))


def _tx_mbps(snapshot: dict, client: str):
    host = (snapshot.get('things') or {}).get('host-%s' % client) or {}
    value = host.get('features', {}).get('traffic', {}).get('txRate')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value * 8.0 / 1e6


def client_traffic_check(record: dict, snapshots: list, events: list,
                         warmup: int = 1, ratio: float = RATIO,
                         min_fraction: float = MIN_FRACTION) -> dict:
    """Kết quả cổng cho MỘT run. Khóa 'client_traffic_ok' kết thúc bằng '_ok'
    nên tự được tính là một cổng khi gộp vào verify_run."""
    inject = next((e.get('tick') for e in events or [] if e.get('kind') == 'inject'), None)
    end = inject + 1 if isinstance(inject, int) else len(snapshots)
    window = snapshots[warmup:end]
    threshold = ratio * planned_min_mbps(record)
    per_client = {}
    for client in CLIENTS:
        values = [_tx_mbps(s, client) for s in window]
        good = sum(1 for v in values if v is not None and v >= threshold)
        known = [v for v in values if v is not None]
        per_client[client] = {
            'n_ticks': len(values),
            'frac_ok': round(good / len(values), 4) if values else 0.0,
            'min_mbps': round(min(known), 4) if known else None,
            'median_mbps': round(sorted(known)[len(known) // 2], 4) if known else None,
        }
    ok = bool(window) and all(v['frac_ok'] >= min_fraction for v in per_client.values())
    return {'client_traffic_threshold_mbps': round(threshold, 4),
            'client_traffic_min_fraction': min_fraction,
            'client_traffic': per_client,
            'client_traffic_ok': ok}


# ===========================================================================
# audit: áp cổng mới lên dữ liệu Phase 5 đã có (không sửa gì của Phase 5)
# ===========================================================================
def audit_phase5(root: Path | None = None) -> dict:
    from ml import campaign as C
    root = Path(root or C.ROOT)
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    warmup = int(contract['constants']['warmup_ticks'])
    rows = {}
    for record in contract['runs']:
        paths = C.run_paths(record['run_id'], root)
        side = json.loads(paths['meta'].read_text(encoding='utf-8'))
        if C.sha256_file(paths['final']) != side['sha256']:
            raise ValueError('raw lệch sha256 sidecar: ' + record['run_id'])
        snaps = C.read_snapshots(paths['final'])
        check = client_traffic_check(record, snaps, side['events'], warmup)
        rows[record['run_id']] = {'split': record['split'], 'group': record['group'],
                                  'old_gates_passed': side['checks'].get('passed'),
                                  **check}
    failing = sorted(r for r, v in rows.items() if not v['client_traffic_ok'])
    return {'what': 'GĐ2 — cổng traffic từng client áp lên 18 run Phase 5',
            'rule': {'ratio': RATIO, 'min_fraction': MIN_FRACTION, 'clients': CLIENTS},
            'n_runs': len(rows), 'failing_runs': failing, 'runs': rows}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ['audit']:
        print(__doc__)
        return 2
    from ml import campaign as C
    rep = audit_phase5()
    out = C.ROOT / AUDIT_OUT
    C.atomic_json(out, rep)
    for rid, v in sorted(rep['runs'].items()):
        mark = '✅' if v['client_traffic_ok'] else '❌'
        fr = ' '.join('%s=%.2f' % (c, v['client_traffic'][c]['frac_ok']) for c in CLIENTS)
        print('%s %-28s %-5s ngưỡng=%.2f Mbps  %s' % (
            mark, rid, v['split'], v['client_traffic_threshold_mbps'], fr))
    print('\nRun trượt cổng mới: %s' % (rep['failing_runs'] or 'không có'))
    print('receipt: %s' % AUDIT_OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
