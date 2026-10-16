"""Test GĐ2 — sửa dữ liệu train (s1008) cho ND2.

Ba phần:
  1. cổng client_traffic: TRƯỢT trên s1008 thật, ĐẠT trên 17 run khỏe (dữ liệu có sẵn trong repo);
  2. hợp đồng gd2: khóa bằng hash, đúng bản sao s1008, phát hiện bị sửa;
  3. pipeline envelope: tái lập ĐÚNG số v1 đã công bố; v2-excl; và nhánh v2 chạy hết
     với một run thay thế GIẢ LẬP (bản sao s1007 đổi danh tính) trong thư mục tạm.
Chạy:
    python3 -m pytest -q test/test_gd2.py
"""
import copy
import json
from pathlib import Path

import pytest

from ml import campaign as C
from ml import client_gate as CG
from ml import gd2campaign as G

ROOT = C.ROOT
P5 = C.load_contract(ROOT / 'results/report/experiment_matrix.json')
REC = {r['run_id']: r for r in P5['runs']}


def _snaps(run_id):
    return C.read_snapshots(ROOT / 'data/phase5/raw' / (run_id + '.jsonl'))


def _events(run_id):
    return json.loads((ROOT / 'data/phase5/raw' / (run_id + '.meta.json')).read_text())['events']


# --------------------------------------------------------------------------- 1. cổng
def test_cong_truot_tren_s1008_that():
    rid = 'N-vary-s1008-r2'
    r = CG.client_traffic_check(REC[rid], _snaps(rid), _events(rid))
    assert r['client_traffic_ok'] is False
    assert r['client_traffic']['h1']['frac_ok'] == 0.0
    assert r['client_traffic']['h3']['frac_ok'] == 0.0
    assert r['client_traffic']['h2']['frac_ok'] == 1.0


def test_audit_chi_bat_dung_mot_run():
    rep = CG.audit_phase5(ROOT)
    assert rep['n_runs'] == 18 and rep['failing_runs'] == ['N-vary-s1008-r2']


def test_muc_ke_hoach_thap_nhat():
    assert CG.planned_min_mbps(REC['N-load4M-s1005-r1']) == 4.0
    assert CG.planned_min_mbps(REC['N-vary-s1007-r1']) == 1.0


def _fake(n, tx_by_client, inject=None):
    snaps = [{'things': {'host-%s' % c: {'features': {'traffic': {'txRate': tx(i) * 1e6 / 8}}}
                         for c, tx in tx_by_client.items()}} for i in range(n)]
    events = [{'kind': 'inject', 'tick': inject}] if inject is not None else []
    return snaps, events


def test_nguong_90_phan_tram_tick():
    rec = {'load_mbps_per_client': 2.0}
    ok = lambda i: 2.0                                       # noqa: E731
    gap15 = lambda i: 0.0 if i % 7 == 0 else 2.0             # ~15% tick tụt
    gap5 = lambda i: 0.0 if i % 20 == 0 else 2.0             # ~5% tick tụt
    s, e = _fake(60, {'h1': gap15, 'h2': ok, 'h3': ok})
    assert CG.client_traffic_check(rec, s, e)['client_traffic_ok'] is False
    s, e = _fake(60, {'h1': gap5, 'h2': ok, 'h3': ok})
    assert CG.client_traffic_check(rec, s, e)['client_traffic_ok'] is True


def test_run_loi_chi_xet_cua_so_truoc_inject():
    # Nạn nhân bị bóp về 0 SAU inject là hệ quả của lỗi, không phải lỗi thu dữ liệu.
    rec = {'load_mbps_per_client': 2.0}
    victim = lambda i: 0.0 if i > 20 else 2.0                # noqa: E731
    s, e = _fake(60, {'h1': lambda i: 2.0, 'h2': lambda i: 2.0, 'h3': victim}, inject=20)
    assert CG.client_traffic_check(rec, s, e)['client_traffic_ok'] is True


# --------------------------------------------------------------------------- 2. hợp đồng gd2
def test_hop_dong_gd2_dung_ban_sao_s1008_va_khoa_hash():
    doc = G.build_contract(ROOT)
    rec = doc['runs'][0]
    src = REC['N-vary-s1008-r2']
    assert rec['run_id'] == 'N-vary-s1008-r3' and rec['exec_index'] == 0
    assert {k: v for k, v in rec.items() if k not in ('run_id', 'exec_index')} == \
           {k: v for k, v in src.items() if k not in ('run_id', 'exec_index')}
    assert doc['source_contract_sha256'] == P5['design_content_sha256']
    assert G.check_integrity(doc, ROOT)['match'] is True
    assert G.design_hash(G.build_contract(ROOT)) == doc['design_content_sha256']  # tất định


def test_sua_hop_dong_bi_phat_hien():
    doc = G.build_contract(ROOT)
    bad = copy.deepcopy(doc)
    bad['runs'][0]['seed'] = 9999
    with pytest.raises(RuntimeError):
        G.check_integrity(bad, ROOT)
    bad2 = copy.deepcopy(doc)
    bad2['runs'][0]['seed'] = 9999
    bad2['design_content_sha256'] = G.design_hash(bad2)      # sửa cả hash cho khớp
    with pytest.raises(RuntimeError):                         # vẫn bị bắt: lệch nguồn Phase 5
        G.check_integrity(bad2, ROOT)


