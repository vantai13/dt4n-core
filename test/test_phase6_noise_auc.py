import json

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from scripts import diag_phase6_noise_auc as N


def test_auc_lower_is_anomalous_has_correct_direction_and_ties():
    assert N.auc_lower_is_anomalous([0.0, 1.0], [1, 0]) == 1.0
    assert N.auc_lower_is_anomalous([1.0, 0.0], [1, 0]) == 0.0
    assert N.auc_lower_is_anomalous([0.0, 0.0], [1, 0]) == 0.5


def test_auc_lower_matches_sklearn_on_negated_scores():
    scores = np.array([0.2, -0.4, 0.2, -0.1, 0.7, -0.4])
    labels = np.array([0, 1, 1, 0, 0, 1])
    assert N.auc_lower_is_anomalous(scores, labels) == pytest.approx(
        roc_auc_score(labels, -scores))


def test_auc_rejects_bad_input_and_undefined_class():
    with pytest.raises(ValueError, match='equal-length'):
        N.auc_lower_is_anomalous([0.0], [0, 1])
    with pytest.raises(ValueError, match='finite'):
        N.auc_lower_is_anomalous([0.0, np.nan], [0, 1])
    assert N.auc_lower_is_anomalous([0.0, 1.0], [1, 1]) is None


def test_live_noise_auc_artifact_hash_and_drift():
    document = json.loads(N.OUT.read_text())
    assert document[N.HASH_FIELD] == N.content_hash(document['content'])
    assert document['content'] == N.current_content()


def test_mean_noise_auc_passes_sanity_range_and_reproduces_signed_arm():
    content = json.loads(N.OUT.read_text())['content']
    assert content['summary'][
        'noise_auc_mean_in_predeclared_sanity_range_0_45_0_55'] is True
    assert content['summary']['all_five_noise_arms_reproduced_exactly'] is True
    assert len(content['per_seed']) == 5
    for row in content['per_seed'].values():
        assert all(row['reproduction_check'][key] for key in (
            'threshold_bit_exact', 'raw_n_alarm_exact', 'masked_tp_fp_exact'))
    assert content['summary']['n_individual_seeds_in_0_45_0_55'] == 3


def test_real_auc_matches_existing_phase6_diagnostic():
    content = json.loads(N.OUT.read_text())['content']
    prior = json.loads((N.REPORT / 'phase6_iforest_posthoc_diag.json').read_text())
    expected = prior['content']['common_comparison']['statistics'][
        'iforest_neg_score']['auc']
    assert content['summary']['auc_real_seed0'] == pytest.approx(expected)
    assert content['summary']['auc_real_seed0'] > 0.8


def test_script_refuses_overwrite():
    before = N.OUT.read_bytes()
    assert N.main() == 1
    assert N.OUT.read_bytes() == before
