import json

import numpy as np
import pandas as pd
import pytest

from ml.detectors import iforest as F


def frame(rows=120, cols=4, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(size=(rows, cols)),
                        columns=[f'x{i}' for i in range(cols)])


def test_registered_config_matches_constants():
    config = {'n_estimators': 300, 'max_features': 1.0, 'bootstrap': False,
              'contamination': 'auto', 'max_samples': [256, 1.0],
              'primary_max_samples': 256, 'seeds': [0, 1, 2, 3, 4]}
    assert F.registered_config(config) == config


def test_registered_config_rejects_drift():
    with pytest.raises(ValueError, match='lech'):
        F.registered_config({'n_estimators': 1})


def test_frozen_columns_requires_raw_delta_pairs():
    assert F.frozen_columns(['d1.b', 'b', 'a', 'd1.a']) == ['a', 'b', 'd1.a', 'd1.b']


def test_frozen_columns_rejects_duplicate():
    with pytest.raises(ValueError, match='trung'):
        F.frozen_columns(['x', 'x', 'd1.x'])


def test_frozen_columns_rejects_unpaired_delta():
    with pytest.raises(ValueError, match='d1'):
        F.frozen_columns(['x', 'd1.y'])


def test_matrix_coerces_nonfinite_and_rejects_missing():
    got = F.matrix(pd.DataFrame({'x': ['1', np.inf]}), ['x'])
    assert got.iloc[0, 0] == 1 and np.isnan(got.iloc[1, 0])
    with pytest.raises(ValueError, match='thieu'):
        F.matrix(got, ['y'])


def test_judgeable_requires_every_column():
    assert F.judgeable_mask(pd.DataFrame({'a': [1, np.nan], 'b': [2, 3]})).tolist() == [True, False]


def test_constant_columns_detects_only_constants():
    assert F.constant_columns(pd.DataFrame({'a': [1, 1], 'b': [1, 2]})) == ['a']


def test_fit_requires_keyword_arguments():
    with pytest.raises(TypeError):
        F.fit(frame(), 0, 256)


def test_fit_rejects_nan():
    values = frame(); values.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match='NaN'):
        F.fit(values, seed=0, max_samples=256)


def test_fit_rejects_unregistered_max_samples():
    with pytest.raises(ValueError, match='max_samples'):
        F.fit(frame(), seed=0, max_samples=100)


def test_contamination_is_auto_and_never_a_base_rate():
    model = F.fit(frame(300), seed=0, max_samples=256)
    assert model.contamination == 'auto'


def test_score_sign_convention_lower_is_more_anomalous():
    train = frame(300)
    model = F.fit(train, seed=0, max_samples=256)
    normal = F.score(model, train)['score'].median()
    anomaly = F.score(model, pd.DataFrame([[20] * 4], columns=train.columns))['score'].iloc[0]
    assert anomaly < normal


def test_unknown_row_scores_nan_and_never_alarms():
    train = frame(300); model = F.fit(train, seed=0, max_samples=256)
    test = train.iloc[:2].copy(); test.iloc[0, 0] = np.nan
    scores = F.score(model, test)
    assert np.isnan(scores.score.iloc[0]) and not F.alarm(scores, 0.0)[0]


def test_alarm_is_strict_so_equality_does_not_fire():
    scores = pd.DataFrame({'score': [-2., -1.], 'judgeable': [True, True]})
    assert F.alarm(scores, -1.).tolist() == [True, False]


def test_threshold_comes_from_train_quantile_only():
    scores = np.arange(100, dtype=float)
    assert F.threshold_from_train(scores, .01) == pytest.approx(np.quantile(scores, .01))
    with pytest.raises(ValueError, match='q phai thuoc'):
        F.threshold_from_train(scores, .2712)


def test_threshold_rejects_no_finite_scores():
    with pytest.raises(ValueError, match='huu han'):
        F.threshold_from_train([np.nan], .01)


def test_effective_tail_samples():
    assert F.effective_tail_samples(464, .005) == 2.32


def test_same_seed_reproduces_and_different_seeds_do_not():
    values = frame(300)
    a = F.score(F.fit(values, seed=0, max_samples=256), values).score
    b = F.score(F.fit(values, seed=0, max_samples=256), values).score
    c = F.score(F.fit(values, seed=1, max_samples=256), values).score
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def test_train_quantile_alarm_rate_matches_q_on_train_itself():
    values = frame(500)
    scores = F.score(F.fit(values, seed=0, max_samples=256), values)
    threshold = F.threshold_from_train(scores.score, .05)
    assert F.alarm(scores, threshold).mean() == pytest.approx(.05, abs=.01)


def test_constant_column_is_never_split_and_score_ignores_it():
    values = frame(300); values['constant'] = 7
    model = F.fit(values, seed=0, max_samples=256)
    usage = F.split_usage(model, list(values))
    assert 'constant' in usage['columns_never_split']


def test_same_column_with_tiny_noise_becomes_usable():
    values = frame(300); values['tiny'] = np.linspace(0, 1e-3, len(values))
    usage = F.split_usage(F.fit(values, seed=0, max_samples=256), list(values))
    assert usage['n_trees_using']['tiny'] > 0


def test_noise_control_is_deterministic_and_near_registered_q():
    a = F.noise_control(464, 590, 72, seed=0)
    b = F.noise_control(464, 590, 72, seed=0)
    assert a['n_alarm'] == b['n_alarm']
    assert 0 <= a['alarm_rate'] < .1


def test_train_matrix_drops_one_delta_row_per_run():
    columns = ['x', 'd1.x']
    base = pd.DataFrame({'run_id': ['a'] * 3 + ['b'] * 3, 'tick': [1,2,3] * 2,
                         'config_id': ['c'] * 6, 'x': range(6)})
    values, labels = F.train_matrix(base, columns)
    assert len(values) == len(labels) == 4


def test_final_thresholds_freezes_every_requested_cell():
    values = frame(300)
    out = F.final_thresholds(values, seeds=(0, 1), quantiles=(.01,),
                             max_samples_list=(256,))
    assert set(out['256']) == {'0', '1'}
    assert set(out['256']['0']['threshold_by_q']) == {'0.01'}


def test_tail_ownership_identifies_config_in_lower_tail():
    values = frame(300)
    labels = pd.DataFrame({'run_id': ['r'] * 300, 'tick': range(300),
                           'config_id': ['normal'] * 150 + ['vary'] * 150})
    result = F.tail_ownership(values, labels, seed=0, q=.01)
    assert result['n_below_threshold'] > 0
    assert result['tail_dominated_by'] in {'normal', 'vary'}
    json.dumps(result)


def test_dynamics_profile_measures_varying_delta_extrapolation():
    values = pd.DataFrame({'x': [1.] * 8, 'd1.x': [.1] * 4 + [10.] * 4})
    labels = pd.DataFrame({'run_id':['r']*8, 'tick':range(8),
                           'config_id':['normal|1']*4 + ['normal_varying|vary']*4})
    result = F.dynamics_profile(values, labels)
    assert result['dynamics_extrapolation_factor'] == 100.


def test_final_threshold_matches_direct_recalculation():
    values = frame(300)
    frozen = F.final_thresholds(values, seeds=(0,), quantiles=(.01,),
                                max_samples_list=(256,))['256']['0']
    model = F.fit(values, seed=0, max_samples=256)
    direct = F.threshold_from_train(F.score(model, values).score, .01)
    assert frozen['threshold_by_q']['0.01'] == direct
