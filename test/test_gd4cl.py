#!/usr/bin/env python3
"""
test_gd4cl.py — GĐ4: luật chọn ứng viên theo chiều cho vòng kín (scripts/gd4cl_common.py).

  1. chỉ giữ máy khách gửi cao hơn biên trên; máy bị hại (tụt dưới biên) bị bỏ;
  2. thiếu số đo, rateValid sai -> bỏ (không hành động là mặc định an toàn);
  3. link, switch, máy chủ giữ nguyên; bộ dựng đầu vào trả DetectorView đúng hình dạng;
  4. biên trên lấy đúng từ mô hình 2.1.

    python3 -m pytest -q test/test_gd4cl.py
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from gd4cl_common import (  # noqa: E402
    DirectionalViewProvider, RELEASE_21, directional_filter, twin_client_tx, upper_bounds_bps,
)

from controller.localize import localize  # noqa: E402
from controller.policy import DetectorView  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402

P = 'org.dt4n:host-'
ROLES = {'h1': 'client', 'h2': 'client', 'h3': 'client', 'srv1': 'server', 'srv2': 'server'}
UPPER = {'h1': 672_000.0, 'h2': 676_600.0, 'h3': 772_700.0}     # ~5,4/5,4/6,2 Mbps


def test_giu_thu_pham_bo_nan_nhan():
    affected = [P + 'h1', P + 'h3', 'org.dt4n:link-s1-s2']
    tx = {'h1': 5_875_000.0, 'h2': 250_000.0, 'h3': 40_000.0}      # h1 47 Mbps, h3 tụt
    kept, removed = directional_filter(affected, ROLES, tx, UPPER)
    assert kept == (P + 'h1', 'org.dt4n:link-s1-s2')
    assert removed == ('h3',)
    assert localize(kept, ROLES).target == 'h1'
    assert localize(affected, ROLES).target is None            # luật cũ: hai ứng viên


def test_thieu_so_do_thi_bo():
    kept, removed = directional_filter([P + 'h1'], ROLES, {}, UPPER)
    assert kept == () and removed == ('h1',)


def test_bang_bien_tren_khong_tinh_la_vuot():
    kept, _ = directional_filter([P + 'h2'], ROLES, {'h2': UPPER['h2']}, UPPER)
    assert kept == ()


def test_may_chu_va_link_giu_nguyen():
    affected = [P + 'srv1', 'org.dt4n:link-s2-srv1', 'org.dt4n:switch-s2']
    kept, removed = directional_filter(affected, ROLES, {}, UPPER)
    assert kept == tuple(affected) and removed == ()


class FakeTwin:
    def __init__(self, things, fields):
        self._lock = threading.Lock()
        self.things = things
        self._fields = fields

    def detector_view_fields(self):
        return dict(self._fields)

    def roles(self):
        return dict(ROLES)


def _host(tx, valid=True):
    return {'features': {'traffic': {'properties': {'txRate': tx, 'rateValid': valid}}}}


def test_doc_toc_do_tu_twin_bo_rate_khong_hop_le():
    twin = FakeTwin({P + 'h1': _host(9e6), P + 'h2': _host(1e5, valid=False), P + 'h3': {}}, {})
    assert twin_client_tx(twin) == {'h1': 9e6}


def test_bo_dung_dau_vao_tra_detector_view_da_loc():
    fields = {'state': 'act', 'cause': '', 'affected': (P + 'h1', P + 'h3'),
              'fresh': True, 'boot_id': 'b', 'seq': 7}
    twin = FakeTwin({P + 'h1': _host(5_875_000.0), P + 'h3': _host(40_000.0)}, fields)
    provider = DirectionalViewProvider(twin, UPPER)
    view = provider()
    assert isinstance(view, DetectorView)
    assert view.affected == (P + 'h1',) and view.seq == 7 and view.state == 'act'
    assert provider.stats()['removed_on_act'] == {'h1': 0, 'h2': 0, 'h3': 1}


def test_bien_tren_lay_tu_mo_hinh_21():
    release = DetectorRelease.load(ROOT / RELEASE_21)
    upper = upper_bounds_bps(release)
    assert release.version == 'detector-release-2.1.0'
    assert round(upper['h1'] * 8 / 1e6, 3) == 5.376
    assert round(upper['h3'] * 8 / 1e6, 3) == 6.182
