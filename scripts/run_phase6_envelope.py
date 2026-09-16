#!/usr/bin/env python3
"""Lesson 6.3 — chạy envelope theo HAI GIAI ĐOẠN, test chỉ mở ở giai đoạn 2.

    python -m scripts.run_phase6_envelope cv     # chỉ train normal -> K, E
    git add + commit phase6_envelope_cv.json      # ĐÓNG BĂNG ngưỡng
    python -m scripts.run_phase6_envelope test   # mở test MỘT lần

Giai đoạn test TỪ CHỐI chạy nếu: file CV chưa commit/đang sửa, code detector
khác code đã tính K, bản đăng ký bị sửa, hoặc kết quả test đã tồn tại.
"""
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
from ml.detectors import envelope as E
from ml.missing import apply_policy

REPORT = C.ROOT / 'results/report'
CV_OUT = REPORT / 'phase6_envelope_cv.json'
TEST_OUT = REPORT / 'phase6_envelope.json'
TICKS_OUT = REPORT / 'phase6_envelope_ticks.csv'
PLOT_OUT = REPORT / 'phase6_envelope_k.png'
CODE = [C.ROOT / 'ml/detectors/envelope.py', C.ROOT / 'scripts/run_phase6_envelope.py',
        C.ROOT / 'ml/metrics.py']


def _hash(obj) -> str:
    return C.sha256_bytes(C.canonical_json(obj).encode('utf-8'))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


# --- 0. bản đăng ký và mã nguồn phải nguyên vẹn ----------------------------
def verify_registration() -> dict:
    pre = _read(REPORT / 'phase6_prereg.json')
    am = _read(REPORT / 'phase6_prereg_amendment_1.json')
    am2 = _read(REPORT / 'phase6_prereg_amendment_2.json')
    if _hash(pre['content']) != pre['prereg_content_sha256']:
        raise RuntimeError('prereg bi sua')
    if _hash(am['content']) != am['amendment_content_sha256'] or \
            am['content']['amends_prereg_content_sha256'] != pre['prereg_content_sha256']:
        raise RuntimeError('amendment bi sua hoac khong tro dung prereg')
    if _hash(am2['content']) != am2['amendment_content_sha256'] or \
            am2['content']['amendment_1_content_sha256'] != am['amendment_content_sha256']:
        raise RuntimeError('amendment 2 bi sua hoac khong tro dung amendment 1')
    return {'prereg': pre, 'amendment': am, 'amendment2': am2}


def families_from_registration() -> dict:
    reg = verify_registration()
    return E.registered_families(reg['amendment'], _read(REPORT / 'ml_dataset_split_manifest.json'))


def code_fingerprint() -> dict:
    return {str(p.relative_to(C.ROOT)): C.sha256_file(p) for p in CODE}


def assert_committed_clean(paths) -> None:
    for p in paths:
        rel = str(Path(p).relative_to(C.ROOT))
        tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', rel], cwd=C.ROOT,
                                 capture_output=True).returncode == 0
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', rel], cwd=C.ROOT,
                               capture_output=True, text=True).stdout.strip()
        if not tracked or dirty:
            raise RuntimeError('chua commit sach: ' + rel)


# --- 1. train base: giống load_split tới trước aggregate --------------------
def load_train_base(root: Path | None = None) -> pd.DataFrame:
    root = Path(root or C.ROOT)
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    if not C.check_contract_integrity(contract)['match']:
        raise RuntimeError('hop dong bi sua')
    raw, _ = _frames(contract, root, list(contract['split']['train']))
    if set(raw.collector_version) != {contract['constants']['collector_version']}:
        raise RuntimeError('tron collector_version')
    base, _ = apply_policy(raw, warmup_ticks=int(contract['constants']['warmup_ticks']))
    return base.sort_values(['run_id', 'tick']).reset_index(drop=True)


# --- 2. GIAI ĐOẠN CV --------------------------------------------------------
def stage_cv() -> int:
    if CV_OUT.exists():
        print('[cv] da ton tai, khong ghi de'); return 1
    fam = families_from_registration()
    base = load_train_base()
    if len(base) != 472:
        raise RuntimeError('train base phai 472 dong, nhan %d' % len(base))
    rep = E.heldout_calibration(base, fam)
    reg = verify_registration()
    content = {'lesson': '6.3-cv', 'data': 'train normal only; no test rows loaded',
               'amendment2_content_sha256': reg['amendment2']['amendment_content_sha256'],
               'families': {k: len(v) for k, v in fam.items()},
               'code_sha256': code_fingerprint(), **rep}
    doc = {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'content': content, 'content_sha256': _hash(content)}
    C.atomic_json(CV_OUT, doc)
    for f in rep['folds']:
        print('[cv] fold %d held=%-22s' % (f['fold'], f['held_out_config']),
              {n: (v['k_max'], round(v['share_k_gt_0'], 3)) for n, v in f['families'].items()})
    print('[cv] thresholds', rep['thresholds'])
    return 0


