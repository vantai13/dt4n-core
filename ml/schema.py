#!/usr/bin/env python3
"""Phân loại CỘT: cột nào là feature ML, cột nào không, và VÌ SAO.

VÌ SAO FILE NÀY TỒN TẠI:
    Quyết định "cột nào được làm feature" là một quyết định NGHIÊN CỨU,
    không phải một dòng code rải rác trong script. Nếu nó nằm rải rác, ba
    tuần sau bạn không còn biết đã loại cột nào và vì lý do gì — và báo
    cáo không biện minh được.

    Vì vậy: mọi luật loại trừ nằm Ở ĐÂY, có tên, có lý do bằng chữ, và có
    test ghim lại.
"""
from __future__ import annotations

# --- cột SIÊU DỮ LIỆU: mô tả lần chạy, KHÔNG BAO GIỜ là feature -----------
META_COLS = (
    'run_id', 'profile', 'tick', 'seed', 'git_hash', 'collector_version',
    'load_mbps_per_client', 't_source', 't_cycle_start', 't_cycle_end',
    'timestamp', 'source_file',
    'cycle_scan_ms',
)

# --- hậu tố xác định LOẠI cột --------------------------------------------
META_SUFFIX = ('.t_source',)
TEXT_SUFFIX = ('.utilIntf', '.utilDirectionSource', '.lossSource',
               '.qdiscReason', '.rateReason', '.dump', '.state')
CUMULATIVE_SUFFIX = ('.rxBytes', '.txBytes')
CONFIG_SUFFIX = ('.bwMbps',)
BOOL_SUFFIX = ('.qdiscValid', '.rateValid')

# --- lý do loại trừ, viết một lần, dùng khắp nơi --------------------------
REASON = {
    'meta': 'siêu dữ liệu của lần chạy, không phải đo lường mạng',
    'text': 'chuỗi/nhãn chẩn đoán; audit nunique nhưng không đưa vào mô hình',
    'cumulative': ('BỘ ĐẾM CỘNG DỒN: phụ thuộc thời gian từ lúc interface/reset; '
                   'có thể làm mô hình học tuổi/thứ tự run thay vì sức khỏe mạng'),
    'config': ('GIÁ TRỊ CẤU HÌNH do chính kịch bản inject ghi vào twin '
               '(LinkDegrade.apply đặt link.dt4n_bw). Dùng làm feature = đọc '
               'lại nhãn của chính mình -> leakage'),
    'constant': 'hằng số trên TOÀN BỘ dataset -> không mang thông tin',
    'mostly_null': 'thiếu quá nhiều -> không đủ bằng chứng',
    'no_separation': 'AUC gần 0.5 trong pilot; chưa thấy tách biệt đơn biến theo thứ tự',
    'unmeasured': 'không đủ mẫu số hữu hạn ở cả normal và fault để đo tách biệt',
}


def column_kind(name: str) -> str:
    """Trả về loại của một cột: meta / text / cumulative / config / bool / numeric."""
    if name in META_COLS or name.endswith(META_SUFFIX):
        return 'meta'
    if name.endswith(CUMULATIVE_SUFFIX):
        return 'cumulative'
    if name.endswith(CONFIG_SUFFIX):
        return 'config'
    if name.endswith(BOOL_SUFFIX):
        return 'bool'
    if name.endswith(TEXT_SUFFIX):
        return 'text'
    return 'numeric'


def is_feature_candidate(name: str) -> bool:
    """Cột này CÓ THỂ trở thành feature không? (chưa xét số liệu)"""
    return column_kind(name) in ('numeric', 'bool')
