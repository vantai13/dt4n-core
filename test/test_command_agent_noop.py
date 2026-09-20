"""Ban va 8.4: setBandwidth phai KHONG TAC DUNG PHU KHI LAP, khong chi lu y dang.

`intf.config()` dung lai qdisc -> bo dem goi ve 0 -> 1 tick
unknown(missing_data) (F8-6, do that o 8.3). Vong reconcile gui lai dinh ky se
tao mot tick mu MOI LAN neu khong co no-op.
"""
import types

import pytest

from bridge.command_agent import (
    _clear_lease,
    _sweep_leases,
    h_set_bandwidth,
    lease_state,
)

TARGET = "org.dt4n:link-h1-s1"


class Intf:
    def __init__(self, node):
        self.node = node
        self.config_calls = 0
        self.last_cfg = None

    def config(self, **kwargs):
        self.config_calls += 1
        self.last_cfg = kwargs


def make_net(bw=None):
    link = types.SimpleNamespace(
        intf1=Intf(types.SimpleNamespace(name="h1")),
        intf2=Intf(types.SimpleNamespace(name="s1")),
    )
    if bw is not None:
        link.dt4n_bw = float(bw)
    net = types.SimpleNamespace(links=[link])
    return net, link


@pytest.fixture(autouse=True)
def clean_leases():
    _clear_lease(TARGET)
    yield
    _clear_lease(TARGET)


def test_lap_lai_khong_dung_lai_qdisc():
    net, link = make_net()
    h_set_bandwidth(net, TARGET, {"bw": 7.0})
    calls = link.intf1.config_calls
    ok, code, detail = h_set_bandwidth(net, TARGET, {"bw": 7.0})
    assert link.intf1.config_calls == calls == 1
    assert link.intf2.config_calls == 1
    assert ok and code == 200 and "no-op" in detail
    assert link.dt4n_bw == 7.0


def test_doi_gia_tri_van_ap_dung():
    """Hoi quy Phase 4: doi bw that su thi van phai cham qdisc."""
    net, link = make_net()
    h_set_bandwidth(net, TARGET, {"bw": 7.0})
    calls = link.intf1.config_calls
    ok, code, detail = h_set_bandwidth(net, TARGET, {"bw": 12.0})
    assert link.intf1.config_calls == calls + 1
    assert ok and link.dt4n_bw == 12.0 and "no-op" not in detail


def test_no_op_van_gia_han_lease():
    """Gia han khong duoc keo theo reset qdisc, nhung PHAI day han lease."""
    net, link = make_net()
    h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
    first = lease_state()[TARGET]["expiry_mono"]
    calls = link.intf1.config_calls
    h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
    assert link.intf1.config_calls == calls          # khong cham qdisc
    assert lease_state()[TARGET]["expiry_mono"] >= first   # nhung han duoc day


def test_restore_bw_chup_lan_dau_khong_bi_ghi_de():
    """Bay nguy hiem nhat: ghi de restore_bw moi lan gia han se lam dead-man
    switch phuc hoi ve dung gia tri dang bi gioi han -> vo hieu ma khong bao loi."""
    net, link = make_net(bw=20.0)
    h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
    assert lease_state()[TARGET]["restore_bw"] == 20.0
    for _ in range(3):
        h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
        assert lease_state()[TARGET]["restore_bw"] == 20.0


def test_lenh_khong_kem_lease_huy_lease_cu():
    net, link = make_net(bw=20.0)
    h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
    assert TARGET in lease_state()
    h_set_bandwidth(net, TARGET, {"bw": 20.0})       # revert tuong minh
    assert TARGET not in lease_state()


def test_lease_het_han_thi_tu_phuc_hoi():
    net, link = make_net(bw=20.0)
    h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 15.0})
    expiry = lease_state()[TARGET]["expiry_mono"]
    assert _sweep_leases(net, None, expiry - 1.0) == 0      # chua het han
    assert link.dt4n_bw == 7.0
    assert _sweep_leases(net, None, expiry + 0.1) == 1      # het han
    assert link.dt4n_bw == 20.0
    assert TARGET not in lease_state()


def test_lease_ngoai_dai_bi_tu_choi():
    net, link = make_net(bw=20.0)
    ok, code, _ = h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": 600.0})
    assert not ok and code == 400
    ok, code, _ = h_set_bandwidth(net, TARGET, {"bw": 7.0, "leaseS": "x"})
    assert not ok and code == 400
    assert link.dt4n_bw is None if not hasattr(link, "dt4n_bw") else True


def test_khong_co_lease_thi_khong_co_watchdog_hanh_dong():
    """Hanh vi Phase 4 giu nguyen: lenh khong kem leaseS -> khong bao gio tu revert."""
    net, link = make_net(bw=20.0)
    h_set_bandwidth(net, TARGET, {"bw": 7.0})
    assert _sweep_leases(net, None, 1e9) == 0
    assert link.dt4n_bw == 7.0
