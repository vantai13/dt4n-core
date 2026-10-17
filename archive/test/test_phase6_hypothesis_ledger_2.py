import json

import pytest

from scripts import build_phase6_hypothesis_ledger_2 as L2


def ledger2(): return json.loads(L2.OUT.read_text())


def test_hash_and_drift():
    doc=ledger2(); assert doc[L2.HASH_FIELD]==L2.content_hash(doc['content'])
    assert doc['content']==L2.current_content()


def test_timing_is_after_cv_before_test():
    timing=ledger2()['content']['timing_and_knowledge']
    assert timing['iforest_fitted_on_campaign_train'] is True
    assert timing['iforest_campaign_test_scores_seen'] is False


def test_h4_iforest_clause_supported():
    row=ledger2()['content']['h4_clause_analysis']
    assert row['iforest_clause']=='supported'
    assert row['iforest_evidence']['clause_holds'] is True


def test_h4_holds_for_every_seed():
    assert ledger2()['content']['h4_clause_analysis']['iforest_evidence']['holds_for_every_seed'] is True


def test_h4_overall_status_is_not_reopened_by_iforest_evidence():
    analysis=ledger2()['content']['h4_clause_analysis']; one=json.loads(L2.LEDGER_1.read_text())
    assert analysis['overall_status_unchanged']==one['content']['hypotheses']['H4']['status']=='refuted'
    assert 'EITHER detector' in analysis['why_unchanged']


def test_predictions_separate_direction_from_magnitude():
    predictions=ledger2()['content']['predictions_recorded_before_test']
    assert 'direction, not a magnitude' in predictions['fpr_direction']
    warning=predictions['fpr_magnitude_warning']
    assert 'counterfactual' in warning and 'all four configs' in warning and 'Phase 7' in warning


def test_prediction_records_no_tuning():
    assert 'remain registered' in ledger2()['content']['predictions_recorded_before_test']['no_tuning']


def test_threshold_ownership_is_generated_from_cv():
    src=L2.sealed_sources(); owner=src['cv']['content']['tail_ownership']['0']['tail_dominated_by']
    assert owner in ledger2()['content']['predictions_recorded_before_test']['threshold_ownership']


def test_dynamics_prediction_contains_measured_factor():
    src=L2.sealed_sources(); factor=str(src['cv']['content']['dynamics_profile']['dynamics_extrapolation_factor'])
    assert factor in ledger2()['content']['predictions_recorded_before_test']['dynamics_not_only_level']


def test_ledger2_bound_to_live_sources():
    src=L2.sealed_sources(); bound=ledger2()['content']['bound_to']
    assert bound['iforest_cv_content_sha256']==src['cv']['content_sha256']


def test_refuses_reduced_grid(monkeypatch):
    original=L2._read
    def forged(path):
        doc=original(path)
        if path==L2.CV:
            doc['content']['is_full_registered_grid']=False
            doc['content_sha256']=L2.content_hash(doc['content'])
        return doc
    monkeypatch.setattr(L2,'_read',forged)
    with pytest.raises(ValueError,match='rut gon'): L2.sealed_sources()


def test_refuses_wrong_ledger_reference(monkeypatch):
    original=L2._read
    def forged(path):
        doc=original(path)
        if path==L2.CV:
            doc['content']['ledger_content_sha256']='0'*64
            doc['content_sha256']=L2.content_hash(doc['content'])
        return doc
    monkeypatch.setattr(L2,'_read',forged)
    with pytest.raises(ValueError,match='khong tro'): L2.sealed_sources()


def test_refuses_overwrite():
    before=L2.OUT.read_bytes(); assert L2.main()==1; assert L2.OUT.read_bytes()==before
