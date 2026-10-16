#!/usr/bin/env python3
"""
test_gd4_retrain.py — GĐ4: học lại trên tập train thu cùng một máy.

  1. tập train v21 = 7 run Phase 5 (bỏ s1008-r2) + N-vary-s1008-r4 (gd4);
  2. phép tính vùng vận hành tái lập đúng số đã niêm phong của tập train cũ
     (T = 4,312610 Mbps, trần máy khách 6,181986 Mbps);
  3. nếu bản 2.1.0 đã dựng: release nạp được và mọi thành phần khớp mã băm.

    python3 -m pytest -q test/test_gd4_retrain.py
"""
from __future__ import annotations

import pytest

from ml import campaign as C
from ml import gd2_envelope as GE
from ml import gd4_retrain as R

ROOT = C.ROOT


def test_tap_train_v21_dung_tam_run():
    tr, te, warmup, used = R.load_raw('v21', ROOT)
    assert len(used) == 8
    assert GE.BAD_RUN not in used and 'N-vary-s1008-r3' not in used
    assert used[-1] == 'N-vary-s1008-r4'
    assert set(tr.run_id) == set(used)


def test_vung_van_hanh_tai_lap_so_cu():
    p5 = C.load_contract(ROOT / GE.P5_CONTRACT)
    v1 = R.operating_numbers([C.run_paths(r, ROOT)['final'] for r in p5['split']['train']])
    assert round(v1['operating_range_T_mbps'], 6) == 4.31261
    assert v1['client_tx_ceiling_mbps'] == 6.181986
    assert v1['ceiling_owner'] == {'run_id': 'N-vary-s1007-r1', 'tick': 16, 'host': 'host-h3'}


@pytest.mark.skipif(not (ROOT / R.RELEASE_OUT).exists(), reason='chưa dựng 2.1.0')
def test_release_21_nap_duoc_va_khop_thanh_phan():
    from ml.release import DetectorRelease
    release = DetectorRelease.load(ROOT / R.RELEASE_OUT)
    assert release.version == 'detector-release-2.1.0'
    assert release.content['fsm_params'] == {'n_suspect': 1, 'n_act': 2,
                                             'release_m': 3, 'cooldown_s': 8.0}
