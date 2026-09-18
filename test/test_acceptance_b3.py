"""B.3: cong phan quyet va projection duoc test khong can R-set."""
from __future__ import annotations

import json

from ml import campaign as C
from ml.acceptance_gates import FIT_FIELDS, dose_fit, gate_g1, gate_g2, gate_g4
from ml.acceptance_stats import DosePoint


def test_gate_g1_is_false_on_empty_evidence():
    assert gate_g1({"with_log": {}, "no_log": {}}, []) is False


def test_gate_g1_is_false_when_a_cell_is_none():
    block = {
        mode: {"envelope_only": {"R1": {"pass": None}}}
        for mode in ("with_log", "no_log")
    }
    assert gate_g1(block, ["R1"]) is False


def test_gate_g2_counts_events_not_ticks():
    block = {"detour": {"R1": {"act_fp_ticks": 5, "act_fp_events": 0}}}
    assert gate_g2(block) is True
    block["detour"]["R1"]["act_fp_events"] = 1
    assert gate_g2(block) is False


def test_dose_fit_projects_to_exactly_the_skeleton_fields():
    points = [
        DosePoint("a", 1.0, False),
        DosePoint("b", 10.0, False),
        DosePoint("c", 100.0, True),
        DosePoint("d", 500.0, True),
    ]
    assert set(dose_fit(points)) == set(FIT_FIELDS)


def test_dose_fit_on_empty_is_all_null():
    assert dose_fit([]) == {field: None for field in FIT_FIELDS}


def test_gate_g4_is_false_while_s12_is_pending():
    report = C.ROOT / "results/report"
    replay_o1 = json.loads((report / "phase6r_replay_o1.json").read_text())["content"]
    replay_o2 = json.loads((report / "phase6r_replay_o2.json").read_text())["content"]
    stability = json.loads((report / "phase6r_stability_v2.json").read_text())[
        "content"
    ]
    assert stability["release_gates"]["G4_S12"].startswith("PENDING")
    assert gate_g4(replay_o1, replay_o2, stability) is False
