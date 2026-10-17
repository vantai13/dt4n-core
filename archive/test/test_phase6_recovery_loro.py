import json

from scripts import diag_phase6_envelope_loro as L
from scripts import diag_phase6_recovery as R


def test_recovery_artifact_hash_and_values():
    doc = json.loads(R.OUT.read_text())
    assert doc[R.HASH_FIELD] == R.content_hash(doc['content'])
    assert doc['content'] == R.current_content()
    content = doc['content']
    assert content['maximum_observed_recovery_span_ticks'] == 7
    assert content['recommended_phase8_cooldown_ticks'] == 8
    assert content['by_fault']['admin_down']['max_span_ticks'] <= 2
    assert content['by_fault']['degrade']['max_span_ticks'] <= 2
    assert content['by_fault']['flood']['max_span_ticks'] == 7


def test_loro_artifact_hash_and_has_two_vary_replicates():
    doc = json.loads(L.OUT.read_text())
    assert doc[L.HASH_FIELD] == L.content_hash(doc['content'])
    assert doc['content'] == L.current_content()
    summary = doc['content']['primary_summary']
    assert len(doc['content']['folds']) == 8
    assert summary['n_vary_replicates'] == 2
    assert len(summary['vary_run_excess_max_values']) == 2


def test_diagnostics_refuse_overwrite():
    before_r = R.OUT.read_bytes(); before_l = L.OUT.read_bytes()
    assert R.main() == 1 and L.main() == 1
    assert R.OUT.read_bytes() == before_r
    assert L.OUT.read_bytes() == before_l
