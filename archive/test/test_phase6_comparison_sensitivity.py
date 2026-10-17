import json

import pytest

from scripts import compare_detectors as C
from scripts import eval_phase6_sensitivity as S


def test_contribution_table_distinguishes_zero_from_undefined_jaccard():
    zero = C.contribution_table([1, 1], [1, 0], [0, 1])
    assert zero == {
        'n_positive_ticks': 2, 'both_detect': 0, 'a_only': 1,
        'b_only': 1, 'both_miss': 0, 'jaccard': 0.0,
        'jaccard_note': 'intersection / union'}
    undefined = C.contribution_table([1], [0], [0])
    assert undefined['jaccard'] is None
    assert undefined['both_miss'] == 1


def test_contribution_table_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match='equal length'):
        C.contribution_table([1], [1, 0], [0])


def test_comparison_artifact_is_hashed_and_reproducible():
    document = json.loads(C.OUT.read_text())
    assert document[C.HASH_FIELD] == C.content_hash(document['content'])
    assert document['content'] == C.current_content()


def test_comparison_central_four_cells_and_jaccard():
    content = json.loads(C.OUT.read_text())['content']
    row = content['per_seed']['0']['secondary_excess_vs_iforest'][
        'primary_all_rows']['positive_contribution']
    assert (row['both_detect'], row['a_only'], row['b_only'], row['both_miss']) == (0, 137, 0, 23)
    assert row['jaccard'] == 0.0
    fp = content['per_seed']['0']['secondary_excess_vs_iforest'][
        'primary_all_rows']['negative_alarm_overlap']
    assert fp['b_only'] == 5


def test_literal_hybrid_reading_is_reported_separately():
    content = json.loads(C.OUT.read_text())['content']
    literal = content['per_seed']['0']['literal_primary_k_vs_iforest'][
        'primary_all_rows']
    assert literal['positive_contribution']['jaccard'] is None
    assert literal['positive_contribution']['both_miss'] == 160
    assert literal['negative_alarm_overlap']['b_only'] == 10


def test_comparison_reports_common_denominator_and_all_seeds():
    content = json.loads(C.OUT.read_text())['content']
    assert content['comparison_sets']['secondary_common_judgeable_rows'] == {
        'n_rows': 564, 'n_positive': 152, 'n_negative': 412}
    excess = content['across_seeds']['secondary_excess_vs_iforest']
    assert excess['primary_all_rows']['b_only_per_seed'] == [0, 0, 0, 0, 0]
    assert excess['secondary_common_judgeable_rows']['a_only_per_seed'] == [134, 134, 134, 134, 133]
    literal = content['across_seeds']['literal_primary_k_vs_iforest']
    assert literal['primary_all_rows']['b_only_per_seed'] == [0, 0, 0, 0, 1]


def test_excess_hybrid_delay_is_measured_not_inferred():
    content = json.loads(C.OUT.read_text())['content']
    for seed in range(5):
        delay = content['per_seed'][str(seed)]['secondary_excess_vs_iforest'][
            'hybrid_or_delay']['overall']
        assert delay['median_delay_detected'] == 0.0
        assert delay['n_censored'] == 1


def test_sensitivity_artifact_is_hashed_and_reproducible():
    document = json.loads(S.OUT.read_text())
    assert document[S.HASH_FIELD] == S.content_hash(document['content'])
    assert document['content'] == S.current_content()


def test_sensitivity_mask_counts_and_control_fpr():
    content = json.loads(S.OUT.read_text())['content']
    assert content['mask_counts']['eval_primary'] == {
        'n': 590, 'positive': 160, 'negative': 430}
    assert content['mask_counts']['eval_sensitivity'] == {
        'n': 558, 'positive': 144, 'negative': 414}
    for row in content['envelope'].values():
        assert row['eval_primary']['fpr']['control']['fpr'] == 0.0
        assert row['eval_sensitivity']['fpr']['control']['fpr'] == 0.0


def test_excess_sensitivity_removes_recovery_false_positives():
    row = json.loads(S.OUT.read_text())['content']['envelope']['secondary_excess']
    assert row['mask_effect']['false_positive_alarms_excluded'] == 9
    assert row['eval_sensitivity']['scores']['fp'] == 14
    assert row['eval_sensitivity']['scores']['fpr'] < row['eval_primary']['scores']['fpr']


def test_all_iforest_seeds_still_reproduce_before_mask_sensitivity():
    rows = json.loads(S.OUT.read_text())['content']['iforest']
    assert len(rows) == 5
    assert all(row['reconstruction_check']['tp_fp_bit_exact'] for row in rows.values())


def test_scripts_refuse_overwrite():
    before_c = C.OUT.read_bytes(); before_s = S.OUT.read_bytes()
    assert C.main() == 1 and S.main() == 1
    assert C.OUT.read_bytes() == before_c
    assert S.OUT.read_bytes() == before_s
