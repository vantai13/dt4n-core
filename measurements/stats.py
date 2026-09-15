#!/usr/bin/env python3
"""
stats.py — Tính & trình bày thống kê latency (Lesson 2.4 Phần 5.3). Pure function.

VÌ SAO KHÔNG CHỈ MEAN (bài học quan trọng nhất của đo lường):
  mean nhỏ có thể CHE GIẤU long tail. [0.5]*19 + [4.8] -> mean=0.74s nghe "đạt
  target <2s", nhưng max=4.8s VƯỢT gấp đôi. Hội đồng hỏi "5% xấu nhất ra sao?"
  -> p95. Quy chuẩn báo cáo: LUÔN mean + p50 + p95 + max kèm n.
"""

from statistics import mean, median


def percentile(sorted_vals, q):
    """Phân vị q (0..1) theo 'nearest-rank'. sorted_vals đã sắp tăng.
    q=0.95 -> giá trị mà 95% mẫu <= nó. Đủ chuẩn cho đồ án (không nội suy)."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    # nearest-rank: vị trí = ceil(q*n) - 1, kẹp trong [0, n-1]
    import math
    idx = max(0, min(len(sorted_vals) - 1, math.ceil(q * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def summarize(latencies_sec):
    """Nhận list latency (giây) -> dict thống kê (đơn vị ms cho dễ đọc)."""
    if not latencies_sec:
        return None
    s = sorted(latencies_sec)
    n = len(s)
    return {
        'n': n,
        'mean_ms': mean(s) * 1000,
        'p50_ms':  median(s) * 1000,
        'p95_ms':  percentile(s, 0.95) * 1000,
        'p99_ms':  percentile(s, 0.99) * 1000,
        'max_ms':  max(s) * 1000,
        'min_ms':  min(s) * 1000,
    }


def format_report(stats, label='', title='Sync Latency'):
    """In bộ tứ chuẩn nghiên cứu."""
    if stats is None:
        return 'Không có mẫu hợp lệ.'
    return (
        '=== %s%s (n=%d) ===\n'
        '  mean: %5.0f ms\n  p50:  %5.0f ms\n  p95:  %5.0f ms\n'
        '  p99:  %5.0f ms\n  max:  %5.0f ms\n  min:  %5.0f ms'
        % (title, ' ' + label if label else '', stats['n'],
           stats['mean_ms'], stats['p50_ms'], stats['p95_ms'],
           stats['p99_ms'], stats['max_ms'], stats['min_ms'])
    )
