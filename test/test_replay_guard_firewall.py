"""The amendment-6 firewall is tested only with synthetic fixtures."""
import json

import pytest

from ml import campaign as C
from ml.replay_guard import R_O1_FIELDS, R_O2_FIELDS, _sealed, replay_gap, replay_restart


@pytest.fixture(scope="module")
def contract():
    path = C.ROOT / "results/report/phase6r_amendment_6.json"
    return json.loads(path.read_text())["content"]["public_output_contract"]


def test_fields_match_sealed_contract_exactly(contract):
    assert list(R_O1_FIELDS) == contract["R_O1_restart_S9_boolean_fields_only"]
    assert list(R_O2_FIELDS) == contract["R_O2_gap_S8_boolean_fields_only"]


def test_extra_key_is_rejected():
    with pytest.raises(ValueError, match="tuong lua"):
        _sealed({**dict.fromkeys(R_O1_FIELDS, True), "n_alarms": 3}, R_O1_FIELDS)


def test_counts_are_rejected_even_under_a_contract_name():
    bad = dict.fromkeys(R_O1_FIELDS, True)
    bad["no_act_before_n_scored"] = 0
    with pytest.raises(ValueError, match="bool"):
        _sealed(bad, R_O1_FIELDS)


def test_missing_key_is_rejected():
    with pytest.raises(ValueError, match="thieu truong"):
        _sealed({"passed": True}, R_O1_FIELDS)


def test_restart_detects_a_broken_fsm():
    class BadFSM:
        def step(self, reading):
            return type("Transition", (), {"state": "normal", "cause": None})()

    class NullScorer:
        def observe(self, snapshot):
            return type("Reading", (), {"judgeable": True})()

    output = replay_restart(NullScorer, BadFSM, [{}] * 10, [0], n_act=2)
    assert output["first_after_restart_is_warming_up"] is False
    assert output["no_normal_before_scored"] is False
    assert output["passed"] is False
    assert set(output) == set(R_O1_FIELDS)


def test_gap_detects_a_broken_fsm():
    class Reading:
        judgeable = False

    class BadScorer:
        def observe(self, snapshot):
            return Reading()

    class BadFSM:
        def step(self, reading):
            return type("Transition", (), {"state": "normal", "cause": None})()

    output = replay_gap(BadScorer, BadFSM, [{}] * 10, [2], gap_len=2)
    assert output["first_after_gap_is_unknown_gap"] is False
    assert output["no_unjudgeable_tick_is_normal"] is False
    assert output["passed"] is False
    assert set(output) == set(R_O2_FIELDS)
