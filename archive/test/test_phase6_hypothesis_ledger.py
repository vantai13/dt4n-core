import json

import pytest

from scripts import build_phase6_hypothesis_ledger as L
from scripts import diag_phase6_envelope_posthoc as D

IFOREST_FIELDS = ('iforest_recall_admin_down', 'iforest_per_seed_delay',
                  'iforest_only_ticks_per_seed', 'iforest_alarm_rate_by_fold',
                  'iforest_fpr_C_vary', 'iforest_fpr_C_load2M')


def ledger():
    return json.loads(L.OUT.read_text(encoding='utf-8'))


def diag():
    return json.loads(D.OUT.read_text(encoding='utf-8'))


def test_ledger_written_before_any_iforest_number_exists():
    timing = ledger()['content']['timing_and_knowledge']
    assert timing['iforest_fitted_on_campaign_train'] is False
    assert timing['iforest_campaign_test_scores_seen'] is False
    assert timing['envelope_campaign_test_scores_seen'] is True


def test_no_evidence_field_carries_an_iforest_number():
    for row in ledger()['content']['hypotheses'].values():
        for field in IFOREST_FIELDS:
            if field in row['evidence']:
                assert row['evidence'][field] is None


def test_h2_refuted_by_censoring_while_loss_only_clause_held():
    row = ledger()['content']['hypotheses']['H2']
    lo, hi = L.LOSS_ONLY_DELAY_RANGE
    assert row['status'] == 'refuted'
    assert row['evidence']['envelope_primary_delay'] is None
    assert row['evidence']['envelope_primary_censored'] is True
    assert lo <= row['evidence']['loss_only_delay'] <= hi
    assert row['evidence']['clause_loss_only_in_range_holds'] is True


def test_h4_refuted_because_low_load_fold_alarms_more_often_than_vary():
    evidence = ledger()['content']['hypotheses']['H4']['evidence']
    assert evidence['highest_other_fold'] == 'normal|1'
    assert evidence['highest_other_share'] > evidence['vary_fold_share']
    assert evidence['strictly_higher_than_vary'] is True


def test_h5_refuted_because_both_control_runs_gave_zero_fpr():
    evidence = ledger()['content']['hypotheses']['H5']['evidence']
    assert evidence['envelope_primary_fpr_C_vary'] == 0.0
    assert evidence['envelope_primary_fpr_C_load2M'] == 0.0
    assert evidence['envelope_clause_refutes'] is True


def test_h3_records_the_trivial_confirmation_warning():
    row = ledger()['content']['hypotheses']['H3']
    assert row['evidence']['envelope_primary_tp'] == 0
    assert row['evidence']['envelope_primary_recall'] == 0.0
    assert 'TRIVIAL CONFIRMATION' in row['note']


def test_h1_note_separates_threshold_failure_from_channel_argument():
    note = ledger()['content']['hypotheses']['H1']['note']
    assert 'NGUONG K' in note and 'khong phai ve kenh' in note


def test_diag_declares_itself_exploratory_and_label_using():
    content = diag()['content']
    assert content['status'].startswith('EXPLORATORY')
    assert content['uses_test_labels'] is True
    assert set(content['authorises_no_change_to']) == {
        'detector', 'threshold', 'hypothesis', 'column set'}


def test_diag_shows_registered_K_is_structurally_unreachable():
    reach = diag()['content']['structural_reachability']
    assert reach['registered_K'] > reach['generous_upper_bound_single_link_fault']
    assert reach['K_reachable_by_single_link_fault'] is False


def test_diag_shows_count_statistic_has_signal_but_no_separating_threshold():
    separation = diag()['content']['separability']
    assert separation['auc_k'] > 0.85
    assert separation['k_negative_max'] >= separation['k_positive_max']
    assert separation['auc_excess'] > separation['auc_k']


def test_diag_quantile_alternative_would_not_have_rescued_the_rule():
    content = diag()['content']
    alternatives = content['quantile_alternatives']
    assert alternatives['registered_rule'] == 'K = max held-out k'
    bound = content['structural_reachability']['generous_upper_bound_single_link_fault']
    assert alternatives['alternative_K_by_quantile']['0.975'] > bound


def test_ledger_hash_and_no_drift():
    document = ledger()
    assert document[L.HASH_FIELD] == L.content_hash(document['content'])
    assert document['content'] == L.current_content()


def test_sealed_sources_rejects_a_tampered_artifact(monkeypatch):
    original = L._read

    def tampered(path):
        document = original(path)
        if path == L.TEST:
            document['content'] = dict(document['content'], lesson='tampered')
        return document

    monkeypatch.setattr(L, '_read', tampered)
    with pytest.raises(ValueError, match='bi sua'):
        L.sealed_sources()


def test_ledger_bound_to_live_artifact_hashes():
    sources = L.sealed_sources()
    bound = ledger()['content']['bound_to']
    assert bound == {
        'prereg_content_sha256': sources['prereg']['prereg_content_sha256'],
        'amendment_1_content_sha256': sources['amendment_1']['amendment_content_sha256'],
        'amendment_2_content_sha256': sources['amendment_2']['amendment_content_sha256'],
        'envelope_cv_content_sha256': sources['cv']['content_sha256'],
        'envelope_test_content_sha256': sources['test']['content_sha256'],
    }


def test_ledger_refuses_overwrite():
    before = L.OUT.read_bytes()
    assert L.main() == 1
    assert L.OUT.read_bytes() == before


def test_ledger_claims_copied_verbatim_from_prereg():
    registered = {row['id']: row for row in
                  L.sealed_sources()['prereg']['content']['hypotheses']}
    for name, row in ledger()['content']['hypotheses'].items():
        assert row['registered_claim'] == registered[name]['claim']
        assert row['registered_refutation'] == registered[name]['refuted_if']


def test_summary_partitions_exactly_and_matches_decided_by():
    content = ledger()['content']
    assert content['summary'] == {'refuted': ['H2', 'H4', 'H5'],
                                  'pending': ['H1', 'H3']}
    for name, row in content['hypotheses'].items():
        expected = 'envelope_evidence_only' if name in content['summary']['refuted'] else 'requires_iforest'
        assert row['decided_by'] == expected


def test_diag_hash_and_no_drift():
    document = diag()
    assert document[D.HASH_FIELD] == D.content_hash(document['content'])
    assert document['content'] == D.current_content()


def test_diag_refuses_overwrite():
    before = D.OUT.read_bytes()
    assert D.main() == 1
    assert D.OUT.read_bytes() == before
