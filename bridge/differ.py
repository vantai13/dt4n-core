#!/usr/bin/env python3
"""
differ.py — Delta sync: so sánh snapshot now vs prev, chỉ trả phần ĐỔI.
LỚP 2 (Bridge). Toàn bộ là pure function -> test được không cần Ditto/Mininet.

VÌ SAO CẦN (Lesson 2.3 Phần 5): full sync gửi mọi property mỗi chu kỳ -> tải
Ditto, nhiễu event cho dashboard. Delta sync chỉ gửi cái thực sự khác.

BẪY FLOAT (Phần 5.3): rxRate tính từ counter/thời gian gần như LUÔN lệch nhẹ
(1500.2 -> 1500.5) do nhiễu đo. So bằng '==' -> gửi mọi chu kỳ -> mất tác dụng.
=> dùng ngưỡng (tolerance) cho số; so trực tiếp cho chuỗi (state up/down).
"""

# Ngưỡng coi 2 số float là "như nhau". Đặt theo từng loại metric nếu cần.
DEFAULT_TOL = 0.5      # byte/s — dưới mức này coi như nhiễu, không đáng gửi
META_FEATURE = 'meta'


def values_equal(old, new, tol=DEFAULT_TOL):
    """So sánh có khoan dung: số dùng ngưỡng, còn lại so trực tiếp."""
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool) and old == new
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return abs(old - new) < tol
    return old == new


def diff_features(now, prev, tol=DEFAULT_TOL):
    """now/prev là dict features dạng Ditto: {fname: {'properties': {...}}}.
    Trả dict CHỈ chứa feature/property đã đổi. prev=None -> trả tất cả (full sync
    chu kỳ đầu)."""
    if prev is None:
        return now

    changes = {}
    for fname, fdata in now.items():
        # tSource changes every collection cycle. It must ride along with real
        # deltas, not create a delta by itself, or delta sync becomes full sync.
        if fname == META_FEATURE:
            continue
        now_props = fdata.get('properties', {})
        prev_props = prev.get(fname, {}).get('properties', {})

        changed = {}
        for prop, val in now_props.items():
            # state (chuỗi rời rạc) -> so trực tiếp, đổi là gửi NGAY (sự kiện quan trọng)
            if not values_equal(prev_props.get(prop), val, tol):
                changed[prop] = val

        if changed:
            changes[fname] = {'properties': changed}

    if changes and META_FEATURE in now:
        changes[META_FEATURE] = now[META_FEATURE]
    return changes


def diff_snapshot(things_now, things_prev, tol=DEFAULT_TOL):
    """So sánh cả snapshot (nhiều Thing). things_* = {thing_id: {'features': {...}}}.
    Trả {thing_id: {'features': changed}} chỉ cho Thing có thay đổi."""
    out = {}
    prev = things_prev or {}
    for tid, data in things_now.items():
        f_now = data.get('features', {})
        f_prev = prev.get(tid, {}).get('features') if tid in prev else None
        changed = diff_features(f_now, f_prev, tol)
        if changed:
            out[tid] = {'features': changed}
    return out
