#!/usr/bin/env python3
"""Hai kenh FSM cua lan quet nghiem thu phai la HAI instance doc lap.

`DetectorFSM` giu trang thai debounce trong `self._cs`, `self._ca`, `self._quiet`.
Dung chung mot instance cho hai kenh se tron trang thai cua chung va lam CA HAI
kenh sai theo cach rat kho thay: moi kenh chi thay mot nua so tick cua minh.
Test nay khoa lai truoc khi R-set duoc mo.

Xem `phase6r_acceptance_prereg.channels.fsm_instances_are_independent`.
"""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.serve import Reading

REPORT = C.ROOT / "results/report"
PARAMS = dict(n_suspect=1, n_act=2, release_m=3, cooldown_s=8.0)


def _reading(index, *, envelope=False, cons=False):
    return Reading(
        t_source=float(index),
        tick=index,
        status="scored",
        reason="fixture",
        judgeable=True,
        envelope_suspect=envelope,
        cons_judgeable=True,
        cons_alarm=cons,
        suspect=envelope,
        act=False,
    )


def _states(readings, suspect_of):
    fsm = DetectorFSM(FSMParams(**PARAMS))
    out = []
    for reading in readings:
        derived = Reading(**{**reading.__dict__, "suspect": suspect_of(reading)})
        out.append(fsm.step(derived).state)
    return out


ENVELOPE = lambda r: r.envelope_suspect
COMBINED = lambda r: r.envelope_suspect or r.cons_alarm


def test_two_channels_need_two_instances():
    """Mot instance dung chung cho hai kenh -> ca hai kenh sai."""
    readings = [
        _reading(0),
        _reading(1, envelope=True),
        _reading(2, cons=True),
        _reading(3, cons=True),
        _reading(4),
    ]
    envelope = _states(readings, ENVELOPE)
    combined = _states(readings, COMBINED)

    shared = DetectorFSM(FSMParams(**PARAMS))
    interleaved = []
    for reading in readings:
        for derive in (ENVELOPE, COMBINED):
            derived = Reading(**{**reading.__dict__, "suspect": derive(reading)})
            interleaved.append(shared.step(derived).state)
    shared_envelope = interleaved[0::2]
    shared_combined = interleaved[1::2]

    assert shared_envelope != envelope or shared_combined != combined, (
        "fixture nay khong phan biet duoc instance dung chung; can mot chuoi khac"
    )
    assert envelope != combined, "fixture phai lam hai kenh khac nhau"


def test_channels_are_derived_from_one_reading_stream():
    """Ba kenh phai doc duoc tu CUNG mot Reading, khong can quet lai."""
    reading = _reading(7, envelope=False, cons=True)
    assert reading.envelope_suspect is False
    assert reading.cons_alarm is True
    assert reading.cons_judgeable is True
    assert ENVELOPE(reading) is False
    assert COMBINED(reading) is True
    # kenh residual-only la TICK-LEVEL: khong co FSM, khong co act
    assert (reading.cons_judgeable and reading.cons_alarm) is True


@pytest.mark.skipif(
    not (REPORT / "phase6r_acceptance_prereg.json").exists(),
    reason="prereg nghiem thu chua duoc dung",
)
def test_prereg_channel_contract_matches_this_test():
    document = json.loads(
        (REPORT / "phase6r_acceptance_prereg.json").read_text(encoding="utf-8")
    )
    assert document["content_sha256"] == C.sha256_bytes(
        C.canonical_json(document["content"]).encode()
    )
    channels = document["content"]["channels"]
    assert channels["n_fsm_channels"] == 2
    assert channels["n_tick_level_channels"] == 1
    assert channels["residual_only_has_no_fsm"] is True
    assert channels["conservation_mode_for_the_pass"] == "shadow"
    assert [c["id"] for c in channels["fsm_channels"]] == ["envelope_only", "combined"]
    assert channels["tick_level_channels"][0]["id"] == "residual_only"
    params = document["content"]["frozen_configuration"]["fsm_params"]
    assert params == PARAMS
