"""Test hop dong A-E cua Phase 8.3 (khong can Mininet, khong can Ditto)."""
import json
import types
from pathlib import Path

import pytest

from bridge.controlloop_contract import (
    CONTROLLOOP_THING_ID,
    MODES,
    build_document,
    check_document,
    initial_controlloop_body,
)
from controller.intervene import ACTION_NAME, SUBJECT, to_command, to_intervention
from controller.policy import ControllerState, DetectorView, PolicyParams, decide
from ml.blast_radius import Routing
from ml.intervention_log import InMemoryInterventionLog

ROOT = Path(__file__).resolve().parents[1]
ROLES = (("h1", "client"), ("h2", "client"), ("h3", "client"),
         ("srv1", "server"), ("srv2", "server"))
H1 = "org.dt4n:host-h1"


def routing():
    return Routing.load(ROOT / "ditto/routing_table.json")


def act_view():
    return DetectorView("act", "", (H1,), ROLES, True, "b3f", 1)


# ------------------------------------------------------- hop dong A: firewall


def test_controller_khong_doc_tat_runner():
    """Hop dong A: controller la CONSUMER cua twin, khong phai ban cung nha."""
    for path in sorted((ROOT / "controller").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("detector_runner", "DetectorRunner",
                          "runner.published", "runner.timeline"):
            assert forbidden not in source, "%s doc tat qua %s" % (path.name, forbidden)


def test_twin_reader_dung_dung_endpoint():
    """Cung endpoint Things ma dashboard dung: mot nguon su that."""
    from controller.twin_reader import SSE_PATH

    js = (ROOT / "dashboard/src/services/sseClient.js").read_text(encoding="utf-8")
    assert "fields=thingId,attributes,features" in SSE_PATH
    assert "fields=thingId,attributes,features" in js
    assert "namespaces=" in SSE_PATH


# ------------------------------------------------------- hop dong B: can thiep


def test_intervention_dung_radius_khong_dung_detour():
    """setBandwidth khong doi topology -> khong co hanh lang vong -> `radius`."""
    from ml.blast_radius import radius, radius_with_detour

    r = routing()
    actions, _ = decide(act_view(), ControllerState(), 0.0, PolicyParams())
    item = to_intervention(actions[0], r, 1000.0)
    targets = {"links": ["h1-s1"], "flows": []}
    assert item.blast_radius == radius(r, targets)
    assert len(item.blast_radius) == 15
    # voi h1-s1 hai ham trung nhau, nhung luat da ghim van bat goi dung ham
    assert item.blast_radius == radius_with_detour(r, targets)
    assert item.routing_sha256 == r.sha256


def test_khong_dung_flows_vi_lam_mu_ca_mang():
    from ml.blast_radius import radius

    r = routing()
    assert len(radius(r, {"links": [], "flows": [["h1", "srv1"]]})) == 16
    assert len(radius(r, {"links": ["h1-s1"], "flows": []})) == 15


def test_ten_hanh_dong_rieng_khong_tron_voi_admin_down():
    r = routing()
    actions, cs = decide(act_view(), ControllerState(), 0.0, PolicyParams())
    item = to_intervention(actions[0], r, 1000.0)
    assert item.action == "inject:rate_limit" != "inject:admin_down"
    assert item.kind == "inject"
    assert ACTION_NAME["revert"] == "revert:rate_limit"


def test_inject_va_revert_cung_pair_key():
    """Neu lech pair_key, InterventionLog khong bao gio dong duoc khoang ->
    lease 120 s het han moi lan -> stale_intervention gia."""
    r = routing()
    params = PolicyParams()
    acts, cs = decide(act_view(), ControllerState(), 0.0, params)
    acts2, _ = decide(act_view(), cs, 1000.0, params)     # het gio giu -> revert
    assert acts2[0].kind == "revert"
    inject = to_intervention(acts[0], r, 100.0)
    revert = to_intervention(acts2[0], r, 120.0)
    assert inject.pair_key == revert.pair_key


def test_log_dong_duoc_khoang_va_khong_cham_lease():
    """Vong doi that: append inject roi revert -> khong con lease treo."""
    from ml.intervention_log import MAX_OPEN_S

    r = routing()
    params = PolicyParams()
    log = InMemoryInterventionLog()
    acts, cs = decide(act_view(), ControllerState(), 0.0, params)
    log.append(to_intervention(acts[0], r, 100.0))
    acts2, _ = decide(act_view(), cs, 15.0, params)
    log.append(to_intervention(acts2[0], r, 115.0))
    assert log.stale_open(100.0 + MAX_OPEN_S + 1.0) == []
    assert log.active(116.0, 8.0)          # con cooldown
    assert not log.active(130.0, 8.0)      # da het


def test_append_hai_lan_cung_id_thi_no():
    """Vong reconcile KHONG duoc append lai: id tat dinh -> ValueError."""
    r = routing()
    log = InMemoryInterventionLog()
    acts, _ = decide(act_view(), ControllerState(), 0.0, PolicyParams())
    item = to_intervention(acts[0], r, 100.0)
    log.append(item)
    with pytest.raises(ValueError):
        log.append(to_intervention(acts[0], r, 101.0))


# ------------------------------------------------------- hop dong C: lenh


def test_lenh_tuyet_doi_va_cid_tat_dinh():
    acts, _ = decide(act_view(), ControllerState(), 0.0, PolicyParams())
    command = to_command(acts[0])
    assert command["subject"] == SUBJECT == "setBandwidth"
    assert command["target"] == "org.dt4n:link-h1-s1"
    assert command["params"] == {"bw": 7.0}          # TUYET DOI
    assert command["cid"] == acts[0].intervention_id  # correlation id = iid
    assert "uuid" not in json.dumps(command)


def test_lenh_lu_y_dang_gui_hai_lan_bang_mot_lan():
    """Hop dong C: at-least-once + lu y dang = hieu ung exactly-once."""
    from bridge.command_agent import h_set_bandwidth

    node_a = types.SimpleNamespace(name="h1")
    node_b = types.SimpleNamespace(name="s1")
    calls = []

    class Intf:
        def __init__(self, node):
            self.node = node

        def config(self, **kwargs):
            calls.append(kwargs)

    link = types.SimpleNamespace(intf1=Intf(node_a), intf2=Intf(node_b))
    net = types.SimpleNamespace(links=[link])

    first = h_set_bandwidth(net, "org.dt4n:link-h1-s1", {"bw": 7.0})
    bw_after_first = link.dt4n_bw
    second = h_set_bandwidth(net, "org.dt4n:link-h1-s1", {"bw": 7.0})
    assert first[1] == second[1] == 200 and first[0] is second[0] is True
    assert link.dt4n_bw == bw_after_first == 7.0
    assert all(call["bw"] == 7.0 for call in calls)


def test_send_command_nhan_cid_tuong_minh():
    """Sua 1 dong o env_runner: caller MOI ghim duoc cid."""
    source = (ROOT / "mininet/env_runner.py").read_text(encoding="utf-8")
    assert "def send_command(self, cmd, cid=None):" in source
    assert "cid = str(cid or cmd.get('cid') or uuid.uuid4())" in source


def test_khong_coi_202_la_hieu_luc():
    """Kenh xac nhan la capacity.bwMbps, khong phai ma HTTP."""
    for name in ("twin_reader.py", "intervene.py"):
        source = (ROOT / "controller" / name).read_text(encoding="utf-8")
        assert "202" not in source


# ------------------------------------------------------- hop dong D: Thing


def test_khoi_tao_fail_safe_khong_bao_gio_idle():
    body = initial_controlloop_body("org.dt4n:default-policy")
    decision = body["features"]["decision"]["properties"]
    assert decision["mode"] == "HOLD"
    assert decision["reason"] == "never_started"
    assert decision["mode"] != "IDLE"
    assert body["features"]["freshness"]["properties"]["seq"] == -1
    assert check_document(body) == []


def test_document_khong_bao_gio_co_null():
    params = PolicyParams()
    acts, cs = decide(act_view(), ControllerState(), 0.0, params)
    document = build_document(
        cs, params, boot_id="b3f", seq=7, heartbeat_at="2026-09-20T10:03:47Z",
        decided_at="2026-09-20T10:03:47Z", now_mono=3.0, dropped=0,
        provenance={"policySha256": "x"},
    )
    assert check_document(document) == []
    assert "null" not in json.dumps(document)
    assert document["features"]["decision"]["properties"]["target"] == "h1"


def test_state_idle_van_khong_sinh_null():
    params = PolicyParams()
    document = build_document(
        ControllerState(mode="IDLE"), params, boot_id="b", seq=1,
        heartbeat_at="t", decided_at="t", now_mono=0.0, dropped=0, provenance={},
    )
    assert check_document(document) == []
    assert document["features"]["decision"]["properties"]["target"] == ""
    assert document["features"]["decision"]["properties"]["limitMbps"] == 0.0


def test_lich_la_khoang_khong_phai_moc():
    params = PolicyParams()
    acts, cs = decide(act_view(), ControllerState(), 100.0, params)
    document = build_document(
        cs, params, boot_id="b", seq=1, heartbeat_at="2026-09-20T10:00:00Z",
        decided_at="2026-09-20T10:00:00Z", now_mono=105.0, dropped=0, provenance={},
    )
    schedule = document["features"]["schedule"]["properties"]
    assert schedule["holdRemainingS"] == 10.0        # 115 - 105, KHOANG
    assert "holdUntil" not in schedule
    # khong moc wall clock nao trong schedule
    assert not any("T" in str(value) and "Z" in str(value)
                   for value in schedule.values())


def test_remaining_khong_bao_gio_am():
    params = PolicyParams()
    acts, cs = decide(act_view(), ControllerState(), 0.0, params)
    document = build_document(
        cs, params, boot_id="b", seq=1, heartbeat_at="t", decided_at="t",
        now_mono=1e9, dropped=0, provenance={},
    )
    assert document["features"]["schedule"]["properties"]["holdRemainingS"] == 0.0


def test_check_document_bat_loi():
    bad = {"features": {"decision": {"properties": {"mode": "RUNNING"}},
                        "schedule": {"properties": {"holdRemainingS": None,
                                                    "probeRemainingS": -1}},
                        "freshness": {"properties": {"seq": "x"}}}}
    problems = check_document(bad)
    assert any("D1" in p for p in problems)
    assert any("D2" in p for p in problems)
    assert any("D3" in p for p in problems)
    assert any("D4" in p for p in problems)


def test_bootstrap_co_controlloop():
    from bridge.bootstrap import entities_from_spec

    ents = entities_from_spec(ROOT / "ditto/topology_spec.json")
    ids = {item["thing_id"] for item in ents}
    assert CONTROLLOOP_THING_ID in ids
    body = next(i["body"] for i in ents if i["thing_id"] == CONTROLLOOP_THING_ID)
    assert body["features"]["decision"]["properties"]["reason"] == "never_started"


def test_mode_cua_policy_va_hop_dong_khop_nhau():
    """Neu policy them mode moi ma hop dong D khong biet -> phat hien ngay."""
    source = (ROOT / "controller/policy.py").read_text(encoding="utf-8")
    for mode in MODES:
        assert mode in source
