#!/usr/bin/env python3
"""
gd4cl_common.py — Luật chọn ứng viên theo chiều cho controller vòng kín, và các tiện ích chung.

evidence.affected của detector gom thực thể có cột vượt biên nhưng không ghi chiều vượt, nên
khi một máy khách flood, máy dùng chung đường bị tụt tốc độ cũng có thể vào danh sách.

Luật theo chiều (đặt ở bước dựng đầu vào của controller): một máy khách trong
evidence.affected chỉ được giữ khi tốc độ gửi của nó trên twin cao hơn biên trên txRate của
chính nó trong mô hình envelope 2.1. Thiếu số đo hoặc rateValid sai thì bỏ (không hành động
là mặc định an toàn). Thực thể khác (link, switch, máy chủ) giữ nguyên. Controller chỉ hành
động khi sau bước lọc còn đúng một ứng viên.

Luật đi qua tham số view_provider của ControlRunner, không sửa controller/*.py. Nhật ký
controller ghi danh sách đã lọc; bộ dựng còn đếm số lần mỗi máy khách bị loại.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.localize import HOST_PREFIX  # noqa: E402
from controller.policy import DetectorView  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402

RELEASE_21 = 'models/detector-release-2.1.0.json'
CLIENTS = ('h1', 'h2', 'h3')


def upper_bounds_bps(release: DetectorRelease, clients=CLIENTS) -> dict:
    """Biên trên txRate (byte/s) của từng máy khách trong mô hình envelope của release."""
    bounds = release.model._c['bounds']
    return {c: float(bounds['host-%s.traffic.txRate' % c]['max']) for c in clients}


def directional_filter(affected, roles: dict, client_tx_bps: dict, upper_bps: dict):
    """Hàm thuần: bỏ máy khách không gửi vượt biên trên. Trả (danh sách mới, các máy bị bỏ)."""
    kept, removed = [], []
    for thing_id in affected or ():
        if isinstance(thing_id, str) and thing_id.startswith(HOST_PREFIX):
            name = thing_id[len(HOST_PREFIX):]
            if roles.get(name) == 'client':
                tx = client_tx_bps.get(name)
                if tx is None or name not in upper_bps or not tx > upper_bps[name]:
                    removed.append(name)
                    continue
        kept.append(thing_id)
    return tuple(kept), tuple(sorted(removed))


def twin_client_tx(twin, clients=CLIENTS) -> dict:
    """txRate (byte/s) của máy khách trên twin; bỏ máy thiếu số đo hoặc rateValid sai."""
    with twin._lock:
        things = dict(twin.things)
    out = {}
    for c in clients:
        traffic = ((((things.get(HOST_PREFIX + c) or {}).get('features') or {})
                    .get('traffic') or {}).get('properties') or {})
        value = traffic.get('txRate')
        if traffic.get('rateValid') is True and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            out[c] = float(value)
    return out


class DirectionalViewProvider:
    """view_provider cho ControlRunner: giống build_view gốc, thêm bước lọc theo chiều."""

    def __init__(self, twin, upper_bps: dict):
        self.twin = twin
        self.upper_bps = dict(upper_bps)
        self.n_calls = 0
        self.n_act_calls = 0
        self.removed = {c: 0 for c in CLIENTS}

    def __call__(self) -> DetectorView:
        fields = self.twin.detector_view_fields()
        roles = self.twin.roles()
        affected, removed = directional_filter(
            fields['affected'], roles, twin_client_tx(self.twin), self.upper_bps)
        self.n_calls += 1
        if fields['state'] == 'act':
            self.n_act_calls += 1
            for name in removed:
                self.removed[name] = self.removed.get(name, 0) + 1
        return DetectorView(
            state=fields['state'], cause=fields['cause'], affected=affected,
            roles=tuple(sorted(roles.items())), fresh=fields['fresh'],
            boot_id=fields['boot_id'], seq=fields['seq'])

    def stats(self) -> dict:
        return {'n_calls': self.n_calls, 'n_act_calls': self.n_act_calls,
                'removed_on_act': dict(self.removed)}


def live21_class():
    """Live của Phase 7/8 nhưng nạp detector-release-2.1.0 (Live gốc ghim 1.0.0)."""
    from phase7_live_common import Live

    class Live21(Live):
        def __init__(self, duration_s: int):
            super().__init__(duration_s)
            self.release = DetectorRelease.load(C.ROOT / RELEASE_21)

    return Live21
