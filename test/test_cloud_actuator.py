"""Test GĐ1.3 — bộ chấp hành cloud trên AWS GIẢ LẬP (moto).

Lưu ý: moto chỉ ĐÁNH DẤU máy Unhealthy, không tự thay máy như AWS thật.
Việc thay máy thật được quan sát qua collector khi chạy trên AWS (GĐ1.5).
Chạy:
    python3 -m pytest -q test/test_cloud_actuator.py
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
        import cloud.actuator
        for mod in (cloud.config, cloud.infra, cloud.twin, cloud.actuator):
            importlib.reload(mod)
        cloud.infra.up()
        yield cloud.infra, cloud.actuator, tmp_path / 'audit.jsonl'


class Counting:
    """Bọc client ASG thật, đếm số lần gọi lệnh GHI; có thể giả lập AWS lỗi."""

    def __init__(self, real, fail=False):
        self.real, self.fail, self.writes = real, fail, 0

    def describe_auto_scaling_groups(self, **kw):
        return self.real.describe_auto_scaling_groups(**kw)

    def set_desired_capacity(self, **kw):
        self.writes += 1
        if self.fail:
            raise RuntimeError('AWS giả lập lỗi mạng')
        return self.real.set_desired_capacity(**kw)

    def set_instance_health(self, **kw):
        self.writes += 1
        return self.real.set_instance_health(**kw)


def _rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _desired(infra):
    return infra.find_asg(infra.aws('autoscaling'))['DesiredCapacity']


def test_ghi_intent_truoc_result_sau(env):
    infra, actuator, audit = env
    act = actuator.CloudActuator(audit_path=audit, push=None)
    r = act.set_capacity(2, reason='test')
    rows = _rows(audit)
    assert [x['kind'] for x in rows] == ['intent', 'result']
    assert rows[0]['cid'] == rows[1]['cid'] == r['cid']
    assert r['outcome'] == 'applied' and r['ok'] is True
    assert _desired(infra) == 2


def test_aws_loi_van_con_intent_va_result_bao_loi(env):
    infra, actuator, audit = env
    client = Counting(infra.aws('autoscaling'), fail=True)
    act = actuator.CloudActuator(audit_path=audit, push=None, asg_client=client)
    r = act.set_capacity(2)
    assert r['ok'] is False and r['outcome'] == 'error' and 'lỗi mạng' in r['error']
    assert [x['kind'] for x in _rows(audit)] == ['intent', 'result']
    assert _desired(infra) == 0


def test_lap_lai_cung_lenh_la_noop_khong_goi_aws(env):
    infra, actuator, audit = env
    client = Counting(infra.aws('autoscaling'))
    act = actuator.CloudActuator(audit_path=audit, push=None, asg_client=client)
    assert act.set_capacity(2)['outcome'] == 'applied'
    assert act.set_capacity(2)['outcome'] == 'noop'
    assert client.writes == 1                       # chỉ gọi AWS một lần
    assert _desired(infra) == 2


def test_kep_tran_va_ghi_ca_so_yeu_cau(env):
    infra, actuator, audit = env
    act = actuator.CloudActuator(audit_path=audit, push=None)
    r = act.set_capacity(10)
    assert r['after'] == 3 and _desired(infra) == 3
    assert _rows(audit)[0]['params'] == {'requested': 10, 'target': 3}


def test_dry_run_ghi_audit_nhung_khong_doi_aws(env):
    infra, actuator, audit = env
    act = actuator.CloudActuator(audit_path=audit, push=None, dry_run=True)
    r = act.set_capacity(2)
    assert r['outcome'] == 'dry_run' and _desired(infra) == 0
    assert _rows(audit)[0]['dry_run'] is True


def test_replace_nham_dung_may_va_lap_lai_an_toan(env):
    infra, actuator, audit = env
    act = actuator.CloudActuator(audit_path=audit, push=None)
    act.set_capacity(2)
    group = infra.find_asg(infra.aws('autoscaling'))
    iid = group['Instances'][0]['InstanceId']
    assert act.replace_instance(iid)['outcome'] == 'applied'
    health = {i['InstanceId']: i['HealthStatus']
              for i in infra.find_asg(infra.aws('autoscaling'))['Instances']}
    assert health[iid] == 'Unhealthy'
    assert list(health.values()).count('Healthy') == 1   # máy kia không bị đụng
    assert act.replace_instance(iid)['outcome'] == 'noop_already_unhealthy'
    assert act.replace_instance('i-khongco0000000')['outcome'] == 'skipped_not_in_group'
    assert _desired(infra) == 2                     # failover KHÔNG đổi số lượng


def test_ghi_lenh_cuoi_len_twin_va_loi_twin_khong_lam_hong_lenh(env):
    infra, actuator, audit = env
    pushes = []
    act = actuator.CloudActuator(audit_path=audit,
                                 push=lambda tid, f: pushes.append((tid, f)) or True)
    act.set_capacity(1, reason='twin')
    tid, f = pushes[-1]
    assert tid == 'org.dt4n:cloud-pool'
    props = f['command']['properties']
    assert props['lastAction'] == 'set_capacity' and props['lastOutcome'] == 'applied'
    assert set(f) == {'command'}                    # không đụng 'pool' của collector

    def broken(tid, f):
        raise RuntimeError('Ditto sập')
    act2 = actuator.CloudActuator(audit_path=audit, push=broken)
    assert act2.set_capacity(2)['outcome'] == 'applied'   # Ditto lỗi, lệnh vẫn chạy


def test_audit_tim_ra_ban_ghi_vo_chu_va_dong_bi_sua(env):
    infra, actuator, audit = env
    act = actuator.CloudActuator(audit_path=audit, push=None)
    act.set_capacity(1)
    orphan = act._intent('cloud-orphan', 'set_capacity', {'target': 2}, 'giả lập sập')
    rep = actuator.check_audit(audit)
    assert rep['chain_ok'] is True and rep['orphans'] == [orphan['cid']]
    lines = audit.read_text().splitlines()
    lines[0] = lines[0].replace('"set_capacity"', '"set_capacityX"')   # sửa lén 1 dòng
    audit.write_text('\n'.join(lines) + '\n')
    assert actuator.check_audit(audit)['chain_ok'] is False
