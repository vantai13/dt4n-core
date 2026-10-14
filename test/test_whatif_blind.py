"""Test GĐ3.5 — kiểm mù. KHÔNG cần testbed: twin giả = snapshot Phase 5 bình thường,
số đo giả dựng tay. Chạy:
    python3 -m pytest -q test/test_whatif_blind.py
"""
import ast
import json
from pathlib import Path

import pytest

from ml import campaign as C
from whatif import blind as B
from whatif import live as L

NORMAL = lambda: L.read_snapshot('C-load2M-s2001-r1', 30)      # noqa: E731


@pytest.fixture(scope='module')
def doc():
    return B.make_predictions(read=NORMAL)


def items(doc, case):
    return {it['id']: it for it in doc['content']['cases'][case]['items']}


# --------------------------------------------------------------------------- 1. dự đoán
def test_du_doan_tinh_tay_duoc(doc):
    c = doc['content']
    bg = c['inputs_from_twin']['inputs_mbps']['srv1->srv2']
    flood = 8 * c['k_wire_over_nominal']
    one, two = items(doc, 'case1'), items(doc, 'case2')
    assert one['1a']['pred'] == pytest.approx(5.0)                      # bị chặn ở dung lượng
    assert one['1b']['pred'] == pytest.approx(100 * (flood - 5) / (flood + bg))
    assert two['2a']['pred'] == pytest.approx(1.5)
    assert two['2b']['pred'] == pytest.approx(100 * (bg - 1.5) / bg)
    assert two['2t']['pred'] == pytest.approx(1000 * 1512 * 8 / ((bg - 1.5) * 1e6))
    assert c['cases']['case2']['steady_window_s'][0] > two['2t']['pred']   # chấm SAU khi đầy


def test_ca_hai_ca_trong_vung_hop_le_va_co_doi_chung(doc):
    for case in doc['content']['cases'].values():
        assert case['outside_validity'] == []
        assert any(it.get('control') for it in case['items'])


def test_ban_du_doan_khoa_bang_hash(doc):
    assert doc['content_sha256'] == C.sha256_bytes(
        C.canonical_json(doc['content']).encode('utf-8'))


def test_twin_cu_thi_khong_du_doan():
    things, ages, meta = NORMAL()
    with pytest.raises(SystemExit):
        B.make_predictions(read=lambda: (things, {k: 120.0 for k in ages}, meta))


# --------------------------------------------------------------------------- 2. đo
def test_chua_commit_du_doan_thi_khong_cho_do(monkeypatch):
    monkeypatch.setattr(B, 'is_committed_unchanged', lambda rel: False)
    with pytest.raises(SystemExit):
        B.measure('case2')


def test_do_case2_gui_lenh_roi_tra_ve(tmp_path, monkeypatch, doc):
    pred = tmp_path / 'pred.json'
    pred.write_text(json.dumps(doc))
    monkeypatch.setattr(B, 'PRED', str(pred))
    monkeypatch.setattr(B, 'SAMPLES', str(tmp_path / 's_%s_try%d.jsonl'))
    monkeypatch.setattr(B, 'is_committed_unchanged', lambda rel: True)
    sent = []
    monkeypatch.setattr(B, 'send_command', lambda s, t, **p: sent.append((s, t, p)) or 202)
    out = B.measure('case2', read=NORMAL, sleep=lambda s: None)
    lines = Path(out).read_text().splitlines()
    assert len(lines) == 1 + B.MEASURE_S
    assert sent == [('setBandwidth', 'org.dt4n:link-s2-s3', {'bw': 1.5}),
                    ('setBandwidth', 'org.dt4n:link-s2-s3', {'bw': 5.0})]   # luôn trả về
    with pytest.raises(SystemExit):                                       # không ghi đè
        B.measure('case2', read=NORMAL, sleep=lambda s: None)


def test_send_command_dung_duong_dashboard(monkeypatch):
    import requests
    seen = {}
    monkeypatch.setattr(requests, 'post', lambda url, **kw: seen.update(url=url, **kw)
                        or type('R', (), {'status_code': 202})())
    assert B.send_command('setBandwidth', 'org.dt4n:link-s2-s3', bw=1.5) == 202
    assert seen['url'].endswith(':controller/inbox/messages/setBandwidth?timeout=0')
    assert seen['json'] == {'target': 'org.dt4n:link-s2-s3', 'bw': 1.5}


def test_server_khong_import_blind():
    tree = ast.parse((C.ROOT / 'whatif/server.py').read_text(encoding='utf-8'))
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert 'whatif.blind' not in mods and 'blind' not in names


# --------------------------------------------------------------------------- 3. chấm
def fake_rows(rates: dict, loss_link: str, loss_pct: float, loss_from_s: float):
    """Số đo giả: tải từng chiều không đổi; lossPct = 0 trước loss_from_s, sau đó = loss_pct."""
    owners = {'s2-s3': 's2', 's2-srv1': 's2', 's3-srv2': 's3', 's1-s2': 's1', 's1-s3': 's1'}
    rows = []
    for t in range(B.MEASURE_S):
        links = {}
        for key, owner in owners.items():
            a, b = key.split('-')
            other = b if owner == a else a
            links[key] = {'utilIntf': owner + '-eth1', 'rateValid': True, 'qdiscValid': True,
                          'txRate': rates.get('%s->%s' % (owner, other), 0) / 8e-6,
                          'rxRate': rates.get('%s->%s' % (other, owner), 0) / 8e-6,
                          'lossPct': (loss_pct if (key == loss_link and t >= loss_from_s) else 0)}
        rows.append({'rel': float(t), 'links': links})
    return rows


def test_cham_dung_het_khi_so_do_khop(doc):
    case = doc['content']['cases']['case2']
    it = items(doc, 'case2')
    rows = fake_rows({'s2->s3': 1.5, 's3->srv2': it['2c']['pred'], 's1->s2': it['2k1']['pred']},
                     's2-s3', it['2b']['pred'], round(it['2t']['pred']))
    res = B.score_case(case, rows)
    assert [r['verdict'] for r in res] == ['ĐẠT'] * len(res)


def test_cham_truot_khi_muc_mat_hoac_doi_chung_sai(doc):
    case = doc['content']['cases']['case2']
    it = items(doc, 'case2')
    rows = fake_rows({'s2->s3': 1.5, 's3->srv2': it['2c']['pred'], 's1->s2': 3.0},
                     's2-s3', it['2b']['pred'] + 8, round(it['2t']['pred']))
    res = {r['id']: r['verdict'] for r in B.score_case(case, rows)}
    assert res['2b'] == 'TRƯỢT' and res['2k1'] == 'TRƯỢT'
    assert res['2a'] == 'ĐẠT' and res['2t'] == 'ĐẠT'


def test_mat_bat_dau_muon_bi_chi_tieu_thoi_diem_bat(doc):
    # Mất bắt đầu muộn (giây 30 thay vì ~18,5): TRUNG BÌNH trong cửa sổ bị pha loãng nên
    # mức mất có thể vẫn lọt ngưỡng — chính vì vậy cần chỉ tiêu thời điểm (2t) riêng.
    case = doc['content']['cases']['case2']
    it = items(doc, 'case2')
    rows = fake_rows({'s2->s3': 1.5, 's3->srv2': it['2c']['pred'], 's1->s2': it['2k1']['pred']},
                     's2-s3', it['2b']['pred'] + 8, 30)
    res = {r['id']: r['verdict'] for r in B.score_case(case, rows)}
    assert res['2t'] == 'TRƯỢT'
