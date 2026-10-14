"""Test GĐ1.2 — cloud collector trên AWS GIẢ LẬP (moto) và Ditto GIẢ (một list).

Không cần AWS thật, không cần Ditto chạy. Chạy:
    python3 -m pytest -q test/test_cloud_collector.py
"""
import importlib
import json

import pytest

moto = pytest.importorskip('moto')


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_REGION', 'ap-southeast-1')
    monkeypatch.setenv('DT4N_ALLOWED_CIDR', '203.0.113.5/32')
    monkeypatch.setenv('DT4N_CLOUD_STATE', str(tmp_path / 'state.json'))
    with moto.mock_aws():
        import cloud.config
        import cloud.infra
        import cloud.twin
        import cloud.collector
        for mod in (cloud.config, cloud.infra, cloud.twin, cloud.collector):
            importlib.reload(mod)
        yield cloud.infra, cloud.collector, cloud.twin, tmp_path


class FakeDitto:
    """Thay cho Ditto: ghi lại mọi lần đẩy."""

    def __init__(self, ok=True):
        self.ok, self.pushes = ok, []

    def __call__(self, thing_id, features):
        self.pushes.append((thing_id, features))
        return self.ok


def _clients(infra):
    return infra.aws('autoscaling'), infra.aws('elbv2')


def test_read_pool_dem_dung_so_may(env):
    infra, collector, _, _ = env
    infra.up()
    infra.scale(2)
    snap = collector.read_pool(*_clients(infra))
    assert (snap['desired'], snap['min'], snap['max']) == (2, 0, 3)
    assert snap['total'] == 2
    assert snap['inService'] == 2
    assert snap['healthy'] == 2            # moto báo ALB healthy ngay
    ids = [x['id'] for x in snap['instances']]
    assert ids == sorted(ids)              # thứ tự cố định -> dễ so sánh


def test_cycle_day_du_feature_va_dong_dau_tSource(env):
    infra, collector, twin, tmp = env
    infra.up()
    infra.scale(1)
    ditto = FakeDitto()
    log = tmp / 'c.jsonl'
    snap, ok = collector.cycle(*_clients(infra), ditto, log_path=log)
    assert ok
    thing_id, features = ditto.pushes[-1]
    assert thing_id == twin.THING_ID == 'org.dt4n:cloud-pool'
    assert set(features) == {'capacity', 'pool', 'instances', 'meta'}
    meta = features['meta']['properties']
    assert meta['pollOk'] is True and meta['tSource'] == snap['t_source']
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]['healthy'] == 1


def test_loi_aws_chi_bao_loi_khong_ghi_tSource_moi(env):
    infra, collector, _, _ = env           # KHÔNG up -> ASG không tồn tại
    ditto = FakeDitto()
    snap, _ = collector.cycle(*_clients(infra), ditto)
    assert snap is None
    _, features = ditto.pushes[-1]
    assert set(features) == {'meta'}
    props = features['meta']['properties']
    assert props['pollOk'] is False and 'tSource' not in props
    assert 'ASG' in props['lastError']


def test_may_bi_xoa_bien_mat_khoi_twin(env):
    infra, collector, _, _ = env
    infra.up()
    infra.scale(2)
    ditto = FakeDitto()
    collector.cycle(*_clients(infra), ditto)
    assert len(ditto.pushes[-1][1]['instances']['properties']['list']) == 2
    infra.scale(0)
    collector.cycle(*_clients(infra), ditto)
    # mảng được thay nguyên -> không còn máy "ma" trong twin
    assert ditto.pushes[-1][1]['instances']['properties']['list'] == []


def test_thing_body_dung_type_va_policy(env):
    _, _, twin, _ = env
    body = twin.thing_body()
    assert body['attributes']['type'] == 'cloud-pool'
    assert body['policyId'] == 'org.dt4n:default-policy'
    assert body['attributes']['maxSize'] == 3


def test_run_moi_chu_ky_deu_day_ke_ca_khi_khong_doi(env):
    infra, collector, _, tmp = env
    infra.up()
    ditto = FakeDitto()
    collector.run(period=0.01, push=ditto, log_path=tmp / 'r.jsonl', max_cycles=3)
    assert len(ditto.pushes) == 3          # nhịp tim: twin luôn biết dữ liệu còn tươi
    t = [f['meta']['properties']['tSource'] for _, f in ditto.pushes]
    assert t[0] < t[1] < t[2]
