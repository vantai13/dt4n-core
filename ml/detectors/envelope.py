"""Envelope detector with held-out, train-only threshold calibration."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from ml.features import add_aggregate_features

N_SPLITS = 4
FLOORS = {'.traffic.rxRate': 1.0e4, '.traffic.txRate': 1.0e4,
          '.traffic.lossPct': 0.1, '.status.state_up': 0.01}
OTHER_FLOOR = 1.0


def registered_families(amendment: dict, manifest: dict) -> dict:
    secondary = amendment['content']['secondary_detector']
    indicator = list(secondary['indicator_columns'])
    rate = list(secondary['rate_shared_columns'])
    primary = sorted(indicator + rate)
    if primary != sorted(manifest['envelope_feature_names']) or set(indicator) & set(rate):
        raise ValueError('registered column families disagree with manifest')
    loss = sorted(c for c in indicator
                  if c.startswith('link-') and c.endswith('.traffic.lossPct'))
    if len(loss) != 8:
        raise ValueError('loss_only must contain eight raw link lossPct columns')
    return {'primary': primary, 'indicator': sorted(indicator),
            'rate_shared': sorted(rate), 'loss_only': loss}


def floor_for(column: str) -> float:
    return next((value for suffix, value in FLOORS.items()
                 if column.endswith(suffix)), OTHER_FLOOR)


def numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [c for c in columns if c not in frame]
    if missing:
        raise ValueError('missing envelope columns: %s' % missing[:5])
    return frame[columns].apply(pd.to_numeric, errors='coerce').replace(
        [np.inf, -np.inf], np.nan)


def fit_bounds(train: pd.DataFrame, columns: list[str]) -> dict:
    values = numeric(train, columns)
    bounds = {}
    for column in columns:
        finite = values[column].dropna()
        if finite.empty:
            raise ValueError('no finite fit value for column: ' + column)
        bounds[column] = {'min': float(finite.min()), 'max': float(finite.max())}
    return bounds


def score(frame: pd.DataFrame, bounds: dict, columns: list[str]) -> pd.DataFrame:
    values = numeric(frame, columns).to_numpy(dtype=float)
    lo = np.array([bounds[c]['min'] for c in columns])
    hi = np.array([bounds[c]['max'] for c in columns])
    scale = np.maximum(hi - lo, [floor_for(c) for c in columns])
    with np.errstate(invalid='ignore'):
        violations = (values < lo) | (values > hi)
        amount = np.maximum.reduce(
            [lo - values, values - hi, np.zeros_like(values)]) / scale
    return pd.DataFrame({
        'k': violations.sum(axis=1).astype('int32'),
        'excess': np.nansum(amount, axis=1),
        'judgeable': np.isfinite(values).all(axis=1),
    }, index=frame.index)


def alarm(scores: pd.DataFrame, threshold: float, key: str = 'k') -> np.ndarray:
    return (scores['judgeable'] & (scores[key] > threshold)).to_numpy()


def dual_alarm(indicator: pd.DataFrame, rate: pd.DataFrame, judgeable71,
               threshold_indicator: int, threshold_rate: int) -> np.ndarray:
    judgeable = np.asarray(judgeable71, dtype=bool)
    return judgeable & ((indicator['k'].to_numpy() > threshold_indicator) |
                        (rate['k'].to_numpy() > threshold_rate))


def _prepare(fit_frame, apply_frame):
    fit_aggregate, stats = add_aggregate_features(fit_frame, link_stats=None)
    apply_aggregate, _ = add_aggregate_features(apply_frame, link_stats=stats)
    return fit_aggregate, apply_aggregate


def _distribution(values) -> dict:
    counts = pd.Series(values).value_counts().sort_index()
    return {str(key): int(value) for key, value in counts.items()}


def fold_splits(base: pd.DataFrame, *, n_splits: int = N_SPLITS):
    for column in ('run_id', 'tick', 'config_id'):
        if column not in base:
            raise ValueError('base missing column ' + column)
    if 'is_fault' in base and base['is_fault'].astype(int).any():
        raise ValueError('calibration base contains fault rows')
    ordered = base.sort_values(['run_id', 'tick']).reset_index(drop=True)
    groups = ordered['config_id'].to_numpy()
    if len(set(groups)) != n_splits:
        raise ValueError('expected exactly %d calibration configs' % n_splits)
    splitter = GroupKFold(n_splits=n_splits)
    for fold, (fit_index, val_index) in enumerate(splitter.split(ordered, groups=groups)):
        fit_frame, val_frame = ordered.iloc[fit_index], ordered.iloc[val_index]
        held = sorted(set(val_frame['config_id']))
        if len(held) != 1 or held[0] in set(fit_frame['config_id']) or \
                set(fit_frame.run_id) & set(val_frame.run_id):
            raise ValueError('fold is not leave-one-config-out')
        yield fold, held[0], fit_frame, val_frame


def heldout_calibration(base: pd.DataFrame, families: dict,
                        *, n_splits: int = N_SPLITS) -> dict:
    pooled = {name: {'k': [], 'excess': []} for name in families}
    folds = []
    for fold, held, fit_frame, val_frame in fold_splits(base, n_splits=n_splits):
        fit_aggregate, val_aggregate = _prepare(fit_frame, val_frame)
        primary_bounds = fit_bounds(fit_aggregate, families['primary'])
        judgeable71 = score(val_aggregate, primary_bounds,
                            families['primary'])['judgeable']
        record = {'fold': fold, 'held_out_config': held,
                  'n_fit_rows': len(fit_frame), 'n_val_rows': len(val_frame),
                  'families': {}}
        for name, columns in families.items():
            bounds = fit_bounds(fit_aggregate, columns)
            scores = score(val_aggregate, bounds, columns)
            if name in ('indicator', 'rate_shared'):
                scores['judgeable'] = judgeable71
            valid = scores[scores.judgeable]
            if valid.empty:
                raise ValueError('fold %d family %s has no judgeable calibration row' %
                                 (fold, name))
            pooled[name]['k'].extend(valid['k'].tolist())
            pooled[name]['excess'].extend(valid['excess'].tolist())
            record['families'][name] = {
                'n_judgeable': len(valid),
                'k_max': int(valid['k'].max()),
                'k_distribution': _distribution(valid['k']),
                'share_k_gt_0': float((valid['k'] > 0).mean()),
                'excess_max': float(valid['excess'].max()),
                'n_constant_on_fold_fit': int(sum(
                    bounds[c]['min'] == bounds[c]['max'] for c in columns)),
            }
        folds.append(record)
    thresholds = {name: {
        'K': int(max(values['k'])),
        'E': float(max(values['excess'])),
        'n_pooled_rows': len(values['k']),
    } for name, values in pooled.items()}
    return {'folds': folds, 'thresholds': thresholds,
            'rule': 'K=max held-out k, E=max held-out excess; alarm strict >'}
