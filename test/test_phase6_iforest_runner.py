import json

import numpy as np
import pandas as pd
import pytest

from ml.detectors import iforest as F
from scripts import run_phase6_iforest as R

CONFIGS = ('normal|1', 'normal|2', 'normal|4', 'normal_varying|vary')


def fake_train_base(columns, *, n_ticks=59, seed=11):
    raw = [c for c in F.base_columns(columns) if not c.startswith('agg.')]
    rng = np.random.default_rng(seed); rows = []
    for level, config in enumerate(CONFIGS, 1):
        for run in range(2):
            run_id = 'N-%s-r%d' % (config.replace('|', ''), run)
            for tick in range(n_ticks):
                row = {'run_id': run_id, 'tick': tick, 'config_id': config, 'is_fault': 0}
                for column in raw:
                    scale = 1e5 if 'Rate' in column or 'Delta' in column else 1.
                    row[column] = level * scale + rng.normal(scale=scale * .01)
                rows.append(row)
    frame = pd.DataFrame(rows)
    for link in sorted({c.split('.')[0] for c in raw if c.startswith('link-')}):
        frame[link + '.traffic.lossPct'] = 0.
        frame[link + '.status.state_up'] = 1.
    return frame


def test_verify_ledger_accepts_live_sealed_ledger():
    assert R.verify_ledger()['content']['summary']['pending'] == ['H1', 'H3']


def test_verify_ledger_refuses_a_ledger_that_already_saw_iforest(tmp_path, monkeypatch):
    document = json.loads(R.LEDGER.read_text())
    document['content']['timing_and_knowledge']['iforest_campaign_test_scores_seen'] = True
    document['ledger_content_sha256'] = R._hash(document['content'])
    forged = tmp_path / 'ledger.json'; forged.write_text(json.dumps(document))
    monkeypatch.setattr(R, 'LEDGER', forged)
    with pytest.raises(RuntimeError, match='thu tu bi pha'):
        R.verify_ledger()


def test_verify_ledger_refuses_a_ledger_with_an_iforest_number_filled(tmp_path, monkeypatch):
    document = json.loads(R.LEDGER.read_text())
    document['content']['hypotheses']['H1']['evidence']['iforest_recall_admin_down'] = .9
    document['ledger_content_sha256'] = R._hash(document['content'])
    forged = tmp_path / 'ledger.json'; forged.write_text(json.dumps(document))
    monkeypatch.setattr(R, 'LEDGER', forged)
    with pytest.raises(RuntimeError, match='dien so IF'):
        R.verify_ledger()


def test_frozen_columns_are_72_and_exclude_indicators():
    columns = R.frozen_columns_from_manifest()
    assert len(columns) == 72
    assert not [c for c in columns if any(m in c for m in R.INDICATOR_MARKERS)]


def test_registered_config_matches_prereg():
    assert R.registered_iforest()['n_estimators'] == 300


def test_stage_cv_runs_end_to_end_on_fake_data(tmp_path, monkeypatch):
    columns = R.frozen_columns_from_manifest(); base = fake_train_base(columns)
    out = tmp_path / 'phase6_iforest_cv.json'
    monkeypatch.setattr(R, 'CV_OUT', out)
    monkeypatch.setattr(R, 'load_train_base', lambda: base)
    monkeypatch.setattr(R, 'N_TRAIN_BASE_ROWS', len(base))
    assert R.stage_cv(seeds=(0, 1), quantiles=(.01, .05)) == 0
    document = json.loads(out.read_text()); content = document['content']
    assert document['content_sha256'] == R._hash(content)
    assert len(content['folds']) == 4 and content['n_columns'] == 72
    assert content['is_full_registered_grid'] is False
    assert content['n_train_rows_after_nan_drop'] == len(base) - 8
    assert content['tail_samples_by_q']['0.01'] == round((len(base) - 8) * .01, 2)
    assert R.stage_cv() == 1


def test_stage_cv_rejects_wrong_row_count(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'CV_OUT', tmp_path / 'x.json')
    monkeypatch.setattr(R, 'load_train_base', lambda: pd.DataFrame())
    with pytest.raises(RuntimeError, match='472'):
        R.stage_cv(seeds=(0,), quantiles=(.01,))


def test_stage_test_refuses_reduced_grid_before_loading_test(tmp_path, monkeypatch):
    content = {'is_full_registered_grid': False, 'code_sha256': R.code_fingerprint()}
    path = tmp_path / 'cv.json'
    path.write_text(json.dumps({'content': content, 'content_sha256': R._hash(content)}))
    monkeypatch.setattr(R, 'CV_OUT', path)
    monkeypatch.setattr(R, 'assert_committed_clean', lambda paths: None)
    with pytest.raises(RuntimeError, match='rut gon'):
        R.stage_test()


def test_evaluate_one_preserves_unknown_as_no_alarm():
    train = np.linspace(-1, 0, 100)
    scores = pd.DataFrame({'score': [-2., np.nan], 'judgeable': [True, False]})
    report, alarm = R.evaluate_one(model_scores_train=train, model_scores_test=scores,
        keys=[{'run_id':'C-a','tick':1},{'run_id':'C-a','tick':2}], y=[0,0],
        eval_primary=[True,True], faults={'C-a':None}, q=.01, n_boot=2, rng_seed=1)
    assert alarm.tolist() == [True, False]
    assert report['scores']['n_unknown_negative'] == 1
