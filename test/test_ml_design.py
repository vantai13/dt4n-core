import pytest
from ml.design import *

@pytest.fixture
def runs():
    return build_matrix()

def test_tat_dinh_goi_hai_lan_giong_het():
    """Nếu ma trận không tất định thì dataset không tái lập được."""
    assert build_matrix() == build_matrix()


def test_khong_co_fault_nao_trong_tap_train(runs):
    """Bắt buộc: mô hình phải học 'bình thường' từ dữ liệu bình thường.
    Trộn fault vào train -> mô hình học fault là bình thường -> recall sụp."""
    assert [r.run_id for r in runs if r.split == 'train' and r.fault] == []


def test_tap_test_co_run_normal_doi_chung(runs):
    """Không có run normal trong test -> KHÔNG đo được false positive rate."""
    control = [r for r in runs if r.split == 'test' and r.fault is None]
    assert len(control) >= 2


def test_thu_tu_chay_khong_gom_nhom_theo_nhan(runs):
    """Nếu 8 run train chạy liền nhau rồi mới tới test, trạng thái máy trôi
    theo thời gian TRÙNG KHỚP với nhãn -> nhiễu gây lẫn có hệ thống."""
    order = execution_order(runs)
    split = {r.run_id: r.split for r in runs}
    seq = [split[rid] for rid in order]
    switches = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    assert switches >= 4, f'thứ tự gom nhóm quá mạnh, chỉ {switches} lần đổi'


def test_ma_tran_cham_toi_ca_8_link(runs):
    """Lesson 5.1 phát hiện s2-s3 là điểm mù (AUC 0.496). Ma trận PHẢI phủ nó."""
    touched = set()
    for r in runs:
        touched |= set(r.expected_links)
    assert set(ALL_LINKS) <= touched, f'chưa phủ: {set(ALL_LINKS) - touched}'


def test_base_rate_nam_trong_khoang_doc_duoc(runs):
    """base_rate = 100% (như file injection pilot v2) thì không đo được
    FPR lẫn detection delay. Phải biết TRƯỚC khi chạy, không phải sau."""
    br = expected_base_rate(runs)
    assert 0.10 <= br <= 0.40, br


def test_du_doan_admin_down_gom_ca_duong_di():
    """Định tuyến TĨNH: hạ s1-s2 thì luồng h1->srv1 và h3->srv1 chết hẳn,
    nên cả h1-s1, h3-s1, s2-srv1 đều đổi theo. Không reroute sang s1-s3."""
    got = expected_affected_links('admin_down', 's1-s2')
    assert got == ['h1-s1', 'h3-s1', 's1-s2', 's2-srv1']
    assert 's1-s3' not in got


def test_collector_version_khong_phai_v1_hay_v2():
    """ML_PREFLIGHT cảnh báo không trộn lossPct v1 (interface) với v2 (qdisc).
    Lesson 5.2 thêm rateValid -> phải là version MỚI, không tái dùng v2."""
    meta = snapshot_metadata(build_matrix()[0], 0, git_provenance())
    assert meta['collector_version'] not in ('v1', 'v2', 'v2-qdisc')
    assert 'ratevalid' in meta['collector_version'].lower()


def test_validate_matrix_bat_duoc_fault_lot_vao_train(runs):
    """Kiểm tra chính phép kiểm: nếu fault lọt vào train, gate PHẢI đỏ."""
    import dataclasses
    bad = list(runs)
    f = next(r for r in bad if r.fault)
    bad[bad.index(f)] = dataclasses.replace(f, split='train')
    checks = validate_matrix(bad)
    assert checks['no_fault_in_train'] is False
    assert checks['all_pass'] is False


def test_varying_load_dung_run_host_shell_khong_dung_host_cmd(monkeypatch):
    """Bẫy đã gặp: host.cmd() đi qua shell tương tác duy nhất của node ->
    tranh chấp với collector -> Mininet nổ assertion self.waiting."""
    from types import SimpleNamespace
    from mininet import traffic

    cmds = []
    hosts = {n: SimpleNamespace(name=n, IP=lambda ip=ip: ip,
                                cmd=lambda c: pytest.fail('dùng host.cmd()!'))
             for n, ip in [('h1', '10.0.0.1'), ('h2', '10.0.0.2'),
                           ('h3', '10.0.0.3'), ('srv1', '10.0.0.4'),
                           ('srv2', '10.0.0.5')]}
    net = SimpleNamespace(hosts=list(hosts.values()), get=hosts.__getitem__)
    monkeypatch.setattr(traffic, 'run_host_shell',
                        lambda h, c, **k: cmds.append((h.name, c)))
    monkeypatch.setattr(traffic.time, 'sleep', lambda _: None)

    traffic.start_varying_load(net, ((0, 1.0), (10, 3.0), (20, 2.0)), duration=30)
    client_cmds = {n: c for n, c in cmds if n.startswith('h') and 'iperf -c' in c}
    assert set(client_cmds) == {'h1', 'h2', 'h3'}
    for cmd in client_cmds.values():
        assert cmd.count('iperf -c') == 3          # ba bậc nối tiếp
        assert 'setsid sh -c' in cmd and '& echo $!' in cmd          # chạy nền, không blocking
    firsts = {n: c.split('-b ')[1].split('M')[0] for n, c in client_cmds.items()}
    assert len(set(firsts.values())) == 3, firsts   # rotate=True có tác dụng


