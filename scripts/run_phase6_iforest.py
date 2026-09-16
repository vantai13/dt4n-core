#!/usr/bin/env python3
"""Two-stage Phase 6 Isolation Forest runner: CV freeze, then one-shot test."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import metrics as M
from ml.dataset import _frames
from ml.detectors import iforest as F
from ml.missing import apply_policy

REPORT = C.ROOT / 'results/report'
CV_OUT = REPORT / 'phase6_iforest_cv.json'
TEST_OUT = REPORT / 'phase6_iforest.json'
TICKS_OUT = REPORT / 'phase6_iforest_ticks.csv'
SCORE_PLOT = REPORT / 'phase6_iforest_scores.png'
DIST_PLOT = REPORT / 'phase6_iforest_score_dist.png'
LEDGER = REPORT / 'phase6_hypothesis_ledger.json'
LEDGER_2 = REPORT / 'phase6_hypothesis_ledger_2.json'
MANIFEST = REPORT / 'ml_dataset_split_manifest.json'
PREREG = REPORT / 'phase6_prereg.json'
CODE = [C.ROOT / 'ml/detectors/iforest.py',
        C.ROOT / 'scripts/run_phase6_iforest.py', C.ROOT / 'ml/metrics.py']
INDICATOR_MARKERS = ('.traffic.lossPct', '.status.state_up',
                     '.traffic.qdiscDropDelta', 'agg.links_down',
                     'agg.loss_max', 'agg.loss_n_above_alert')
N_TRAIN_BASE_ROWS = 472


def _hash(value):
    return C.sha256_bytes(C.canonical_json(value).encode('utf-8'))


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def code_fingerprint():
    return {str(path.relative_to(C.ROOT)): C.sha256_file(path) for path in CODE}


def assert_committed_clean(paths):
    for path in paths:
        relative = str(Path(path).relative_to(C.ROOT))
        tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', relative],
                                 cwd=C.ROOT, capture_output=True).returncode == 0
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', relative],
                               cwd=C.ROOT, capture_output=True, text=True).stdout.strip()
        if not tracked or dirty:
            raise RuntimeError('chua commit sach: ' + relative)


def verify_registration():
    prereg = _read(PREREG)
    if _hash(prereg['content']) != prereg['prereg_content_sha256']:
        raise RuntimeError('prereg bi sua')
    return {'prereg': prereg}


def registered_iforest():
    prereg = verify_registration()['prereg']['content']['detectors']['iforest']
    return F.registered_config(prereg)


def verify_ledger():
    ledger = _read(LEDGER)
    if _hash(ledger['content']) != ledger['ledger_content_sha256']:
        raise RuntimeError('so quyet dinh gia thuyet bi sua')
    timing = ledger['content']['timing_and_knowledge']
    if timing['iforest_fitted_on_campaign_train'] or \
            timing['iforest_campaign_test_scores_seen']:
        raise RuntimeError('so quyet dinh khai da thay so IF: thu tu bi pha')
    filled = [(name, field)
              for name, row in ledger['content']['hypotheses'].items()
              for field, value in row['evidence'].items()
              if field.startswith('iforest') and value is not None]
    if filled:
        raise RuntimeError('so quyet dinh da bi dien so IF: %s' % filled)
    return ledger


def verify_ledger_2():
    ledger = _read(LEDGER_2)
    if _hash(ledger['content']) != ledger['ledger_content_sha256']:
        raise RuntimeError('so quyet dinh 2 bi sua')
    timing = ledger['content']['timing_and_knowledge']
    if not timing['iforest_fitted_on_campaign_train']:
        raise RuntimeError('so quyet dinh 2 phai duoc viet SAU khi co CV train-only')
    if timing['iforest_campaign_test_scores_seen']:
        raise RuntimeError('so quyet dinh 2 khai da thay so test: thu tu bi pha')
    return ledger


def frozen_columns_from_manifest():
    columns = F.frozen_columns(_read(MANIFEST)['feature_names'])
    leaked = [c for c in columns if any(marker in c for marker in INDICATOR_MARKERS)]
    if leaked:
        raise RuntimeError('cot chi bao lot vao tap IF: %s' % leaked)
    return columns


def load_train_base(root: Path | None = None):
    root = Path(root or C.ROOT)
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    if not C.check_contract_integrity(contract)['match']:
        raise RuntimeError('hop dong bi sua')
    raw, _ = _frames(contract, root, list(contract['split']['train']))
    base, _ = apply_policy(raw, warmup_ticks=int(contract['constants']['warmup_ticks']))
    return base.sort_values(['run_id', 'tick']).reset_index(drop=True)


def stage_cv(*, seeds=None, quantiles=None):
    seeds = tuple(F.SEEDS if seeds is None else seeds)
    quantiles = tuple(F.QUANTILES if quantiles is None else quantiles)
    if CV_OUT.exists():
        print('[cv] da ton tai, khong ghi de')
        return 1
    ledger = verify_ledger()
    config = registered_iforest()
    columns = frozen_columns_from_manifest()
    base = load_train_base()
    if len(base) != N_TRAIN_BASE_ROWS:
        raise RuntimeError('train base phai %d dong, nhan %d' %
                           (N_TRAIN_BASE_ROWS, len(base)))
    report = F.heldout_calibration(base, columns, seeds=seeds,
                                   quantiles=quantiles,
                                   max_samples=F.PRIMARY_MAX_SAMPLES)
    train_values, train_labels = F.train_matrix(base, columns)
    frozen = F.final_thresholds(train_values, seeds=seeds, quantiles=quantiles,
                                max_samples_list=F.MAX_SAMPLES)
    ownership = {str(seed): F.tail_ownership(
        train_values, train_labels, seed=seed,
        q=(F.PRIMARY_Q if F.PRIMARY_Q in quantiles else quantiles[0]))
        for seed in seeds}
    dynamics = F.dynamics_profile(train_values, train_labels)
    content = {
        'lesson': '6.4-cv', 'data': 'train normal only; no test rows loaded',
        'registered_config': config,
        'grid_used': {'seeds': list(seeds), 'quantiles': list(quantiles),
                      'max_samples': F.PRIMARY_MAX_SAMPLES},
        'is_full_registered_grid': (list(seeds) == list(F.SEEDS) and
                                    list(quantiles) == list(F.QUANTILES)),
        'n_columns': len(columns), 'columns': columns,
        'ledger_content_sha256': ledger['ledger_content_sha256'],
        'interpretation_declared_before_cv': {
            'what': ('IF column identity is frozen to the 72 registered feature_names in '
                     'every fold; only link_stats and the forest are refit on fold-train. '
                     'select_features is not re-run.'),
            'why': ('the preregistration fixed the IF hyperparameters but did not state a '
                    'fold refit rule for column selection; this fills that gap using the '
                    'reason amendment 2 gave for the envelope, namely that a per-fold '
                    'column set changes the score scale'),
            'change_type': 'gap-filling interpretation; no registered rule altered',
            'declared_before': 'any campaign IF fit and any test row load',
        },
        'n_train_rows_after_nan_drop': len(train_values),
        'tail_samples_by_q': {str(q): F.effective_tail_samples(len(train_values), q)
                              for q in quantiles},
        'final_thresholds': frozen, 'tail_ownership': ownership,
        'dynamics_profile': dynamics,
        'code_sha256': code_fingerprint(), **report,
    }
    document = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'content': content, 'content_sha256': _hash(content)}
    CV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CV_OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    q_show = F.PRIMARY_Q if F.PRIMARY_Q in quantiles else quantiles[0]
    for fold in report['folds']:
        rates = [row['alarm_rate_by_q'][str(q_show)]['alarm_rate']
                 for row in fold['per_seed'].values()]
        mean_rate = float(np.mean(rates))
        ratio = mean_rate / q_show
        print('[cv] fold %d held=%-22s const=%2d  alarm@q=%.01f%% -> %.2f%% (x%.1f)%s' %
              (fold['fold'], fold['held_out_config'], fold['n_constant_on_fold_fit'],
               q_show * 100, mean_rate * 100, ratio,
               '  [FLAG]' if ratio > F.HONESTY_RATIO_FLAG else ''))
    for q, row in report['summary_by_q'].items():
        print('[cv] q=%-6s mean alarm %.4f (x%.1f)%s' %
              (q, row['mean_alarm_rate'], row['mean_ratio_to_q'],
               '  [FLAG]' if row['honesty_flag'] else ''))
    return 0


def evaluate_one(*, model_scores_train, model_scores_test, keys, y,
                 eval_primary, faults, q, n_boot, rng_seed):
    threshold = F.threshold_from_train(model_scores_train, q)
    fired = F.alarm(model_scores_test, threshold)
    run_id = [key['run_id'] for key in keys]
    frame = M.build_frame(
        run_id=run_id, tick=[int(key['tick']) for key in keys],
        group=[rid[0] for rid in run_id], fault=[faults.get(rid) for rid in run_id],
        y=y, eval_mask=eval_primary,
        judgeable=model_scores_test['judgeable'].to_numpy(), alarm=fired,
        mask_name='eval_primary')
    return {'q': q, 'threshold': threshold,
            'scores': M.point_wise_scores(frame), 'fpr': M.fpr_breakdown(frame),
            'by_fault': M.scores_by_fault(frame), 'delay': M.detection_delay(frame),
            'bootstrap': M.cluster_bootstrap(frame, n_boot=n_boot,
                                             rng_seed=rng_seed)}, fired


def _nested(row, path):
    for key in path:
        row = row[key]
    return row


def seed_summary(per_seed, path):
    return M.summarize_seeds(_nested(row, path) for row in per_seed.values())


def noise_arm(*, n_train, n_test, n_features, judgeable, keys, y,
              eval_primary, faults, n_boot, rng_seed):
    run_id = [key['run_id'] for key in keys]
    per_seed = {}
    for seed in F.SEEDS:
        control = F.noise_control(n_train, n_test, n_features, seed=seed)
        fired = np.asarray(control.pop('alarm_flags')) & judgeable
        frame = M.build_frame(
            run_id=run_id, tick=[int(key['tick']) for key in keys],
            group=[rid[0] for rid in run_id], fault=[faults.get(rid) for rid in run_id],
            y=y, eval_mask=eval_primary, judgeable=judgeable, alarm=fired,
            mask_name='eval_primary')
        control['metrics'] = {
            'scores': M.point_wise_scores(frame), 'fpr': M.fpr_breakdown(frame),
            'delay': M.detection_delay(frame),
            'bootstrap': M.cluster_bootstrap(frame, n_boot=n_boot,
                                             rng_seed=rng_seed),
        }
        per_seed[str(seed)] = control
    return {'per_seed': per_seed,
            'across_seeds': {
                metric: seed_summary(per_seed, ('metrics', 'scores', metric))
                for metric in ('recall', 'fpr', 'fpr_judgeable_only',
                               'precision', 'f1')},
            'campaign_unknown_mask_applied': True}


def _plots(ticks, threshold, train_scores):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    runs = sorted(ticks.run_id.unique())
    fig, axes = plt.subplots(len(runs), 1, figsize=(10, 1.6 * len(runs)), sharex=True)
    for axis, run_id in zip(axes, runs):
        group = ticks[ticks.run_id == run_id]
        axis.fill_between(group.tick, group.score.min(), threshold,
                          where=group.y.astype(bool), alpha=.15, step='mid')
        axis.step(group.tick, group.score, where='mid', lw=1)
        axis.scatter(group.tick[~group.judgeable], group.score[~group.judgeable],
                     marker='x', color='red', s=20)
        axis.axhline(threshold, ls='--', lw=.8, color='k')
        axis.set_ylabel(run_id.replace('-s', '\n-s', 1), fontsize=6)
    axes[-1].set_xlabel('tick (shaded = y=1, dashed = q=0.01 threshold)')
    fig.tight_layout(); fig.savefig(SCORE_PLOT, dpi=130); plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 4))
    axis.hist(train_scores, bins=35, alpha=.55, label='train normal')
    axis.hist(ticks.loc[ticks.judgeable & ticks.y.eq(0), 'score'], bins=35,
              alpha=.55, label='test normal')
    axis.hist(ticks.loc[ticks.judgeable & ticks.y.eq(1), 'score'], bins=35,
              alpha=.55, label='test fault')
    axis.axvline(threshold, ls='--', color='k', label='q=0.01 threshold')
    axis.legend(); axis.set_xlabel('score_samples (lower = more anomalous)')
    fig.tight_layout(); fig.savefig(DIST_PLOT, dpi=130); plt.close(fig)


def stage_test():
    if TEST_OUT.exists():
        print('[test] ket qua da ton tai: test chi mo MOT lan')
        return 1
    registration = verify_registration()
    verify_ledger()
    ledger2 = verify_ledger_2()
    assert_committed_clean([CV_OUT, LEDGER, LEDGER_2, *CODE])
    cv = _read(CV_OUT)
    if _hash(cv['content']) != cv['content_sha256']:
        raise RuntimeError('CV bi sua sau khi ky')
    if cv['content']['code_sha256'] != code_fingerprint():
        raise RuntimeError('code doi sau khi tinh nguong CV')
    if not cv['content'].get('is_full_registered_grid'):
        raise RuntimeError('CV chay luoi rut gon (smoke test), khong dung cho test that')
    columns = frozen_columns_from_manifest()
    if cv['content']['columns'] != columns:
        raise RuntimeError('tap cot doi so voi luc CV')
    registered_iforest()

    from ml.dataset import load_split
    split = load_split()
    if sorted(split.feature_names) != columns:
        raise RuntimeError('feature_names cua load_split lech tap cot da dong bang')
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {row['run_id']: row.get('fault') for row in contract['runs']}
    uncertainty = registration['prereg']['content']['metrics']['uncertainty']
    keys = split.meta['test_row_keys']; y = split.y_test.to_numpy()
    eval_primary = split.eval_primary.to_numpy()
    X_train = F.matrix(split.X_train, columns); X_test = F.matrix(split.X_test, columns)

    configs = {}; primary_ticks = None; primary_train_scores = None
    primary_threshold = None
    for max_samples in F.MAX_SAMPLES:
        per_seed = {}
        for seed in F.SEEDS:
            model = F.fit(X_train, seed=seed, max_samples=max_samples)
            train_scores = F.score(model, X_train)['score'].to_numpy()
            frozen_row = cv['content']['final_thresholds'][str(max_samples)][str(seed)]
            for q in F.QUANTILES:
                recalculated = F.threshold_from_train(train_scores, q)
                if recalculated != frozen_row['threshold_by_q'][str(q)]:
                    raise RuntimeError('nguong tinh lai khac nguong da dong bang o CV')
            test_scores = F.score(model, X_test)
            by_q = {}; fired_primary = None
            for q in F.QUANTILES:
                report, fired = evaluate_one(
                    model_scores_train=train_scores, model_scores_test=test_scores,
                    keys=keys, y=y, eval_primary=eval_primary, faults=faults, q=q,
                    n_boot=uncertainty['n_boot'], rng_seed=uncertainty['rng_seed'])
                by_q[str(q)] = report
                if q == F.PRIMARY_Q:
                    fired_primary = fired
            per_seed[str(seed)] = {
                'by_q': by_q,
                'train_score': F._distribution(train_scores),
                'split_usage': F.split_usage(model, columns),
            }
            if max_samples == F.PRIMARY_MAX_SAMPLES and seed == F.SEEDS[0]:
                primary_train_scores = train_scores
                primary_threshold = by_q[str(F.PRIMARY_Q)]['threshold']
                primary_ticks = pd.DataFrame({
                    'run_id': [key['run_id'] for key in keys],
                    'tick': [int(key['tick']) for key in keys], 'y': y.astype(int),
                    'score': test_scores['score'],
                    'judgeable': test_scores['judgeable'],
                    'alarm_q01': fired_primary})
        configs[str(max_samples)] = {
            'per_seed': per_seed,
            'across_seeds': {str(q): {
                metric: seed_summary(per_seed, ('by_q', str(q), 'scores', metric))
                for metric in ('recall', 'fpr', 'fpr_judgeable_only', 'precision', 'f1')}
                for q in F.QUANTILES},
            'never_split_across_seeds': sorted(set.intersection(*[
                set(row['split_usage']['columns_never_split'])
                for row in per_seed.values()])),
        }

    judgeable = primary_ticks['judgeable'].to_numpy()
    noise = noise_arm(
        n_train=len(X_train), n_test=len(X_test), n_features=len(columns),
        judgeable=judgeable, keys=keys, y=y, eval_primary=eval_primary,
        faults=faults, n_boot=uncertainty['n_boot'],
        rng_seed=uncertainty['rng_seed'])
    primary_ticks.to_csv(TICKS_OUT, index=False)
    _plots(primary_ticks, primary_threshold, primary_train_scores)
    content = {
        'lesson': '6.4-test', 'cv_content_sha256': cv['content_sha256'],
        'ledger_content_sha256': _read(LEDGER)['ledger_content_sha256'],
        'ledger_2_content_sha256': ledger2['ledger_content_sha256'],
        'prereg_content_sha256': registration['prereg']['prereg_content_sha256'],
        'code_sha256': code_fingerprint(), 'n_columns': len(columns),
        'configs': configs, 'noise_control': noise,
        'ticks_csv_sha256': C.sha256_file(TICKS_OUT),
        'score_plot_sha256': C.sha256_file(SCORE_PLOT),
        'distribution_plot_sha256': C.sha256_file(DIST_PLOT),
    }
    with TEST_OUT.open('x', encoding='utf-8') as handle:
        json.dump({'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'content': content, 'content_sha256': _hash(content)},
                  handle, indent=2)
        handle.write('\n')
    primary = configs[str(F.PRIMARY_MAX_SAMPLES)]['across_seeds'][str(F.PRIMARY_Q)]
    print('[test] recall mean=%.4f FPR mean=%.4f noise recall mean=%.4f' %
          (primary['recall']['mean'], primary['fpr']['mean'],
           noise['across_seeds']['recall']['mean']))
    return 0


if __name__ == '__main__':
    stages = {'cv': stage_cv, 'test': stage_test}
    if len(sys.argv) != 2 or sys.argv[1] not in stages:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(stages[sys.argv[1]]())