# --- 3. GIAI ĐOẠN TEST ------------------------------------------------------
def evaluate(*, fam, X_train_env, X_test_env, keys, y, eval_primary, faults, thresholds,
             n_boot, rng_seed) -> tuple[dict, pd.DataFrame]:
    """Thuần: nhận ma trận + ngưỡng đã đóng băng, trả báo cáo + bảng tick."""
    bounds = {n: E.fit_bounds(X_train_env, cols) for n, cols in fam.items()}
    S = {n: E.score(X_test_env, bounds[n], cols) for n, cols in fam.items()}
    j71 = S['primary']['judgeable'].to_numpy()
    T = {n: thresholds[n] for n in fam}
    alarms = {
        'primary_k': E.alarm(S['primary'], T['primary']['K']),
        'secondary_excess': E.alarm(S['primary'], T['primary']['E'], key='excess'),
        'secondary_dual': E.dual_alarm(S['indicator'], S['rate_shared'], j71,
                                       T['indicator']['K'], T['rate_shared']['K']),
        'ablation_loss_only': E.alarm(S['loss_only'], T['loss_only']['K']),
    }
    judge = {'primary_k': j71, 'secondary_excess': j71, 'secondary_dual': j71,
             'ablation_loss_only': S['loss_only']['judgeable'].to_numpy()}
    run_id = [k['run_id'] for k in keys]
    tick = [int(k['tick']) for k in keys]
    group = [r[0] for r in run_id]
    fault = [faults.get(r) for r in run_id]
    report = {}
    for name, a in alarms.items():
        f = M.build_frame(run_id=run_id, tick=tick, group=group, fault=fault, y=y,
                          eval_mask=eval_primary, judgeable=judge[name], alarm=a,
                          mask_name='eval_primary')
        report[name] = {'scores': M.point_wise_scores(f), 'fpr': M.fpr_breakdown(f),
                        'by_fault': M.scores_by_fault(f), 'delay': M.detection_delay(f),
                        'bootstrap': M.cluster_bootstrap(f, n_boot=n_boot, rng_seed=rng_seed)}
    ticks = pd.DataFrame({'run_id': run_id, 'tick': tick, 'y': np.asarray(y, dtype=int),
                          'k': S['primary']['k'], 'excess': S['primary']['excess'],
                          'k_ind': S['indicator']['k'], 'k_rate': S['rate_shared']['k'],
                          'k_loss': S['loss_only']['k'], 'judgeable71': j71,
                          'judgeable_loss': judge['ablation_loss_only'],
                          **{'alarm_' + n: a for n, a in alarms.items()}})
    return report, ticks


def plot_k(ticks: pd.DataFrame, K: int, path: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    runs = sorted(ticks.run_id.unique())
    fig, axes = plt.subplots(len(runs), 1, figsize=(10, 1.6 * len(runs)), sharex=True)
    for ax, rid in zip(axes, runs):
        g = ticks[ticks.run_id == rid]
        ax.fill_between(g.tick, 0, g.k.max() + 1, where=g.y.astype(bool), alpha=0.15, step='mid')
        ax.step(g.tick, g.k, where='mid', lw=1)
        ax.scatter(g.tick[~g.judgeable71], g.k[~g.judgeable71], marker='x', color='red', s=20)
        ax.axhline(K, ls='--', lw=0.8, color='k')
        ax.set_ylabel(rid.replace('-s', '\n-s', 1), fontsize=6)
    axes[-1].set_xlabel('tick  (vung to = y=1, x do = unknown, net dut = K)')
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def stage_test() -> int:
    if TEST_OUT.exists():
        print('[test] ket qua da ton tai: test chi mo MOT lan'); return 1
    reg = verify_registration()
    assert_committed_clean([CV_OUT, *CODE, REPORT / 'phase6_prereg_amendment_1.json',
                            REPORT / 'phase6_prereg_amendment_2.json'])
    cv = _read(CV_OUT)
    if _hash(cv['content']) != cv['content_sha256'] or cv['content']['code_sha256'] != code_fingerprint():
        raise RuntimeError('CV bi sua hoac code da doi sau khi tinh K')
    from ml.dataset import load_split
    fam = families_from_registration()
    split = load_split()
    official = {c: {'min': v['min'], 'max': v['max']} for c, v in split.envelope.items()}
    if E.fit_bounds(split.X_train_envelope, fam['primary']) != official:
        raise RuntimeError('bounds cuoi lech load_split')
    contract = C.load_contract(REPORT / 'experiment_matrix.json')
    faults = {r['run_id']: r.get('fault') for r in contract['runs']}
    unc = reg['prereg']['content']['metrics']['uncertainty']
    report, ticks = evaluate(fam=fam, X_train_env=split.X_train_envelope,
                             X_test_env=split.X_test_envelope, keys=split.meta['test_row_keys'],
                             y=split.y_test.to_numpy(), eval_primary=split.eval_primary.to_numpy(),
                             faults=faults, thresholds=cv['content']['thresholds'],
                             n_boot=unc['n_boot'], rng_seed=unc['rng_seed'])
    ticks.to_csv(TICKS_OUT, index=False)
    plot_k(ticks, cv['content']['thresholds']['primary']['K'], PLOT_OUT)
    content = {'lesson': '6.3-test', 'cv_content_sha256': cv['content_sha256'],
               'prereg_content_sha256': reg['prereg']['prereg_content_sha256'],
               'amendment_content_sha256': reg['amendment']['amendment_content_sha256'],
               'amendment2_content_sha256': reg['amendment2']['amendment_content_sha256'],
               'code_sha256': code_fingerprint(), 'thresholds': cv['content']['thresholds'],
               'recall_ceiling_note': 'primary/dual/excess 0.975; loss_only per its own unknown count',
               'ticks_csv_sha256': C.sha256_file(TICKS_OUT), 'variants': report}
    C.atomic_json(TEST_OUT, {'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                             'content': content, 'content_sha256': _hash(content)})
    for name, r in report.items():
        s = r['scores']
        print('[test] %-20s recall=%.3f (tran %.3f) FPR_ctrl=%s delay_med=%s censored=%d' % (
            name, s['recall'], s['recall_ceiling'], r['fpr']['control']['fpr'],
            r['delay']['median_delay_detected'], r['delay']['n_censored']))
    return 0


if __name__ == '__main__':
    stages = {'cv': stage_cv, 'test': stage_test}
    if len(sys.argv) != 2 or sys.argv[1] not in stages:
        print(__doc__); sys.exit(2)
    sys.exit(stages[sys.argv[1]]())