def test_link_admin_down_goi_configLinkStatus_dung_chieu():
    """LinkDown cũ chỉ thắt bw -> status.state vẫn 'up' -> 16 cột state_up
    chết. LinkAdminDown hạ link THẬT bằng cùng cơ chế command_agent dùng."""
    from types import SimpleNamespace
    from rl.scenarios import LinkAdminDown

    calls = []

    def link(a, b):
        return SimpleNamespace(
            intf1=SimpleNamespace(node=SimpleNamespace(name=a)),
            intf2=SimpleNamespace(node=SimpleNamespace(name=b)))

    net = SimpleNamespace(
        links=[link('s1', 's2'), link('s1', 's3')],
        configLinkStatus=lambda a, b, st: calls.append((a, b, st)))
    sc = LinkAdminDown('s1-s2')
    sc.apply(net)
    assert calls == [('s1', 's2', 'down')] and sc._applied
    sc.revert(net)
    assert calls[-1] == ('s1', 's2', 'up') and not sc._applied
    sc.revert(net)                      # idempotent
    assert sc.describe()['type'] == 'LinkAdminDown'


@pytest.mark.parametrize('schedule,duration', [
    ((),60), (((0,1),(0,2)),60), (((1,1),),60),
    (((0,1),(10,2)),10), (((0,0),),60), (((0,float('nan')),),60),
    (((0,1),(0.5,2)),60), (((0,1),),0)])
def test_invalid_schedule_rejected(schedule,duration):
    from mininet.traffic import schedule_segments
    with pytest.raises(ValueError):
        schedule_segments(schedule,duration)


def test_schedule_preserves_rates_and_total_duration():
    from mininet.traffic import schedule_segments
    assert schedule_segments(((0,1),(10,3),(20,2)),30) == ((1,10),(3,10),(2,10))


@pytest.mark.parametrize('fault_run', [r for r in build_matrix() if r.fault], ids=lambda r:r.run_id)
def test_seeded_scenario_uses_locked_target(fault_run):
    from ml.design import scenario_for_run,fault_parameters
    a,b = scenario_for_run(fault_run),scenario_for_run(fault_run)
    assert a.describe() == b.describe()
    p = fault_parameters(fault_run)
    if fault_run.fault == 'flood':
        assert f'{p["src"]}->{p["dst"]}' == fault_run.fault_target
    else:
        assert p['link_key'] == fault_run.fault_target
    if fault_run.fault in ('degrade','shift'):
        capacity = max(1,p['baseline']*(1-p['factor']))
        assert capacity < (2 if fault_run.fault_target=='s2-s3' else 4)


def test_missing_coverage_fails_the_actual_gate(runs):
    from dataclasses import replace
    bad = [replace(r,expected_links=()) if r.fault else r for r in runs]
    assert not validate_matrix(bad)['all_links_covered']
    assert not validate_matrix(bad)['all_pass']


@pytest.mark.parametrize('start,end', [(40,20),(20,65),(0,40)])
def test_invalid_fault_window_fails(runs,start,end):
    from dataclasses import replace
    bad = list(runs)
    bad[-1] = replace(bad[-1],t_inject=start,t_revert=end)
    assert not validate_matrix(bad)['all_pass']


def test_order_must_contain_each_run_once(runs):
    from ml.design import matrix_to_records
    with pytest.raises(ValueError):
        matrix_to_records(runs,[r.run_id for r in runs[:-1]])


def test_git_failure_cannot_masquerade_as_clean_source(tmp_path):
    with pytest.raises(RuntimeError):
        git_provenance(tmp_path)


def test_flow_paths_follow_actual_routing():
    from ml.design import route_paths,FLOW_PATHS
    assert route_paths() == FLOW_PATHS


def test_stop_varying_load_terminates_future_shell_steps(tmp_path):
    import os,shlex,subprocess,time
    from types import SimpleNamespace
    from mininet.traffic import stop_varying_load
    marker = tmp_path/'pid'
    evidence = tmp_path/'restarted'
    body = 'sleep 1; echo restarted > '+shlex.quote(str(evidence))
    proc = subprocess.Popen(['setsid','sh','-c',body])
    marker.write_text(str(proc.pid))
    host = SimpleNamespace(_dt4n_varying_marker=str(marker))
    def run(_host,command,**kwargs):
        return subprocess.run(command,shell=True,capture_output=True,text=True).stdout
    from unittest.mock import patch
    try:
        for _ in range(100):
            if os.getpgid(proc.pid)==proc.pid:
                break
            time.sleep(.01)
        else:
            pytest.fail('process group did not initialize')
        with patch('mininet.traffic.run_host_shell',run):
            stop_varying_load(host)
        proc.wait(timeout=2)
        assert proc.returncode != 0
        assert not evidence.exists() and not marker.exists()
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,15)
            proc.wait()
