"""Test luat dinh vi 8.1. Luat khong co tham so tu do nen liet ke duoc HET."""
import itertools
import json
from pathlib import Path

import pytest

from controller.localize import (
    AMBIGUOUS,
    NO_CLIENT,
    SINGLE,
    Localization,
    client_candidates,
    localize,
    roles_from_snapshot,
)

ROLES = {
    "h1": "client",
    "h2": "client",
    "h3": "client",
    "srv1": "server",
    "srv2": "server",
}
H = "org.dt4n:host-"
ROOT = Path(__file__).resolve().parents[1]


def test_thuan_khong_io():
    """localize.py phai THUAN: khong dong ho, khong random, khong I/O."""
    source = (ROOT / "controller/localize.py").read_text(encoding="utf-8")
    for forbidden in (
        "import time",
        "import random",
        "import requests",
        "import os",
        "open(",
        "Path(",
        "datetime",
    ):
        assert forbidden not in source, "localize.py phai THUAN, thay: %s" % forbidden


@pytest.mark.parametrize(
    "subset",
    [s for n in range(len(ROLES) + 1) for s in itertools.combinations(sorted(ROLES), n)],
)
def test_liet_ke_moi_to_hop(subset):
    """Liet ke toan bo 2^5 = 32 tap con host. Khong to hop nao ra hanh vi la."""
    affected = [H + name for name in subset]
    loc = localize(affected, ROLES)
    clients = [name for name in subset if ROLES[name] == "client"]
    if len(clients) == 0:
        assert loc.target is None and loc.reason == NO_CLIENT
    elif len(clients) == 1:
        assert loc.target == clients[0] and loc.reason == SINGLE
    else:
        assert loc.target is None and loc.reason == AMBIGUOUS
    assert list(loc.candidates) == sorted(clients)


def test_server_khong_bao_gio_la_muc_tieu():
    """srv1 luon co trong affected luc flood. No KHONG duoc thanh muc tieu."""
    loc = localize([H + "srv1", H + "h1"], ROLES)
    assert loc.target == "h1"


def test_link_va_switch_bi_bo_qua():
    loc = localize(["org.dt4n:link-h1-s1", "org.dt4n:switch-s1"], ROLES)
    assert loc.target is None and loc.reason == NO_CLIENT


def test_affected_rong_va_none():
    for affected in ([], None, ()):
        assert localize(affected, ROLES).target is None


def test_khong_hardcode_ten_host():
    """Topology doi (h4, h5) thi luat van dung."""
    roles = {"h4": "client", "h5": "client", "srv9": "server"}
    assert localize([H + "h4"], roles).target == "h4"
    assert localize([H + "h4", H + "h5"], roles).target is None


def test_bo_qua_id_la_va_trung_lap():
    assert client_candidates([H + "h1", H + "h1", 17, None, "h1"], ROLES) == ("h1",)
    assert client_candidates(["other:host-h1"], ROLES) == ()


def test_ket_qua_bat_bien():
    loc = localize([H + "h1"], ROLES)
    with pytest.raises(Exception):
        loc.target = "h2"  # frozen dataclass
    assert isinstance(loc, Localization)


def test_ham_thuan_lap_lai_cho_ket_qua_giong_nhau():
    affected = [H + "h1", H + "srv1"]
    assert localize(affected, ROLES) == localize(affected, ROLES)


def test_roles_from_snapshot():
    snapshot = {
        "things": {
            "host-h1": {"attributes": {"type": "host", "role": "client"}},
            "host-srv1": {"attributes": {"type": "host", "role": "server"}},
            "link-h1-s1": {"attributes": {"type": "link"}},
        }
    }
    assert roles_from_snapshot(snapshot) == {"h1": "client", "srv1": "server"}


# --- Bat bien phai giu dung voi receipt cua probe (bo qua neu chua chay probe) ---

PROBE = ROOT / "results/report/phase8_actionability.json"


def _probe():
    if not PROBE.exists():
        pytest.skip("chua chay scripts/probe_phase8_actionability.py")
    return json.loads(PROBE.read_text(encoding="utf-8"))


def test_probe_khong_hanh_dong_tren_run_khong_flood():
    """C2 offline: admin_down / shift / degrade / none -> khong bao gio co muc tieu."""
    for row in _probe()["runs"]:
        if row.get("fault") == "flood":
            continue
        assert row.get("latched_target") is None, row["run_id"]


def test_probe_flood_luon_chi_dung_thu_pham():
    rows = [r for r in _probe()["runs"] if r.get("fault") == "flood"]
    assert rows, "khong tim thay run flood nao"
    for row in rows:
        expected = (row["fault_target"] or "").split("->")[0].strip()
        assert row["latched_target"] == expected, row["run_id"]


def test_probe_latch_khac_danh_gia_moi_tick():
    """Bang chung recovery burst: latch la bat buoc, khong phai trang tri."""
    assert _probe()["summary"]["latch_vs_per_tick_differs"]
