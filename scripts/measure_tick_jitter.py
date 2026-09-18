#!/usr/bin/env python3
"""Đo phân bố delta-t trên raw R-S; metrology chỉ đọc ``t_rel``.

Không import scorer/model, không đọc nhãn và không sinh detector output.  Phép
đo này định lượng độ phủ mất bởi chính sách đã khóa ở 6R.3: delta-t > 1.5 s
thì đạo hàm bậc một trở thành unknown.
"""
from __future__ import annotations

import json
import statistics as st
import sys

from ml import campaign as C

THRESHOLD = 1.5
EXPECTED_PERIOD = 1.0
RS_RUNS = (
    'RS-soak2M-s4001-r1',
    'RS-soak2M-s4002-r2',
    'RS-soak2M-s4003-r3',
)
OUT = C.ROOT / 'results/report/phase6r_tick_jitter.json'


def times_and_deltas(path):
    times = [json.loads(line)['t_rel'] for line in path.open(encoding='utf-8')]
    return times, [times[index + 1] - times[index]
                   for index in range(len(times) - 1)]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(int(fraction * len(ordered)), len(ordered) - 1)]


def main() -> int:
    if OUT.exists():
        print('[tick-jitter] receipt da ton tai; khong ghi de')
        return 1
    raw = C.ROOT / 'data/phase6r/raw'
    per_run, pooled = {}, []
    for run_id in RS_RUNS:
        times, deltas = times_and_deltas(raw / ('%s.jsonl' % run_id))
        pooled.extend(deltas)
        over = [(index, round(delta, 4))
                for index, delta in enumerate(deltas) if delta > THRESHOLD]
        expected_last = (len(times) - 1) * EXPECTED_PERIOD
        per_run[run_id] = {
            'n_snapshots': len(times),
            'n_intervals': len(deltas),
            'p50_sec': round(st.median(deltas), 4),
            'p95_sec': round(percentile(deltas, .95), 4),
            'p99_sec': round(percentile(deltas, .99), 4),
            'max_sec': round(max(deltas), 4),
            'n_over_threshold': len(over),
            'over_threshold_first_20': over[:20],
            't_rel_first': round(times[0], 4),
            't_rel_last': round(times[-1], 4),
            'observed_span_sec': round(times[-1] - times[0], 4),
            'span_drift_vs_observed_count_sec': round(
                times[-1] - times[0] - expected_last, 4),
            'missing_ticks_vs_contract': 3600 - len(times),
        }
        result = per_run[run_id]
        print('%s: p50=%ss p95=%ss p99=%ss max=%ss, delta-t >1.5s=%d' %
              (run_id, result['p50_sec'], result['p95_sec'], result['p99_sec'],
               result['max_sec'], len(over)))

    n_over = sum(item['n_over_threshold'] for item in per_run.values())
    content = {
        'lesson': '6R.5B-metrology',
        'threshold_sec': THRESHOLD,
        'decision_this_supports': '6R.3 cach A: delta-t > 1.5s -> d1 unknown',
        'input_runs': list(RS_RUNS),
        'per_run': per_run,
        'pooled': {
            'n_intervals': len(pooled),
            'p50_sec': round(st.median(pooled), 4),
            'p95_sec': round(percentile(pooled, .95), 4),
            'p99_sec': round(percentile(pooled, .99), 4),
            'max_sec': round(max(pooled), 4),
            'n_over_threshold': n_over,
            'coverage_loss_fraction': round(n_over / len(pooled), 8),
        },
        'reads_only_snapshot_fields': ['t_rel'],
        'reads_labels': False,
        'reads_detector_output': False,
    }
    document = {
        'content': content,
        'content_sha256': C.sha256_bytes(
            C.canonical_json(content).encode('utf-8')),
    }
    C.atomic_json(OUT, document)
    print('\nTONG: %d khoang, max=%.4fs, so khoang >1.5s=%d (%.6f%%)' %
          (len(pooled), max(pooled), n_over, 100 * n_over / len(pooled)))
    print('[tick-jitter] content_sha256 =', document['content_sha256'])
    return 0


if __name__ == '__main__':
    assert 'ml.serve' not in sys.modules and 'ml.model' not in sys.modules, \
        'metrology script khong duoc nap scorer/model'
    raise SystemExit(main())
