"""Pure Isolation Forest detector functions for the registered Phase 6 study."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import GroupKFold

from ml.features import add_aggregate_features, add_delta_features

N_ESTIMATORS = 300
MAX_FEATURES = 1.0
BOOTSTRAP = False
CONTAMINATION = 'auto'
MAX_SAMPLES = (256, 1.0)
PRIMARY_MAX_SAMPLES = 256
SEEDS = (0, 1, 2, 3, 4)
QUANTILES = (0.005, 0.01, 0.02, 0.05)
PRIMARY_Q = 0.01
QUANTILE_METHOD = 'linear'
N_SPLITS = 4
NOISE_RNG_BASE = 10000
HONESTY_RATIO_FLAG = 3.0


def registered_config(prereg_iforest: dict) -> dict:
    expected = {
        'n_estimators': N_ESTIMATORS, 'max_features': MAX_FEATURES,
        'bootstrap': BOOTSTRAP, 'contamination': CONTAMINATION,
        'max_samples': list(MAX_SAMPLES),
        'primary_max_samples': PRIMARY_MAX_SAMPLES,
        'seeds': list(SEEDS),
    }
    missing = [key for key in expected if key not in prereg_iforest]
    if missing:
        raise ValueError('cau hinh IF lech ban dang ky: thieu %s' % missing)
    actual = {key: prereg_iforest[key] for key in expected}
    if actual != expected:
        raise ValueError('cau hinh IF lech ban dang ky: %s' % actual)
    return expected


def frozen_columns(manifest_feature_names) -> list[str]:
    columns = sorted(manifest_feature_names)
    if len(columns) != len(set(columns)):
        raise ValueError('feature_names co cot trung')
    raw = [c for c in columns if not c.startswith('d1.')]
    delta = [c for c in columns if c.startswith('d1.')]
    if sorted('d1.' + c for c in raw) != delta:
        raise ValueError('moi cot tho phai co dung mot cot d1. tuong ung')
    return columns


def base_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if not c.startswith('d1.')]


def matrix(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [c for c in columns if c not in frame]
    if missing:
        raise ValueError('thieu cot IF: %s' % missing[:5])
    return frame[columns].apply(pd.to_numeric, errors='coerce').replace(
        [np.inf, -np.inf], np.nan)


def judgeable_mask(values: pd.DataFrame) -> np.ndarray:
    return values.notna().all(axis=1).to_numpy()


def constant_columns(values: pd.DataFrame) -> list[str]:
    finite = values.dropna(axis=0, how='any')
    return sorted(column for column in values.columns
                  if finite.empty or finite[column].min() == finite[column].max())


def fit(values: pd.DataFrame, *, seed: int, max_samples) -> IsolationForest:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError('seed phai la so nguyen')
    if max_samples not in MAX_SAMPLES:
        raise ValueError('max_samples phai thuoc %s' % (MAX_SAMPLES,))
    if values.isna().to_numpy().any():
        raise ValueError('IF khong nhan NaN: bo dong khong day du TRUOC khi fit')
    if values.empty:
        raise ValueError('khong co dong nao de fit')
    return IsolationForest(
        n_estimators=N_ESTIMATORS, max_samples=max_samples,
        max_features=MAX_FEATURES, bootstrap=BOOTSTRAP,
        contamination=CONTAMINATION, random_state=seed, n_jobs=1,
    ).fit(values)


def score(model: IsolationForest, values: pd.DataFrame) -> pd.DataFrame:
    judgeable = judgeable_mask(values)
    scores = np.full(len(values), np.nan)
    if judgeable.any():
        scores[judgeable] = model.score_samples(values[judgeable])
    return pd.DataFrame({'score': scores, 'judgeable': judgeable}, index=values.index)


def threshold_from_train(train_scores, q: float) -> float:
    if q not in QUANTILES:
        raise ValueError('q phai thuoc %s' % (QUANTILES,))
    finite = np.asarray(train_scores, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError('khong co score train huu han')
    return float(np.quantile(finite, q, method=QUANTILE_METHOD))


def alarm(scores: pd.DataFrame, threshold: float) -> np.ndarray:
    values = scores['score'].to_numpy()
    with np.errstate(invalid='ignore'):
        fired = values < threshold
    return scores['judgeable'].to_numpy() & fired


def effective_tail_samples(n_train_rows: int, q: float) -> float:
    return round(n_train_rows * q, 2)


def _prepare(fit_frame, apply_frame, columns):
    raw = base_columns(columns)
    fit_aggregate, stats = add_aggregate_features(fit_frame, link_stats=None)
    apply_aggregate, _ = add_aggregate_features(apply_frame, link_stats=stats)
    fit_full = add_delta_features(fit_aggregate, raw)
    apply_full = add_delta_features(apply_aggregate, raw)
    return matrix(fit_full, columns), matrix(apply_full, columns)


def fold_splits(base: pd.DataFrame, *, n_splits: int = N_SPLITS):
    for column in ('run_id', 'tick', 'config_id'):
        if column not in base:
            raise ValueError('base thieu cot ' + column)
    if 'is_fault' in base and base['is_fault'].astype(int).any():
        raise ValueError('tap hieu chinh chua dong fault')
    ordered = base.sort_values(['run_id', 'tick']).reset_index(drop=True)
    groups = ordered['config_id'].to_numpy()
    if len(set(groups)) != n_splits:
        raise ValueError('can dung %d config de hieu chinh' % n_splits)
    splitter = GroupKFold(n_splits=n_splits)
    for fold, (fit_index, val_index) in enumerate(splitter.split(ordered, groups=groups)):
        fit_frame, val_frame = ordered.iloc[fit_index], ordered.iloc[val_index]
        held = sorted(set(val_frame['config_id']))
        if len(held) != 1 or held[0] in set(fit_frame['config_id']) or \
                set(fit_frame.run_id) & set(val_frame.run_id):
            raise ValueError('fold khong phai leave-one-config-out')
        yield fold, held[0], fit_frame, val_frame


def _distribution(values) -> dict:
    values = np.asarray(values, dtype=float)
    return {'n': int(values.size), 'min': float(np.min(values)),
            'median': float(np.median(values)), 'mean': float(np.mean(values)),
            'max': float(np.max(values)), 'std': float(np.std(values, ddof=1))}


def heldout_calibration(base: pd.DataFrame, columns: list[str], *,
                        seeds=SEEDS, quantiles=QUANTILES,
                        max_samples=PRIMARY_MAX_SAMPLES,
                        n_splits: int = N_SPLITS) -> dict:
    folds, pooled = [], {q: [] for q in quantiles}
    for fold, held, fit_frame, val_frame in fold_splits(base, n_splits=n_splits):
        fit_values, val_values = _prepare(fit_frame, val_frame, columns)
        fit_ok = fit_values.dropna(axis=0, how='any')
        val_judgeable = judgeable_mask(val_values)
        constants = constant_columns(fit_values)
        if not val_judgeable.any():
            raise ValueError('fold %d khong co dong validation judgeable' % fold)
        record = {
            'fold': fold, 'held_out_config': held,
            'n_fit_rows': len(fit_values), 'n_fit_rows_after_nan_drop': len(fit_ok),
            'n_val_rows': len(val_values),
            'n_val_rows_judgeable': int(val_judgeable.sum()),
            'n_constant_on_fold_fit': len(constants),
            'constant_on_fold_fit': constants, 'per_seed': {},
        }
        for seed in seeds:
            model = fit(fit_ok, seed=seed, max_samples=max_samples)
            train_scores = score(model, fit_ok)['score'].to_numpy()
            val_scores = score(model, val_values)
            entry = {'train_score': _distribution(train_scores),
                     'heldout_score': _distribution(val_scores['score'].dropna()),
                     'alarm_rate_by_q': {}}
            for q in quantiles:
                threshold = threshold_from_train(train_scores, q)
                fired = alarm(val_scores, threshold)
                rate = float(fired.sum() / int(val_judgeable.sum()))
                entry['alarm_rate_by_q'][str(q)] = {
                    'threshold': threshold, 'n_alarm': int(fired.sum()),
                    'alarm_rate': rate, 'ratio_to_q': round(rate / q, 3),
                    'honesty_flag': bool(rate / q > HONESTY_RATIO_FLAG),
                }
                pooled[q].append(rate)
            record['per_seed'][str(seed)] = entry
        folds.append(record)
    summary = {str(q): {
        'mean_alarm_rate': float(np.mean(pooled[q])),
        'max_alarm_rate': float(np.max(pooled[q])),
        'mean_ratio_to_q': round(float(np.mean(pooled[q])) / q, 3),
        'honesty_flag': bool(float(np.mean(pooled[q])) / q > HONESTY_RATIO_FLAG),
    } for q in quantiles}
    return {'folds': folds, 'summary_by_q': summary,
            'measures': 'alarm rate on unseen load levels (out-of-distribution normal)',
            'does_not_measure': 'recall: every validation fold is 100% normal by design',
            'honesty_ratio_flag': HONESTY_RATIO_FLAG}


def split_usage(model: IsolationForest, columns: list[str]) -> dict:
    trees, splits = Counter(), Counter()
    for estimator in model.estimators_:
        used = estimator.tree_.feature
        used = used[used >= 0]
        for index in set(used.tolist()):
            trees[columns[index]] += 1
        for index in used.tolist():
            splits[columns[index]] += 1
    never = sorted(c for c in columns if trees[c] == 0)
    total = sum(splits.values())
    top = sorted(splits.items(), key=lambda item: (-item[1], item[0]))[:10]
    return {'n_trees': len(model.estimators_), 'n_splits_total': total,
            'n_trees_using': {c: trees[c] for c in columns},
            'n_splits': {c: splits[c] for c in columns},
            'columns_never_split': never, 'n_columns_never_split': len(never),
            'top10_by_splits': [{'column': c, 'n_splits': n,
                                 'share': round(n / total, 4) if total else None}
                                for c, n in top],
            'top10_share_of_all_splits': (round(sum(n for _, n in top) / total, 4)
                                          if total else None)}


def noise_control(n_train: int, n_test: int, n_features: int, *, seed: int,
                  q: float = PRIMARY_Q, max_samples=PRIMARY_MAX_SAMPLES) -> dict:
    rng = np.random.default_rng(NOISE_RNG_BASE + seed)
    train = pd.DataFrame(rng.normal(size=(n_train, n_features)))
    test = pd.DataFrame(rng.normal(size=(n_test, n_features)))
    model = fit(train, seed=seed, max_samples=max_samples)
    train_scores = score(model, train)['score'].to_numpy()
    threshold = threshold_from_train(train_scores, q)
    fired = alarm(score(model, test), threshold)
    return {'seed': seed, 'q': q, 'threshold': threshold,
            'n_train': n_train, 'n_test': n_test, 'n_features': n_features,
            'n_alarm': int(fired.sum()), 'alarm_rate': float(fired.mean()),
            'alarm_flags': fired,
            'rng_rule': 'default_rng(%d+seed); draw train then test' % NOISE_RNG_BASE}
