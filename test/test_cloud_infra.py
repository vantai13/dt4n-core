"""Test GĐ1.1 — dựng/thu phóng/dọn hạ tầng AWS trên AWS GIẢ LẬP (moto).

Không tốn tiền, không cần mạng, không cần key thật. Chạy:
    python3 -m pytest -q test/test_cloud_infra.py
"""
import importlib

import pytest

boto3 = pytest.importorskip('boto3')
moto = pytest.importorskip('moto')


@pytest.fixture
def infra(monkeypatch, tmp_path):
    # Key GIẢ: moto chặn mọi lời gọi, không có gì đi ra AWS thật.
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_REGION', 'ap-southeast-1')
    monkeypatch.setenv('DT4N_ALLOWED_CIDR', '203.0.113.5/32')   # khỏi gọi checkip
    monkeypatch.setenv('DT4N_CLOUD_STATE', str(tmp_path / 'state.json'))
    with moto.mock_aws():
        import cloud.config
        import cloud.infra
        importlib.reload(cloud.config)
        importlib.reload(cloud.infra)
        yield cloud.infra


def _asg(region='ap-southeast-1'):
    groups = boto3.client('autoscaling', region_name=region).describe_auto_scaling_groups(
        AutoScalingGroupNames=['dt4n-asg'])['AutoScalingGroups']
    return groups[0] if groups else None


def test_up_tao_du_tai_nguyen_bat_dau_0_may(infra):
    infra.up()
    g = _asg()
    assert g is not None
    assert (g['MinSize'], g['DesiredCapacity'], g['MaxSize']) == (0, 0, 3)
    assert infra.find_alb(infra.aws('elbv2')) is not None
    assert infra.find_tg(infra.aws('elbv2')) is not None


def test_up_lan_hai_bi_chan(infra):
    infra.up()
    with pytest.raises(SystemExit):
        infra.up()


def test_scale_la_lenh_dat_muc_va_bi_kep_tran(infra):
    infra.up()
    infra.scale(2)
    infra.scale(2)                       # gửi lại: vẫn 2, không thành 4
    assert _asg()['DesiredCapacity'] == 2
    assert len(_asg()['Instances']) == 2
    infra.scale(10)                      # vượt trần -> kẹp về 3
    assert _asg()['DesiredCapacity'] == 3
    infra.scale(-1)                      # âm -> kẹp về 0
    assert _asg()['DesiredCapacity'] == 0


def test_down_don_sach_va_chay_lai_duoc(infra):
    infra.up()
    infra.scale(2)
    infra.down()
    assert _asg() is None
    assert infra.find_alb(infra.aws('elbv2')) is None
    assert infra.find_tg(infra.aws('elbv2')) is None
    infra.down()                         # down lần 2 không lỗi (lũy đẳng)
    infra.up()                           # dựng lại được sau khi dọn
    assert _asg() is not None
