import json

import numpy as np
import pandas as pd
import pytest

from ml.campaign import ROOT
from ml.detectors import envelope as E

RATES = ['link-a.traffic.rxRate', 'link-a.traffic.txRate',
         'link-b.traffic.rxRate', 'link-b.traffic.txRate']
LOSS = ['link-a.traffic.lossPct', 'link-b.traffic.lossPct']
STATE = ['link-a.status.state_up', 'link-b.status.state_up']
INDICATOR = sorted(LOSS + STATE + ['agg.loss_max', 'agg.links_down'])
RATE = sorted(RATES + ['agg.rate_absz_max'])
FAMILIES = {'primary': sorted(INDICATOR + RATE), 'indicator': INDICATOR,
            'rate_shared': RATE, 'loss_only': LOSS}


def fake_base(seed=0, n_ticks=20):
    rng = np.random.default_rng(seed)
    levels = {'normal|1': 1e5, 'normal|2': 2e5, 'normal|4': 4e5,
              'normal_varying|vary': None}
    rows = []
    for config, level in levels.items():
        for repeat in (1, 2):
            for tick in range(1, n_ticks + 1):
                schedule = (1e5, 3e5, 2e5, 5e5, 1e5, 4e5)
                current = schedule[min((tick - 1) * 6 // n_ticks, 5)] if level is None else level
                row = {'run_id': f'{config}-r{repeat}', 'tick': tick,
                       'config_id': config, 'is_fault': 0}
                row.update({c: current * (1 + .01 * rng.standard_normal()) for c in RATES})
                row.update({c: 0.0 for c in LOSS})
                row.update({c: 1 for c in STATE})
                rows.append(row)
    return pd.DataFrame(rows)


def test_strict_bounds_floor_and_unknown_policy():
    train = pd.DataFrame({'x.traffic.lossPct': [0., 0.],
                          'y.traffic.rxRate': [1e5, 2e5]})
    bounds = E.fit_bounds(train, list(train))
    scores = E.score(pd.DataFrame({'x.traffic.lossPct': [0., .3, np.nan],
                                   'y.traffic.rxRate': [2e5, 2.5e5, 1e5]}),
                     bounds, list(train))
    assert scores.k.tolist() == [0, 2, 0]
    assert scores.excess.iloc[1] == pytest.approx(3.5)
    assert scores.judgeable.tolist() == [True, True, False]
    assert E.alarm(scores, 0).tolist() == [False, True, False]


def test_dual_rule_is_strict_and_uses_71_column_judgeability():
    indicator = pd.DataFrame({'k': [0, 1, 0, 1]})
    rate = pd.DataFrame({'k': [3, 0, 0, 5]})
    got = E.dual_alarm(indicator, rate, [True, True, True, False], 0, 2)
    assert got.tolist() == [True, True, False, False]


def test_folds_are_leave_one_config_out_and_refit_preprocessing():
    base = fake_base()
    splits = list(E.fold_splits(base))
    assert len(splits) == 4
    assert sorted(item[1] for item in splits) == sorted(base.config_id.unique())
    fit, val = base[base.config_id != 'normal|4'], base[base.config_id == 'normal|4']
    fit_a, _ = E._prepare(fit, val)
    changed = val.copy()
    changed[RATES] *= 1000
    fit_b, _ = E._prepare(fit, changed)
    pd.testing.assert_frame_equal(fit_a, fit_b)


def test_calibration_and_failure_guards():
    report = E.heldout_calibration(fake_base(), FAMILIES)
    assert report['thresholds']['indicator']['K'] == 0
    assert all(v['n_pooled_rows'] == 160 for v in report['thresholds'].values())
    faulty = fake_base()
    faulty.loc[0, 'is_fault'] = 1
    with pytest.raises(ValueError, match='fault'):
        E.heldout_calibration(faulty, FAMILIES)
    unknown = fake_base()
    unknown.loc[unknown.config_id == 'normal|2', LOSS[0]] = np.nan
    with pytest.raises(ValueError, match='no judgeable'):
        E.heldout_calibration(unknown, FAMILIES)


def test_registered_families_and_floors_match_registration():
    amendment = json.loads((ROOT / 'results/report/phase6_prereg_amendment_1.json').read_text())
    manifest = json.loads((ROOT / 'results/report/ml_dataset_split_manifest.json').read_text())
    families = E.registered_families(amendment, manifest)
    assert [len(families[k]) for k in ('primary', 'indicator', 'rate_shared', 'loss_only')] == [71, 35, 36, 8]
    prereg = json.loads((ROOT / 'results/report/phase6_prereg.json').read_text())['content']
    floors = prereg['decision_rules']['envelope']['floors']
    assert E.floor_for('link-x.traffic.rxRate') == floors['rxRate']
    assert E.floor_for('link-x.status.state_up') == floors['state_up']
    assert E.floor_for('agg.loss_max') == floors['all_other_registered_columns']


@pytest.mark.skipif(not any((ROOT / 'data/phase5/raw').glob('*.jsonl')),
                    reason='raw campaign is unavailable')
def test_train_only_cv_path_reproduces_registered_full_train_bounds():
    """Check the independent CV preprocessing path without opening test rows."""
    from scripts.run_phase6_envelope import (families_from_registration,
                                              load_train_base)

    manifest = json.loads((ROOT / 'results/report/ml_dataset_split_manifest.json').read_text())
    families = families_from_registration()
    base = load_train_base()
    train_aggregate, _ = E._prepare(base, base.iloc[:0])
    got = E.fit_bounds(train_aggregate, families['primary'])
    expected = {column: {'min': values['min'], 'max': values['max']}
                for column, values in manifest['envelope'].items()}
    assert got == expected
