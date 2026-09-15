#!/usr/bin/env python3
"""
health.py — Tính healthState (trạng thái sức khỏe ngữ nghĩa) từ metric thô.
LỚP 2 (Bridge). Thêm ở Phase 3 / Lesson 3.4 (Lựa chọn B).

VÌ SAO TỒN TẠI (bản chất):
  Metric thô (rxRate=9800000) tự nó KHÔNG nói "tốt/xấu". Cần THRESHOLD (ngưỡng)
  để phân loại thành trạng thái ngữ nghĩa: ok / warning / critical.

  Theo Lesson 3.1 (twin = single source of truth), trạng thái ngữ nghĩa PHẢI
  sống trong twin để MỌI consumer (dashboard, ML, controller) đọc CÙNG một
  trạng thái -> nhất quán tuyệt đối. Vì thế ta tính Ở ĐÂY (Sync Agent, Phase 2)
  và lưu vào Thing, thay vì để mỗi dashboard tự tính (dễ lệch nhau).

NGUYÊN TẮC THIẾT KẾ:
  - PURE FUNCTION: nhận số, trả chuỗi. Không đụng mạng/Ditto/Mininet -> TEST ĐƯỢC
    không cần hạ tầng. (Cùng tư duy pure-function của translate.js frontend.)
  - ADDITIVE: file MỚI, độc lập. Không sửa collector/differ/pusher -> không thể
    phá vỡ luồng đẩy đang chạy. Rủi ro được cô lập.
  - PRECEDENCE: khi nhiều điều kiện đúng, trạng thái XẤU NHẤT thắng (down > warning).

HẠN CHẾ ĐÃ BIẾT (ghi vào báo cáo):
  - Ngưỡng hiện CỐ ĐỊNH (hardcoded) theo topo demo 20 Mbps, sai cho link khác.
    Hướng cải tiến: ngưỡng tương đối theo công suất link, hoặc cấu hình được.
"""

# --- NGƯỠNG: gom về một chỗ (không rải rác) -> dễ chỉnh, dễ đưa ra config sau ---
# rxRate/txRate collector trả về BYTES/GIÂY. Quy ra Mbps để so cho trực giác:
#   Mbps = bytes_per_sec * 8 / 1_000_000
HOST_WARN_MBPS = 14.0       # > 70% link 20 Mbps -> warning (tải cao)
HOST_CRIT_MBPS = 18.0       # > 90% link 20 Mbps -> critical (sắp nghẽn)
LINK_WARN_UTIL = 0.70
LINK_CRIT_UTIL = 0.90

PATH_WARN_LATENCY_MS = 50.0     # > 50ms   -> warning
PATH_CRIT_LATENCY_MS = 150.0    # > 150ms  -> critical
PATH_WARN_LOSS_PCT = 1.0        # > 1%     -> warning
PATH_CRIT_LOSS_PCT = 5.0        # > 5%     -> critical

# Thứ tự nghiêm trọng (để lấy "xấu nhất"). Số lớn = nặng hơn.
_SEVERITY = {'unknown': 0, 'ok': 1, 'warning': 2, 'critical': 3}


def _worst(*states):
    """Trả trạng thái NẶNG nhất trong các trạng thái đưa vào (precedence)."""
    return max(states, key=lambda s: _SEVERITY.get(s, 0))


def _bytes_to_mbps(bytes_per_sec):
    if bytes_per_sec is None:
        return None
    return bytes_per_sec * 8.0 / 1_000_000.0


def health_for_host(features):
    """Trạng thái sức khỏe của 1 HOST từ features thô (định dạng collector, PHẲNG)."""
    status = features.get('status', {})
    state = status.get('state')

    # 1) down/unknown -> ưu tiên cao nhất (precedence).
    if state == 'down':
        return 'critical'
    if state in (None, 'unknown'):
        return 'unknown'

    # 2) up: xét tải. Lấy MAX(rx, tx) vì chỉ cần 1 chiều nghẽn là có vấn đề.
    traffic = features.get('traffic', {})
    rx = _bytes_to_mbps(traffic.get('rxRate'))
    tx = _bytes_to_mbps(traffic.get('txRate'))
    peak = max([v for v in (rx, tx) if v is not None], default=None)

    if peak is None:
        return 'ok'                     # up nhưng chưa có số tải -> coi là ok
    if peak > HOST_CRIT_MBPS:
        return 'critical'
    if peak > HOST_WARN_MBPS:
        return 'warning'
    return 'ok'


def health_for_link(features):
    """Trạng thái của 1 LINK vật lý: up/down + utilization nếu có."""
    state = features.get('status', {}).get('state')
    if state == 'down':
        return 'critical'
    if state != 'up':
        return 'unknown'

    traffic = features.get('traffic', {})
    capacity = features.get('capacity', {})
    cap = capacity.get('bwMbps')
    if not traffic or not cap or cap <= 0:
        return 'ok'

    rx = _bytes_to_mbps(traffic.get('rxRate'))
    tx = _bytes_to_mbps(traffic.get('txRate'))
    peak = max([v for v in (rx, tx) if v is not None], default=None)
    if peak is None:
        return 'ok'

    util = peak / cap
    if util > LINK_CRIT_UTIL:
        return 'critical'
    if util > LINK_WARN_UTIL:
        return 'warning'
    return 'ok'


def health_for_path(features):
    """Trạng thái của 1 PATH (đo latency/loss)."""
    q = features.get('quality', {})
    lat = q.get('latency_ms')
    loss = q.get('packetLoss_pct')

    if lat is None and loss is None:
        return 'unknown'

    result = 'ok'
    if lat is not None:
        if lat > PATH_CRIT_LATENCY_MS:
            result = _worst(result, 'critical')
        elif lat > PATH_WARN_LATENCY_MS:
            result = _worst(result, 'warning')
    if loss is not None:
        if loss > PATH_CRIT_LOSS_PCT:
            result = _worst(result, 'critical')
        elif loss > PATH_WARN_LOSS_PCT:
            result = _worst(result, 'warning')
    return result


def compute_health_state(kind, features):
    """Điểm vào duy nhất: chọn hàm theo loại thiết bị.
    kind: 'host' | 'switch' | 'link' | 'path'. Trả 'ok'|'warning'|'critical'|'unknown'.
    """
    if kind == 'host':
        return health_for_host(features)
    if kind == 'switch':
        # switch: hiện chỉ có state -> dùng chung logic link.
        return health_for_link(features)
    if kind == 'link':
        return health_for_link(features)
    if kind == 'path':
        return health_for_path(features)
    return 'unknown'