def test_duong_dan_gd2_tach_khoi_phase5_raw():
    p = G.run_paths('N-vary-s1008-r3', ROOT)
    assert 'data/phase5/gd2/raw' in str(p['final']).replace('\\', '/')
    assert 'data/phase5/raw/' not in str(p['final']).replace('\\', '/')


def test_verify_gd2_cach_ly_run_co_client_im_lang():
    rid = 'N-vary-s1008-r2'
    checks = G.verify_gd2_run(REC[rid], P5['constants'], _snaps(rid), [])
    assert checks['passed'] is False and 'client_traffic_ok' in checks['failed_gates']
    rid = 'N-vary-s1007-r1'
    checks = G.verify_gd2_run(REC[rid], P5['constants'], _snaps(rid), [])
    assert checks['passed'] is True


def test_binding_gd2_duoc_dang_ky():
    from ml import campaign_binding as B
    b = B.get('gd2')
    doc = G.build_contract(ROOT)
    integ = G.check_integrity(doc, ROOT)
    assert b.contract_hash(doc) == doc['design_content_sha256']
    assert B.integrity_ok(b, doc, json.dumps(integ)) is True
    assert {'phase5', 'phase6r', 'gd2'} <= set(B.BINDINGS)


# --------------------------------------------------------------------------- 3. envelope
def test_tai_lap_dung_so_v1_da_cong_bo():
    from ml import gd2_envelope as GE
    rep = GE.reproduce_check(ROOT)
    assert rep['match'], rep['mismatches']


def test_bo_s1008_doi_nguong_bien_va_nan_nhan_hien_ra():
    from ml import gd2_envelope as GE
    v2 = GE.summary(GE.fit_and_evaluate('v2-excl', ROOT, n_boot=10))
    assert v2['thresholds']['rate_shared']['K'] == 24
    assert abs(v2['thresholds']['primary']['E'] - 5.4964) < 1e-3
    assert v2['owner_K_rate']['run_id'] == 'N-load1M-s1001-r1'
    assert v2['lower_bound_txRate_mbps']['host-h3.traffic.txRate'] > 0.8
    assert v2['victim_visibility']['F-flood-h1_to_srv1-s3005-r1']['h3'] == 13
    assert all(sum(v.values()) == 0 for r, v in v2['victim_visibility'].items()
               if r.startswith('C-'))


def _fake_gd2(tmp: Path):
    """Dựng chiến dịch gd2 GIẢ trong thư mục tạm: run thay thế = bản sao s1007 đổi danh tính."""
    doc = G.build_contract(ROOT)
    doc['provenance'] = {'git_hash': 'test', 'git_dirty': False, 'source_dirty': False}
    rec = doc['runs'][0]
    sha_design = doc['design_content_sha256']
    paths = G.run_paths(rec['run_id'], tmp)
    paths['final'].parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for line in (ROOT / 'data/phase5/raw/N-vary-s1007-r1.jsonl').read_text().splitlines():
        s = json.loads(line)
        s['run'] = dict(s['run'], run_id=rec['run_id'], seed=rec['seed'], exec_index=0,
                        design_content_sha256=sha_design)
        lines.append(json.dumps(s))
    paths['final'].write_text('\n'.join(lines) + '\n')
    sha = C.sha256_file(paths['final'])
    side = json.loads((ROOT / 'data/phase5/raw/N-vary-s1007-r1.meta.json').read_text())
    side.update(run_id=rec['run_id'], record=rec, sha256=sha, design_content_sha256=sha_design,
                collection_provenance={'source_dirty': False, 'git_hash': 'test'})
    paths['meta'].write_text(json.dumps(side))
    manifest = {'complete': True, 'runs': {rec['run_id']: {'sha256': sha, 'status': 'ok'}}}
    (tmp / 'manifest.json').write_text(json.dumps(manifest))
    return doc, (lambda rid: G.run_paths(rid, tmp)), tmp / 'manifest.json'


def test_nhanh_v2_chay_het_va_artifact_hop_le(tmp_path, monkeypatch):
    from ml import gd2_envelope as GE
    from ml.model import EnvelopeModel
    fake = _fake_gd2(tmp_path)
    monkeypatch.setattr(GE, 'gd2_source', lambda root: fake)
    res = GE.fit_and_evaluate('v2', ROOT, n_boot=10)
    assert res['train_run_ids'][-1] == 'N-vary-s1008-r3' and len(res['train_run_ids']) == 8
    assert res['n_train_rows'] == 472
    content, model = GE.build_artifact(res, ROOT)
    out = tmp_path / 'envelope-2.0.0.json'
    model.save(out)
    loaded = EnvelopeModel.load(out)                       # tự kiểm schema + hash
    assert loaded.version == 'envelope-2.0.0'
    assert content['provenance']['replaces'] == 'envelope-1.0.0'
