import json

from ml import campaign as C
from ml.fsm import FSMParams


SLO = C.ROOT / "results/report/phase6r_slo.json"
AMEND2 = C.ROOT / "results/report/phase6r_amendment_2.json"


def _slo(slo_id):
    for item in json.loads(SLO.read_text())["content"]["slo"]:
        if item["id"] == slo_id:
            return item
    raise AssertionError("khong co " + slo_id)


def test_fsm_params_respect_sealed_debounce_ceiling():
    ceiling = _slo("S4b")["target"]["value"]
    params = FSMParams(**json.loads(AMEND2.read_text())["content"]["fsm"]["params"])
    assert params.n_suspect <= ceiling
    assert params.n_act <= ceiling


def test_ceiling_derivation_is_arithmetically_true():
    budget_ms = _slo("S4")["target"]["value"]
    latency_ms = _slo("S5")["target"]["value"]

    def detection_ms(n, onset=1):
        return (onset + n - 1) * 1000 + latency_ms

    assert detection_ms(2) <= budget_ms < detection_ms(3)
