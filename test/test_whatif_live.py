"""Test GĐ3.3 — what-if từ trạng thái twin. KHÔNG cần Ditto thật.

Đường đọc Ditto được thử bằng một session GIẢ trả về Thing dựng bởi CHÍNH adapter của repo
(bridge/adapter.collector_to_things) từ một snapshot Phase 5 -> đúng dạng 'properties' của
twin thật. Chạy:
    python3 -m pytest -q test/test_whatif_live.py
"""
import copy
import io
import json
import time
from contextlib import redirect_stdout

import pytest

from bridge.adapter import collector_to_things
from bridge.ditto_common import DITTO_BASE_URL
from ml import campaign as C
from whatif import live as L

FLOOD = 'F-flood-h1_to_srv1-s3005-r1'


def snapshot(rid, tick):
    return next(s for s in C.read_snapshots(C.run_paths(rid)['final']) if s['tick'] == tick)


class FakeSession:
    """Giả requests.Session: GET /things/<id> trả Thing theo dạng Ditto."""
    def __init__(self, bodies):
        self.bodies = bodies

    def get(self, url, timeout=None):
        tid = url.rsplit('/things/', 1)[-1]
        body = self.bodies.get(tid)

        class R:
            status_code = 200 if body is not None else 404
            def json(self_inner):
                return copy.deepcopy(body)
        return R()


def ditto_bodies(snap, age_s=1.0):
    """Dựng Thing dạng Ditto từ snapshot bằng adapter thật; tSource = bây giờ − age_s."""
    out = {}
    for tid, body in collector_to_things(snap).items():
        short = 'host-' + tid.split(':host-')[1] if ':host-' in tid else \
            'link-' + tid.split(':link-')[1] if ':link-' in tid else None
        if short is None or short not in snap['things']:
            continue
        body = dict(body, thingId=tid, attributes=snap['things'][short]['attributes'])
        body['features']['meta'] = {'properties': {'tSource': time.time() - age_s}}
        out[tid] = body
    return out


# --------------------------------------------------------------------------- đọc
def test_twin_va_snapshot_cho_cung_mot_state():
    snap = snapshot(FLOOD, 30)
    t_things, t_ages, _ = L.read_twin(FakeSession(ditto_bodies(snap)))
    s_things, s_ages, _ = L.read_snapshot(FLOOD, 30)
    st_t, rep_t = L.state_from_things(t_things, t_ages)
    st_s, rep_s = L.state_from_things(s_things, s_ages)
    assert st_t.capacity == st_s.capacity and st_t.down == st_s.down
    assert [(d.name, round(d.mbps, 6)) for d in st_t.demands] == \
           [(d.name, round(d.mbps, 6)) for d in st_s.demands]
    assert rep_t['ok'] is True and 0.5 < rep_t['max_age_s'] < 5


def test_thing_qua_cu_thi_khong_ok():
    snap = snapshot('C-load2M-s2001-r1', 30)
    things, ages, _ = L.read_twin(FakeSession(ditto_bodies(snap, age_s=120)))
    _, rep = L.state_from_things(things, ages)
    assert rep['ok'] is False and len(rep['stale']) == 13


def test_thieu_thing_thi_khong_ok():
    snap = snapshot('C-load2M-s2001-r1', 30)
    bodies = ditto_bodies(snap)
    bodies.pop('org.dt4n:link-s1-s2')
    things, ages, meta = L.read_twin(FakeSession(bodies))
    _, rep = L.state_from_things(things, ages)
    assert rep['ok'] is False and rep['missing'] == ['link-s1-s2']


def test_rate_khong_hop_le_thi_bo_so_cu():
    # merge-patch giữ số cũ: twin còn txRate = 99 MB/s nhưng rateValid = false
    things, ages, _ = L.read_snapshot('C-load2M-s2001-r1', 30)
    things['host-h2']['features']['traffic'].update(rateValid=False, txRate=99e6)
    state, rep = L.state_from_things(things, ages)
    assert rep['inputs_mbps']['h2->srv2'] == pytest.approx(2.0)
    assert any('h2 không có txRate hợp lệ' in w for w in rep['warnings'])


def test_link_tat_va_bang_thong_lay_tu_twin():
    st, rep = L.state_from_things(*L.read_snapshot('F-admin_down-s1-s2-s3001-r1', 30)[:2])
    assert rep['down'] == ['s1-s2'] and st.down == {'s1-s2'}
    st, rep = L.state_from_things(*L.read_snapshot('F-degrade-s2-s3-s3004-r1', 30)[:2])
    assert rep['capacity_changed'] == {'s2-s3': 1.0}


# --------------------------------------------------------------------------- bẫy "nhu cầu bị kiểm duyệt"
def test_dang_flood_thi_canh_bao_va_h3_bi_doc_thap():
    st, rep = L.state_from_things(*L.read_snapshot(FLOOD, 30)[:2])
    assert rep['inputs_mbps']['h3->srv1'] < 0.1                # TCP đã lùi
    assert any('gấp' in w for w in rep['warnings'])             # h1 gửi gấp 10 lần
    assert any('nghẽn' in w for w in rep['warnings'])
    r = L.ask(st, [{'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}])
    assert r['hành động']['prediction']['flows']['h3->srv1/tcp']['delivered'] < 0.1


def test_restore_nominal_tra_loi_cau_go_nghen_thi_sao():
    st, rep = L.state_from_things(*L.read_snapshot(FLOOD, 30)[:2], restore_nominal=True)
    assert set(rep['restored_from']) == {'h3'} and rep['restored_from']['h3'] < 0.1
    assert rep['inputs_mbps']['h3->srv1'] == pytest.approx(2.0)
    r = L.ask(st, [{'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}])
    h3 = r['hành động']['prediction']['flows']['h3->srv1/tcp']
    assert h3['delivered'] == pytest.approx(2.0) and h3['outside_validity'] is False


# --------------------------------------------------------------------------- CLI
def test_parse_actions():
    ns = type('NS', (), {'disable': ['s1-s2'], 'enable': None, 'set_bw': ['h1-s1=7'],
                         'flood': ['h1:srv1:50']})()
    assert L.parse_actions(ns) == [
        {'op': 'disableLink', 'link': 's1-s2'},
        {'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7.0},
        {'op': 'addDemand', 'src': 'h1', 'dst': 'srv1', 'mbps': 50.0, 'kind': 'udp'}]


def test_cli_json_tu_snapshot():
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = L.main(['ask', '--snapshot', FLOOD + ':30', '--set-bw', 'h1-s1=7', '--json'])
    out = json.loads(buf.getvalue())
    assert code == 0 and set(out['result']) == {'không làm gì', 'hành động'}


def test_cli_khong_co_ditto_thi_tu_choi(monkeypatch):
    monkeypatch.setattr(L, 'read_twin', lambda: ({}, {}, {'source': 'ditto'}))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert L.main(['now']) == 3
    assert 'Không đọc được' in buf.getvalue()
