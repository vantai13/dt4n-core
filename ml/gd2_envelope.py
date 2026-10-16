#!/usr/bin/env python3
"""
gd2_envelope.py — GĐ2: huấn luyện lại envelope với tập train SẠCH, so sánh với 1.0.0.

NGUYÊN TẮC: chỉ đổi MỘT thứ — tập train. Mọi thứ khác giữ nguyên như Phase 6:
  - cùng bộ cột đã ĐĂNG KÝ (families_from_registration), không chọn cột lại;
  - cùng thuật toán biên min/max (ml.detectors.envelope.fit_bounds);
  - cùng cách đặt ngưỡng K/E: leave-one-config-out, chỉ trên train (heldout_calibration);
  - cùng hàm đánh giá evaluate() của scripts/run_phase6_envelope.py, cùng tập test.

BA PHƯƠNG ÁN được tính bằng CÙNG một đường code:
  v1         : 8 run train gốc (có s1008)  -> PHẢI tái lập đúng số đã công bố
  v2-excl    : bỏ s1008, chưa có run thay  -> xem trước hướng thay đổi (không cần thu)
  v2         : bỏ s1008 + run thay thế N-vary-s1008-r3 (thu ở chiến dịch gd2)

LƯU Ý TRUNG THỰC: tập test Phase 5 ĐÃ được mở ở Phase 6. Số của v2 trên tập này là
kết quả MÔ TẢ, không phải kết quả xác nhận trên dữ liệu chưa thấy.

CÁCH CHẠY (không cần Mininet):
    python3 -m ml.gd2_envelope reproduce   # v1 qua đường code GĐ2 == số đã công bố?
    python3 -m ml.gd2_envelope preview     # v1 vs v2-excl
    python3 -m ml.gd2_envelope build       # cần dữ liệu gd2: ghi models/envelope-2.0.0.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import labels as L
from ml.dataset import config_id
from ml.detectors import envelope as E
from ml.features import add_aggregate_features
from ml.flatten import load_jsonl
from ml.missing import apply_policy, assert_no_fabricated_zero_in_loss

P5_CONTRACT = 'results/report/experiment_matrix.json'
P5_MANIFEST = 'results/report/ml_dataset_manifest.json'
BAD_RUN = 'N-vary-s1008-r2'
REPLACEMENT_RUN = 'N-vary-s1008-r3'
MODEL_V2 = 'models/envelope-2.0.0.json'
COMPARE_OUT = 'results/report/gd2_envelope_compare.json'
PREVIEW_OUT = 'results/report/gd2_envelope_preview.json'
VARIANTS = ('primary_k', 'secondary_excess', 'secondary_dual', 'ablation_loss_only')


# ===========================================================================
# PHẦN 1 — nạp run kèm MỌI kiểm tra toàn vẹn như ml/dataset._frames,
#          nhưng cho phép nguồn khác (thư mục, manifest của chiến dịch gd2).
#          (ml/dataset.py có mã băm nằm trong prereg Phase 5/6 nên KHÔNG sửa.)
# ===========================================================================
def load_frames(contract: dict, run_ids: list, run_paths, manifest_path: Path) -> pd.DataFrame:
    records = {r['run_id']: r for r in contract['runs']}
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if not manifest.get('complete'):
        raise ValueError('chiến dịch chưa hoàn tất: %s' % manifest_path)
    frames, tables, cfg = [], [], {}
    for rid in run_ids:
        record = records[rid]
        paths = run_paths(rid)
        side = json.loads(paths['meta'].read_text(encoding='utf-8'))
        if manifest['runs'][rid]['sha256'] != side['sha256'] or manifest['runs'][rid]['status'] != 'ok':
            raise ValueError('manifest không khớp sidecar: ' + rid)
        if (side['record'] != record or side['constants'] != contract['constants']
                or side['label_convention'] != L.LABEL_CONVENTION_COLLECTED
                or side['collection_provenance']['source_dirty']):
            raise ValueError('sidecar lệch record/constants/convention/source: ' + rid)
        if side['design_content_sha256'] != contract['design_content_sha256']:
            raise ValueError('sidecar lệch design SHA: ' + rid)
        if C.sha256_file(paths['final']) != side['sha256']:
            raise ValueError('raw lệch sha256 sidecar: ' + rid)
        if side['checks'].get('passed') is not True:
            raise ValueError('run chưa được nghiệm thu: ' + rid)
        df = load_jsonl(paths['final'])
        if len(df) != side['checks']['n_snapshots'] or not df.run_id.eq(rid).all():
            raise ValueError('raw identity/count mismatch: ' + rid)
        frames.append(df)
        tables.append(L.label_table(
            run_id=rid, n_snapshots=len(df), events=side['events'],
            warmup_ticks=int(contract['constants']['warmup_ticks']),
            split=record['split'], group=record['group'],
            fault=record.get('fault'), fault_target=record.get('fault_target'),
            seed=record.get('seed'), max_separation=side['checks'].get('max_separation')))
        cfg[rid] = config_id(record)
    df = pd.concat(frames, ignore_index=True, sort=False)
    assert_no_fabricated_zero_in_loss(df)
    df = L.attach_labels(df, tables)
    df['config_id'] = df['run_id'].map(cfg)
    return df


def phase5_source(root: Path):
    contract = C.load_contract(root / P5_CONTRACT)
    if not C.check_contract_integrity(contract, root)['match']:
        raise RuntimeError('hợp đồng Phase 5 bị sửa')
    return contract, (lambda rid: C.run_paths(rid, root)), root / P5_MANIFEST


def gd2_source(root: Path):
    from ml import gd2campaign as G
    contract = G.load_contract(root / G.CONTRACT_REL)
    if not G.check_integrity(contract, root)['match']:
        raise RuntimeError('hợp đồng gd2 bị sửa')
    return contract, (lambda rid: G.run_paths(rid, root)), root / G.MANIFEST_REL


def load_variant_raw(variant: str, root: Path):
    """(train_raw, test_raw, warmup, train_ids) cho một phương án."""
    p5, p5_paths, p5_manifest = phase5_source(root)
    warmup = int(p5['constants']['warmup_ticks'])
    train_ids = list(p5['split']['train'])
    test_ids = list(p5['split']['test'])
    if variant == 'v1':
        parts = [load_frames(p5, train_ids, p5_paths, p5_manifest)]
        used = train_ids
    elif variant in ('v2-excl', 'v2'):
        keep = [r for r in train_ids if r != BAD_RUN]
        parts = [load_frames(p5, keep, p5_paths, p5_manifest)]
        used = list(keep)
        if variant == 'v2':
            g, g_paths, g_manifest = gd2_source(root)
            if g['constants'] != p5['constants']:
                raise RuntimeError('hằng số gd2 khác Phase 5')
            parts.append(load_frames(g, [REPLACEMENT_RUN], g_paths, g_manifest))
            used.append(REPLACEMENT_RUN)
    else:
        raise ValueError(variant)
    train_raw = pd.concat(parts, ignore_index=True, sort=False)
    test_raw = load_frames(p5, test_ids, p5_paths, p5_manifest)
    versions = set(train_raw.collector_version) | set(test_raw.collector_version)
    if versions != {p5['constants']['collector_version']}:
        raise RuntimeError('trộn collector_version: %s' % versions)
    return train_raw, test_raw, warmup, used


# ===========================================================================
# PHẦN 2 — huấn luyện + đánh giá MỘT phương án (đúng các bước của Phase 6)
# ===========================================================================
def threshold_owners(base: pd.DataFrame, fam: dict) -> dict:
    """Run/tick nào ĐẶT ngưỡng K và E (dòng có k / excess lớn nhất khi bị giữ ra)."""
    best = {}
    for _, held, fit_frame, val_frame in E.fold_splits(base):
        fit_agg, val_agg = E._prepare(fit_frame, val_frame)
        primary_bounds = E.fit_bounds(fit_agg, fam['primary'])
        j71 = E.score(val_agg, primary_bounds, fam['primary'])['judgeable']
        for name, cols in fam.items():
            scores = E.score(val_agg, E.fit_bounds(fit_agg, cols), cols)
            if name in ('indicator', 'rate_shared'):
                scores['judgeable'] = j71
            valid = scores[scores.judgeable]
            for key in ('k', 'excess'):
                idx = valid[key].idxmax()
                value = float(valid.loc[idx, key])
                slot = best.setdefault(name, {}).get(key)
                if slot is None or value > slot['value']:
                    best[name][key] = {'value': value, 'run_id': val_frame.loc[idx, 'run_id'],
                                       'tick': int(val_frame.loc[idx, 'tick']),
                                       'held_out_config': held}
    return best


def fit_and_evaluate(variant: str, root: Path, n_boot=None, rng_seed=None,
                     loader=None) -> dict:
    """``loader(variant, root)`` thay load_variant_raw khi nguồn train khác (GĐ4)."""
    from scripts.run_phase6_envelope import evaluate, families_from_registration, \
        verify_registration
    fam = families_from_registration()
    unc = verify_registration()['prereg']['content']['metrics']['uncertainty']
    n_boot = unc['n_boot'] if n_boot is None else n_boot
    rng_seed = unc['rng_seed'] if rng_seed is None else rng_seed

    train_raw, test_raw, warmup, used = (loader or load_variant_raw)(variant, root)

    # (a) ngưỡng K/E: CHỈ train, leave-one-config-out (giống stage_cv)
    base, _ = apply_policy(train_raw, warmup_ticks=warmup)
    base = base.sort_values(['run_id', 'tick']).reset_index(drop=True)
    calib = E.heldout_calibration(base, fam)
    owners = threshold_owners(base, fam)

    # (b) biên cuối + đánh giá trên test (giống load_split -> evaluate)
    tr, _ = apply_policy(train_raw, warmup_ticks=warmup)
    te, _ = apply_policy(test_raw, warmup_ticks=warmup)
    tr, link_stats = add_aggregate_features(tr, link_stats=None)
    te, _ = add_aggregate_features(te, link_stats=link_stats)
    cols = fam['primary']
    for frame in (tr, te):
        frame[cols] = frame[cols].apply(pd.to_numeric, errors='coerce').replace(
            [np.inf, -np.inf], np.nan)
    tr = tr.sort_values(['run_id', 'tick']).reset_index(drop=True)
    te = te.sort_values(['run_id', 'tick']).reset_index(drop=True)
    p5 = C.load_contract(root / P5_CONTRACT)
    faults = {r['run_id']: r.get('fault') for r in p5['runs']}
    report, _ = evaluate(fam=fam, X_train_env=tr[cols], X_test_env=te[cols],
                         keys=te[['run_id', 'tick']].to_dict('records'),
                         y=te['is_fault'].to_numpy(), eval_primary=te['eval_primary'].to_numpy(),
                         faults=faults, thresholds=calib['thresholds'],
                         n_boot=n_boot, rng_seed=rng_seed)
    bounds = E.fit_bounds(tr[cols], cols)
    return {'variant': variant, 'train_run_ids': used, 'n_train_rows': int(len(base)),
            'thresholds': calib['thresholds'], 'owners': owners, 'folds': calib['folds'],
            'bounds': bounds, 'link_stats': link_stats, 'families': fam, 'report': report,
            'victim_visibility': victim_visibility(te, bounds)}


def victim_visibility(te: pd.DataFrame, bounds: dict) -> dict:
    """Số tick client tụt DƯỚI biên dưới txRate: run lỗi -> trong cửa sổ lỗi (y=1);
    run đối chứng C -> cả run. Đo trực tiếp giới hạn "hệ không thấy nạn nhân"."""
    out = {}
    for rid, g in te.groupby('run_id'):
        if rid.startswith('F-'):
            g = g[g['is_fault'] == 1]
        out[rid] = {c.split('.')[0].replace('host-', ''): int((g[c] < bounds[c]['min']).sum())
                    for c in TRACKED_BOUNDS}
    return out


# ===========================================================================
# PHẦN 3 — tóm tắt, so sánh, kiểm tái lập
# ===========================================================================
TRACKED_BOUNDS = ['host-h1.traffic.txRate', 'host-h2.traffic.txRate',
                  'host-h3.traffic.txRate']


def summary(res: dict) -> dict:
    out = {'train_run_ids': res['train_run_ids'], 'n_train_rows': res['n_train_rows'],
           'thresholds': {k: {'K': v['K'], 'E': round(v['E'], 4)}
                          for k, v in res['thresholds'].items()},
           'owner_K_rate': res['owners']['rate_shared']['k'],
           'owner_E_primary': res['owners']['primary']['excess'],
           'lower_bound_txRate_mbps': {
               c: round(res['bounds'][c]['min'] * 8 / 1e6, 3)
               for c in TRACKED_BOUNDS if c in res['bounds']},
           'victim_visibility': {r: v for r, v in res['victim_visibility'].items()
                                 if r.startswith('C-') or any(v.values())},
           'variants': {}}
    for name in VARIANTS:
        r = res['report'][name]
        s = r['scores']
        out['variants'][name] = {
            'recall': round(s['recall'], 4), 'recall_ceiling': round(s['recall_ceiling'], 4),
            'fpr_all': round(s['fpr'], 4), 'fpr_control': r['fpr']['control']['fpr'],
            'tp': s['tp'], 'fp': s['fp'], 'fn': s['fn'],
            'delay_median': r['delay']['median_delay_detected'],
            'n_censored': r['delay']['n_censored'],
            'recall_by_fault': {f: round(v['pooled']['recall'], 4)
                                for f, v in r['by_fault'].items()},
        }
    return out


def reproduce_check(root: Path) -> dict:
    """v1 qua đường code GĐ2 phải ra ĐÚNG ngưỡng và điểm số đã công bố ở Phase 6."""
    res = fit_and_evaluate('v1', root)
    cv = json.loads((root / 'results/report/phase6_envelope_cv.json').read_text())['content']
    pub = json.loads((root / 'results/report/phase6_envelope.json').read_text())['content']
    mismatches = []
    for fam_name, t in cv['thresholds'].items():
        mine = res['thresholds'][fam_name]
        if mine['K'] != t['K'] or abs(mine['E'] - t['E']) > 1e-9:
            mismatches.append('ngưỡng %s: %s vs công bố %s' % (fam_name, mine, t))
    keys = ('recall', 'fpr', 'tp', 'fp', 'fn', 'n_positive', 'n_negative')
    for name in VARIANTS:
        a, b = res['report'][name]['scores'], pub['variants'][name]['scores']
        for k in keys:
            if abs(float(a[k]) - float(b[k])) > 1e-12:
                mismatches.append('%s.%s: %s vs công bố %s' % (name, k, a[k], b[k]))
    return {'match': not mismatches, 'mismatches': mismatches, 'v1': summary(res)}


def compare(results: list) -> dict:
    return {'note': ('Tập test Phase 5 đã được mở ở Phase 6: các số dưới đây là MÔ TẢ, '
                     'không phải xác nhận trên dữ liệu chưa thấy. Chỉ tập train thay đổi; '
                     'cột, thuật toán, cách đặt ngưỡng, tập test giữ nguyên.'),
            'variants': {r['variant']: summary(r) for r in results}}


def print_compare(cmp: dict) -> None:
    names = list(cmp['variants'])
    print('\n%-34s' % '' + ''.join('%-18s' % n for n in names))
    def row(label, getter):
        print('%-34s' % label + ''.join('%-18s' % getter(cmp['variants'][n]) for n in names))
    row('K (rate_shared) / E (primary)', lambda v: '%d / %.2f' % (
        v['thresholds']['rate_shared']['K'], v['thresholds']['primary']['E']))
    row('run đặt K', lambda v: v['owner_K_rate']['run_id'].replace('N-', '')[:16])
    for c in TRACKED_BOUNDS:
        row('biên dưới %s (Mbps)' % c.split('.')[0].replace('host-', ''),
            lambda v, c=c: '%.3f' % v['lower_bound_txRate_mbps'][c])
    for name in VARIANTS:
        row('%s recall' % name, lambda v, n=name: '%.3f' % v['variants'][n]['recall'])
        row('%s FPR' % name, lambda v, n=name: '%.4f' % v['variants'][n]['fpr_all'])
    row('dual recall degrade', lambda v: '%.3f' % v['variants']['secondary_dual']
        ['recall_by_fault'].get('degrade', float('nan')))
    row('dual recall flood', lambda v: '%.3f' % v['variants']['secondary_dual']
        ['recall_by_fault'].get('flood', float('nan')))
    row('h3 dưới biên, flood h1 (tick lỗi)', lambda v: '%d / 20' % v['victim_visibility']
        .get('F-flood-h1_to_srv1-s3005-r1', {}).get('h3', 0))
    row('client dưới biên, đối chứng C', lambda v: '%d' % sum(
        sum(x.values()) for r, x in v['victim_visibility'].items() if r.startswith('C-')))
    print('\n' + cmp['note'])


# ===========================================================================
# PHẦN 4 — artifact envelope-2.0.0 (cùng định dạng, kiểm bởi ml.model.EnvelopeModel)
# ===========================================================================
def build_artifact(res: dict, root: Path) -> dict:
    from ml.model import SCHEMA_VERSION, EnvelopeModel
    v1 = json.loads((root / 'models/envelope-1.0.0.json').read_text())['content']
    fam = res['families']
    content = {
        'schema_version': SCHEMA_VERSION,
        'version': 'envelope-2.0.0',
        'columns': list(fam['primary']),
        'families': {k: list(v) for k, v in fam.items()},
        'bounds': res['bounds'],
        'thresholds': {k: {'K': int(v['K']), 'E': float(v['E'])}
                       for k, v in res['thresholds'].items()},
        'floors': v1['floors'],
        'link_stats': res['link_stats'],
        'feature_spec': v1['feature_spec'],
        'unknown_policy': v1['unknown_policy'],
        'provenance': {
            'replaces': 'envelope-1.0.0',
            'change': 'train: bỏ %s (h1,h3 txRate=0), thêm %s (qua cổng client_traffic)'
                      % (BAD_RUN, REPLACEMENT_RUN),
            'train_run_ids': res['train_run_ids'],
            'n_train_rows_envelope': res['n_train_rows'],
            'threshold_owners': res['owners'],
            'envelope_code_sha256': C.sha256_file(root / 'ml/detectors/envelope.py'),
            'gd2_code_sha256': C.sha256_file(root / 'ml/gd2_envelope.py'),
            'built_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'scope_note': 'Vòng kín Phase 8 KHÔNG dùng bản này; Phase 8 gắn với 1.0.0.',
        },
    }
    model = EnvelopeModel(content)
    model._check_content(content)
    return content, model


def _write_once(path: Path, doc) -> None:
    if path.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % path)
    C.atomic_json(path, doc)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = C.ROOT
    cmd = argv[0] if argv else ''
    if cmd == 'reproduce':
        rep = reproduce_check(root)
        print('Tái lập v1 qua đường code GĐ2: %s' % ('✅ KHỚP' if rep['match'] else '❌ LỆCH'))
        for m in rep['mismatches']:
            print('  - ' + m)
        return 0 if rep['match'] else 1
    if cmd == 'preview':
        cmp = compare([fit_and_evaluate('v1', root), fit_and_evaluate('v2-excl', root)])
        C.atomic_json(root / PREVIEW_OUT, cmp)
        print_compare(cmp)
        print('đã ghi: %s' % PREVIEW_OUT)
        return 0
    if cmd == 'build':
        rep = reproduce_check(root)
        if not rep['match']:
            raise SystemExit('Không tái lập được v1 -> không build v2: %s' % rep['mismatches'])
        results = [fit_and_evaluate(v, root) for v in ('v1', 'v2-excl', 'v2')]
        content, model = build_artifact(results[2], root)
        cmp = compare(results)
        cmp['model_v2_sha256'] = model.content_sha256
        _write_once(root / MODEL_V2, {'content': content, 'content_sha256': model.content_sha256})
        _write_once(root / COMPARE_OUT, cmp)
        print_compare(cmp)
        print('\nđã ghi: %s (sha %s…) và %s' % (MODEL_V2, model.content_sha256[:12], COMPARE_OUT))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
