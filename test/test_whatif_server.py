"""Test GĐ3.4 — server trang what-if. KHÔNG cần Ditto: dùng snapshot Phase 5 hoặc twin giả.

Chạy:
    python3 -m pytest -q test/test_whatif_server.py
"""
import ast
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from whatif import live as L
from whatif import server as S

FLOOD = 'F-flood-h1_to_srv1-s3005-r1'
BOP = [{'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}]


# --------------------------------------------------------------------------- logic hỏi
def test_hoi_khong_hanh_dong_chi_tra_khong_lam_gi():
    body = S.handle_ask({'source': 'snapshot', 'run': FLOOD, 'tick': 30})
    assert set(body['result']) == {'không làm gì'}
    assert len(body['topology']['links']) == 8 and 'không lệnh nào' in body['note'].lower()


def test_hoi_co_hanh_dong_va_restore():
    body = S.handle_ask({'source': 'snapshot', 'run': FLOOD, 'tick': 30,
                         'restore_nominal': True, 'actions': BOP})
    after = body['result']['sau hành động']['prediction']
    assert after['flows']['h3->srv1/tcp']['delivered'] == pytest.approx(2.0)
    assert after['links']['s1->s2']['rho'] == pytest.approx((7 + 2) / 20, abs=0.01)


@pytest.mark.parametrize('payload', [
    {'source': 'ftp'},
    {'source': 'snapshot', 'run': '../../etc/passwd', 'tick': 30},
    {'source': 'snapshot', 'run': 'N-load1M-s1001-r1', 'tick': 30},   # không thuộc tập test
    {'source': 'snapshot', 'run': FLOOD, 'tick': 99},
    {'source': 'snapshot', 'run': FLOOD, 'tick': 30, 'actions': [{'op': 'rm -rf'}]},
    {'source': 'snapshot', 'run': FLOOD, 'tick': 30,
     'actions': [{'op': 'disableLink', 'link': 'h9-s1'}]},              # link không tồn tại
    {'source': 'snapshot', 'run': FLOOD, 'tick': 30, 'actions': BOP * 11},
    ['không', 'phải', 'object'],
])
def test_yeu_cau_sai_tra_400(payload):
    with pytest.raises(S.AskError) as exc:
        S.handle_ask(payload)
    assert exc.value.status == 400


def test_khong_doc_duoc_ditto_tra_503():
    with pytest.raises(S.AskError) as exc:
        S.handle_ask({'source': 'twin'}, read_twin=lambda: ({}, {}, {'source': 'ditto'}))
    assert exc.value.status == 503


def test_twin_qua_cu_tra_409_kem_canh_bao():
    things, ages, _ = L.read_snapshot(FLOOD, 30)
    old = {k: 120.0 for k in ages}
    fake = lambda: (things, old, {'source': 'ditto'})       # noqa: E731
    with pytest.raises(S.AskError) as exc:
        S.handle_ask({'source': 'twin'}, read_twin=fake)
    assert exc.value.status == 409 and exc.value.extra['report']['stale']
    body = S.handle_ask({'source': 'twin', 'allow_stale': True}, read_twin=fake)
    assert 'không làm gì' in body['result']


# --------------------------------------------------------------------------- an toàn
def _imports_and_strings(path):
    """Mọi module được import + mọi hằng chuỗi trong CODE (bỏ docstring)."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    mods, strings = set(), []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module or '')
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            strings.append(n.value)
    return mods, strings


def test_server_chi_doc_khong_co_duong_gui_lenh():
    for f in ('whatif/server.py', 'whatif/live.py', 'whatif/model.py'):
        mods, strings = _imports_and_strings(S.C.ROOT / f)
        assert not any('command' in m or 'pusher' in m for m in mods), (f, mods)
        assert not any('/messages' in s or 'inbox' in s for s in strings), f
    assert S.HOST == '127.0.0.1'


# --------------------------------------------------------------------------- HTTP thật
@pytest.fixture
def base_url(tmp_path, monkeypatch):
    monkeypatch.setattr(S, 'QUERY_LOG', tmp_path / 'q.jsonl')
    srv = S.make_server(0)                              # cổng 0 -> hệ điều hành chọn cổng trống
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d' % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _post(url, data: bytes):
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_trang_va_api(base_url, tmp_path):
    with urllib.request.urlopen(base_url + '/', timeout=10) as r:
        assert r.status == 200 and 'Thử trước khi làm' in r.read().decode('utf-8')
    with urllib.request.urlopen(base_url + '/api/snapshots', timeout=10) as r:
        assert len(json.loads(r.read())['runs']) == 10
    status, body = _post(base_url + '/api/ask', json.dumps(
        {'source': 'snapshot', 'run': FLOOD, 'tick': 30, 'actions': BOP}).encode())
    assert status == 200 and 'sau hành động' in body['result']
    rows = [json.loads(x) for x in (tmp_path / 'q.jsonl').read_text().splitlines()]
    assert rows[-1]['status'] == 200 and rows[-1]['actions'] == BOP


def test_http_loi(base_url):
    assert _post(base_url + '/api/ask', b'{khong phai json')[0] == 400
    assert _post(base_url + '/api/ask', b' ' * (S.MAX_BODY + 1))[0] == 413
    assert _post(base_url + '/api/khong-co', b'{}')[0] == 404
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base_url + '/etc/passwd', timeout=10)
    assert exc.value.code == 404
