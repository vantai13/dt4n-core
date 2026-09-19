"""Danh tính của producer collector — Phase 7.2, hợp đồng A.

Phiên bản do phía sản xuất tuyên bố và được ghim vào vân tay của mã nguồn đo
lường. Nếu một file nguồn đổi, test buộc người sửa chủ động bump phiên bản.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


COLLECTOR_VERSION = "v3-qdisc-ratevalid"
MEASUREMENT_SOURCES = {
    "bridge/collector.py": "f98979a82f8f347a227b2bddb81b00eb5081dedda442f01b2d7799979b4193cf",
    "twin/link_direction.py": "046698b02895843e0d2b04f3457ddc9eca778bbc85ea52e55b6c06c27c83c7d2",
}
ROOT = Path(__file__).resolve().parents[1]


def source_sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def drifted_sources() -> list[str]:
    """Trả các file đo lường đã lệch khỏi vân tay; rỗng nghĩa là khớp."""
    return [
        relative
        for relative, digest in MEASUREMENT_SOURCES.items()
        if source_sha256(relative) != digest
    ]
