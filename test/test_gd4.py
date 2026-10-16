#!/usr/bin/env python3
"""
test_gd4.py — GĐ4: hai hợp đồng thu lại trên máy GCP.

  1. gd4: run train thay thế = bản sao ĐÚNG record s1008 (chỉ khác run_id), khóa hash,
     ghi máy thu, dữ liệu tách khỏi data/phase5/raw và data/phase5/gd2;
  2. gd4r: cùng thiết kế R-campaign 6R (nhóm, số run, liều R-D, thời lượng), chỉ khác
     seed (+1000), run_id, thứ tự chạy, thư mục; khóa hash, phát hiện bị sửa;
  3. hai binding mới được đăng ký và đi qua integrity_ok như các chiến dịch cũ.

    python3 -m pytest -q test/test_gd4.py
"""
from __future__ import annotations

import copy
import json

import pytest

from ml import campaign as C
from ml import campaign_binding as B
from ml import gd4campaign as G4
from ml import gd4rcampaign as G4R
from ml import rcampaign as R

ROOT = C.ROOT
P5 = C.load_contract(ROOT / 'results/report/experiment_matrix.json')
OLD_R = R.load_contract(ROOT / 'results/report/phase6r_rcampaign_matrix.json')


# --------------------------------------------------------------------------- 1. gd4
def test_gd4_ban_sao_s1008_khoa_hash_va_may_thu():
    doc = G4.build_contract(ROOT)
    src = next(r for r in P5['runs'] if r['run_id'] == 'N-vary-s1008-r2')
    (rec,) = doc['runs']
    assert rec == dict(src, run_id='N-vary-s1008-r4', exec_index=0)
    assert doc['constants'] == P5['constants']
    assert doc['collection_host'] == 'dt4n-research-01'
    assert G4.check_integrity(doc, ROOT)['match'] is True
    for key, value in (('collection_host', 'laptop'), ('runs', [src])):
        bad = copy.deepcopy(doc)
        bad[key] = value
        bad['design_content_sha256'] = G4.design_hash(bad)
        with pytest.raises(RuntimeError):
            G4.check_integrity(bad, ROOT)


def test_gd4_duong_dan_tach_rieng():
    p = G4.run_paths('N-vary-s1008-r4', ROOT)
    assert 'data/phase5/gd4/raw' in str(p['final']).replace('\\', '/')
    with pytest.raises(ValueError):
        G4.run_paths('../x', ROOT)


# --------------------------------------------------------------------------- 2. gd4r
def _strip(record, seed_offset=0):
    """Record bỏ danh tính (run_id, seed, exec_index) để so thiết kế."""
    out = {k: v for k, v in record.items() if k not in ('run_id', 'seed', 'exec_index')}
    if record['group'] == 'RC':
        out.pop('fault_parameters')      # mức độ R-C sinh từ seed: khác là đúng
    return out


def test_gd4r_cung_thiet_ke_6r_chi_khac_seed():
    doc = G4R.build_contract(ROOT)
    old = {(r['group'], r['seed']): r for r in OLD_R['runs']}
    new = {(r['group'], r['seed'] - 1000): r for r in doc['runs']}
    assert set(old) == set(new)
    for key, record in old.items():
        assert _strip(new[key]) == _strip(record), key
        assert new[key]['run_id'] != record['run_id']
    assert {g: len(v) for g, v in doc['groups'].items()} == \
        {g: len(v) for g, v in OLD_R['groups'].items()}
    assert doc['execution_order'] != OLD_R['execution_order']
    assert doc['source_design_sha256'] == OLD_R['design_content_sha256']
    assert doc['validation']['checks'] and all(doc['validation']['checks'].values())


def test_gd4r_lieu_rd_giong_het_6r():
    doc = G4R.build_contract(ROOT)
    dose = lambda runs: sorted((r['fault_target'], r['fault_parameters']['factor'])
                               for r in runs if r['group'] == 'RD')
    assert dose(doc['runs']) == dose(OLD_R['runs'])


def test_gd4r_khoa_hash_phat_hien_bi_sua():
    doc = G4R.build_contract(ROOT)
    assert G4R.check_integrity(doc, ROOT)['match'] is True
    bad = copy.deepcopy(doc)
    bad['runs'][0]['load_mbps_per_client'] = 3.0
    with pytest.raises(RuntimeError):
        G4R.check_integrity(bad, ROOT)


def test_gd4r_duong_dan_tach_rieng():
    p = G4R.run_paths('RS-soak2M-s5001-r1', ROOT)
    assert 'data/phase5/gd4r/raw' in str(p['final']).replace('\\', '/')


# --------------------------------------------------------------------------- 3. binding
@pytest.mark.parametrize('name, module', [('gd4', G4), ('gd4r', G4R)])
def test_binding_gd4_duoc_dang_ky(name, module):
    b = B.get(name)
    doc = module.build_contract(ROOT)
    integ = module.check_integrity(doc, ROOT)
    assert b.contract_hash(doc) == doc['design_content_sha256']
    assert B.integrity_ok(b, doc, json.dumps(integ)) is True
    assert b.supports_interventions is (name == 'gd4r')
