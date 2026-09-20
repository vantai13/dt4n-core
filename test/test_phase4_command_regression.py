"""Hoi quy Phase 4: them tham so `cid` vao send_command KHONG duoc doi hanh vi cu.

Caller cu goi send_command(cmd) -> van sinh uuid ngau nhien nhu truoc.
Caller moi (controller Phase 8) ghim cid = intervention_id de dedup cua
command_agent khop voi chuoi nhan qua trong audit.
"""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    status_code = 202
    text = ""

    def json(self):
        return {}


def make_env(monkeypatch, captured):
    """Dung EnvRunner.send_command nhu mot ham roi, khong dung Mininet."""
    import requests

    from mininet import env_runner as module

    def fake_post(url, json=None, headers=None, auth=None, timeout=None):
        captured.append({"url": url, "body": json, "headers": headers})
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    env = object.__new__(module.EnvRunner)
    return env, module


def send(env, module, cmd, **kwargs):
    return module.EnvRunner.send_command(env, cmd, **kwargs)


CMD = {"subject": "setBandwidth", "target": "org.dt4n:link-h1-s1",
       "params": {"bw": 7.0}}


def test_khong_truyen_cid_van_sinh_uuid_moi(monkeypatch):
    captured = []
    env, module = make_env(monkeypatch, captured)
    first = send(env, module, CMD)
    second = send(env, module, CMD)
    assert first["cid"] != second["cid"]              # hanh vi Phase 4 giu nguyen
    assert len(first["cid"]) == 36                    # van la uuid4
    assert first["http_status"] == 202


def test_cid_tuong_minh_duoc_ton_trong(monkeypatch):
    captured = []
    env, module = make_env(monkeypatch, captured)
    result = send(env, module, CMD, cid="ctl-b3f-e1-k0:inject")
    assert result["cid"] == "ctl-b3f-e1-k0:inject"
    assert captured[-1]["headers"]["correlation-id"] == "ctl-b3f-e1-k0:inject"
    assert captured[-1]["body"]["clientCorrelationId"] == "ctl-b3f-e1-k0:inject"


def test_cid_trong_cmd_cung_duoc_ton_trong(monkeypatch):
    """to_command() tra dict co san 'cid' -> send_command dung luon."""
    from controller.intervene import to_command
    from controller.policy import ControllerState, DetectorView, PolicyParams, decide

    captured = []
    env, module = make_env(monkeypatch, captured)
    view = DetectorView("act", "", ("org.dt4n:host-h1",),
                        (("h1", "client"),), True, "b3f", 1)
    actions, _ = decide(view, ControllerState(), 0.0, PolicyParams())
    command = to_command(actions[0])
    result = send(env, module, command)
    assert result["cid"] == actions[0].intervention_id
    assert "cid" not in result["params"]              # cid khong lot vao params
    assert captured[-1]["body"]["bw"] == 7.0


def test_gui_lai_lenh_dung_cid_cu_thi_agent_tra_ket_qua_cu(monkeypatch):
    """Dedup cua command_agent: reconcile gui lai -> KHONG cham Mininet."""
    import bridge.command_agent as agent

    monkeypatch.setattr(agent, "_processed_ids", agent.OrderedDict())
    cid = "ctl-b3f-e1-k0:inject"
    assert agent.processed_result(cid) is None
    agent.remember_processed(cid, (True, 200, "link bw -> 7.0 Mbps"))
    again = agent.processed_result(cid)
    assert again is not None
    assert again == (True, 200, "link bw -> 7.0 Mbps")
