#!/usr/bin/env python3
"""
adapter.py — Lớp dịch (Anti-Corruption Layer) giữa collector Phase 1 và Ditto.
LỚP 2 (Bridge).

VÌ SAO TỒN TẠI:
  collector.py (Phase 1) xuất:  features.traffic.rxRate          (phẳng)
  Ditto Thing cần:              features.traffic.properties.rxRate (có tầng 'properties')
  Hai mô hình KHÁC nhau. Thay vì sửa collector (làm bẩn Lớp 1) hoặc bắt Ditto
  chịu cấu trúc lạ, ta đặt MỘT lớp dịch ở giữa. Đổi collector -> chỉ sửa file này.

  Đây là pattern Anti-Corruption Layer: cô lập sự khác biệt mô hình vào một chỗ.
"""

from bridge.ditto_common import (make_thing_id_host, make_thing_id_switch,
                                 make_thing_id_link, make_thing_id_path)
from bridge.health import compute_health_state   # Phase 3 / Lesson 3.4 (Lựa chọn B)


def _wrap_properties(feature_dict):
    """Bọc mỗi feature collector vào tầng 'properties' mà Ditto yêu cầu.
    {'traffic': {'rxRate': 5}} -> {'traffic': {'properties': {'rxRate': 5}}}
    Bỏ qua field rỗng/None để PATCH không ghi 'null' (merge-patch coi null = xóa!)."""
    out = {}
    for fname, props in feature_dict.items():
        clean = {k: v for k, v in props.items() if v is not None}
        if clean:
            out[fname] = {'properties': clean}
    return out


def collector_to_things(snapshot):
    """Nhận snapshot collector -> trả dict {ditto_thing_id: {'features': {...}}}.

    - Lột vỏ ['things'] của collector.
    - Đổi key ngắn ('host-h1') thành thingId đầy đủ ('org.dt4n:host-h1') qua
      đúng quy ước make_thing_id_* (single source of truth từ 2.2).
    - Bọc 'properties' cho khớp Ditto.
    """
    things = snapshot.get('things', snapshot)   # chấp nhận cả 2 dạng
    snapshot_ts = snapshot.get('t_source')
    result = {}

    for short_key, data in things.items():
        attrs = data.get('attributes', {})
        kind = attrs.get('type')
        features = data.get('features', {})

        # === Phase 3 / Lesson 3.4 (Lựa chọn B): tính healthState NGAY TẠI TWIN ===
        # ADDITIVE: chỉ THÊM feature 'health' mới. Logic dịch cũ bên dưới KHÔNG đổi.
        # 'kind' có thể là 'host'/'switch'/'link'/'path'; nếu short_key gợi ý khác,
        # ta chuẩn hóa nhẹ để compute_health_state nhận đúng loại.
        health_kind = kind
        if health_kind is None:
            if short_key.startswith('host-'):   health_kind = 'host'
            elif short_key.startswith('switch-'): health_kind = 'switch'
            elif short_key.startswith('link-'):  health_kind = 'link'
            elif short_key.startswith('path-'):  health_kind = 'path'
        state = compute_health_state(health_kind, features)
        # Chèn thành FEATURE (dữ liệu ĐỘNG) — nó sẽ tự chảy qua _wrap_properties.
        # KHÔNG đặt vào attributes (attributes là dữ liệu TĨNH, không đẩy mỗi chu kỳ).
        features = dict(features)                 # bản sao -> không mutate input (immutable)
        features['health'] = {'state': state}
        t_source = data.get('t_source', snapshot_ts)
        if t_source is not None:
            # A0: millisecond quantisation is the same scale as the per-link
            # offset estimand E3. Epoch float64 supports meaningful microseconds.
            features['meta'] = {'tSource': round(float(t_source), 6)}

        # short_key dạng 'host-h1' / 'switch-s1' / 'link-h1-srv1'
        if kind == 'host' or short_key.startswith('host-'):
            name = short_key.split('host-', 1)[-1]
            tid = make_thing_id_host(name)
        elif kind == 'switch' or short_key.startswith('switch-'):
            name = short_key.split('switch-', 1)[-1]
            tid = make_thing_id_switch(name)
        elif kind == 'path' or short_key.startswith('path-'):
            src = attrs.get('src')
            dst = attrs.get('dst')
            if not (src and dst):
                body = short_key.split('path-', 1)[-1]
                parts = body.split('-')
                if len(parts) < 2:
                    continue
                src, dst = parts[0], '-'.join(parts[1:])
            tid = make_thing_id_path(src, dst)
        elif kind == 'link' or short_key.startswith('link-'):
            # collector có thể đặt 'link-h1-srv1'; tách 2 đầu để canonical lại
            body = short_key.split('link-', 1)[-1]
            parts = body.split('-')
            if len(parts) >= 2:
                tid = make_thing_id_link(parts[0], '-'.join(parts[1:]))
            else:
                tid = make_thing_id_link(body, body)
        else:
            continue   # loại không nhận diện -> bỏ qua an toàn

        wrapped = _wrap_properties(features)
        if wrapped:
            result[tid] = {'features': wrapped}

    return result
