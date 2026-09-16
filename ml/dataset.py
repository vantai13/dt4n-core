#!/usr/bin/env python3
"""Lesson 5.6 — API DUY NHẤT để nạp dataset. Phase 6 không được nạp cách khác.

VÌ SAO MỘT API DUY NHẤT LÀ CƠ CHẾ, KHÔNG PHẢI TIỆN LỢI:
    Sau 5 lesson bạn có: 6 quyết định nhãn, 3 tầng chính sách missing, một
    ma trận đã ký, một split đã đóng băng. TẤT CẢ đang là kỷ luật trong docs.
    Phase 6 la mot file Python moi, va no khong doc docs.

    Neu Phase 6 tu `glob('*.jsonl')` + `train_test_split(shuffle=True)`, moi
    ky luat cua Phase 5 bien mat trong MOT dong code, va khong co gi bao loi.
    `load_split()` la cach chan: no la duong DUY NHAT, va no da cai san ca
    bon tang chong leakage.

BỐN TẦNG ĐƯỢC CÀI SẴN (không phải nhắc nhở):
    T1 chia theo run_id       -> doc tu contract['split'] DA KY, khong tinh lai
    T2 feature chi dung qua khu -> delta/rolling luon groupby+shift
    T3 scaler fit tren train  -> link_stats fit tren TRAIN, transform cho TEST
    T4 chon feature khong nhan -> select_features(train_df) chi nhan train

TÍNH TẤT ĐỊNH: bon nguon phi tat dinh bi chan tuong minh — thu tu file (lap
theo contract da ky), thu tu cot (sorted), thu tu dong (sort_values), va
feature_names duoc GHI ra manifest de doi chieu. Thu tu COT la nguon nguy
hiem nhat: IF chon chieu ngau nhien theo CHI SO, nen doi thu tu cot = doi cay
= doi score, ma khong co gi bao loi.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ml import campaign as C
from ml import labels as L
from ml.features import (add_aggregate_features, add_delta_features,
                         add_rolling_features, select_features)
from ml.flatten import load_jsonl
from ml.missing import apply_policy, assert_no_fabricated_zero_in_loss

DATASET_VERSION = 'DT4N-D1'

# Nhãn và mặt nạ: KHÔNG BAO GIỜ là feature. schema.META_COLS đã chặn, đây là
# lớp chặn thứ hai — hai lớp vì đây là lỗi hủy hoại toàn bộ kết quả.
LABEL_COLS = ('is_fault', 'eval_primary', 'eval_sensitivity')


@dataclass
class Split:
    """Kết quả nạp. y_test TÁCH RỜI khỏi meta — có ý.

    VÌ SAO TÁCH: neu `meta` chua base_rate cua test va code train doc `meta`,
    ban co the vo tinh dat `contamination = base_rate` -> nhan test chay vao
    mo hinh qua cua sau. Chua nhan o mot truong RIENG, va `meta` chi chua
    thu code train duoc phep thay.
    """
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_test: pd.Series
    eval_primary: pd.Series
    eval_sensitivity: pd.Series
    groups_train_run: pd.Series
    groups_train_config: pd.Series
    feature_names: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def config_id(record: dict) -> str:
    """Khóa nhóm cho leave-one-CONFIG-out. KHÁC run_id — và khác biệt QUAN TRỌNG.

    N-load2M-s1003-r1 va N-load2M-s1004-r2 khac SEED nhung CUNG cau hinh.
    GroupKFold theo run_id se train tren r1 va validate tren r2 -> validate
    tren dieu kien mo hinh DA THAY -> uoc luong QUA CAO kha nang tong quat
    sang muc tai moi.

    GroupKFold theo config_id (4 nhom: 1M/2M/4M/vary) tra loi cau hoi dung:
    "mo hinh tong quat sang MUC TAI CHUA TUNG THAY khong?" — va do chinh la
    kiem chung truc tiep Nguyen tac 1 cua Lesson 5.3.
    """
    load = record.get('load_mbps_per_client')
    return '%s|%s' % (record['profile'],
                      'vary' if load is None else '%g' % load)


def _frames(contract, root, run_ids, sidecar_check=True):
    """Nạp từng run + gắn nhãn theo KHÓA. Lặp theo contract['runs'] ĐÃ KÝ."""
    records = {r['run_id']: r for r in contract['runs']}
    manifest = json.loads((root / 'results/report/ml_dataset_manifest.json').read_text())
    if not manifest['complete']:
        raise ValueError('campaign is incomplete')
    frames, tables, cfg = [], [], {}
    for rid in run_ids:                     # thứ tự do contract quyết, KHÔNG glob
        record = records[rid]
        paths = C.run_paths(rid, root)
        side = json.loads(paths['meta'].read_text())
        if sidecar_check:
            if manifest['runs'][rid]['sha256'] != side['sha256'] or manifest['runs'][rid]['status'] != 'ok':
                raise ValueError('manifest acceptance mismatch: ' + rid)
            if side['record'] != record or side['constants'] != contract['constants'] or side['label_convention'] != L.LABEL_CONVENTION_COLLECTED or side['collection_provenance']['source_dirty']:
                raise ValueError('sidecar record/constants/convention/source mismatch: ' + rid)
            if bool(side['events']) != bool(record.get('fault')):
                raise ValueError('events disagree with fault record: ' + rid)
            if side['design_content_sha256'] != contract['design_content_sha256']:
                raise ValueError('sidecar lech design SHA: ' + rid)
            if C.sha256_file(paths['final']) != side['sha256']:
                raise ValueError('raw lech sha256 sidecar: ' + rid)
            if side['checks'].get('passed') is not True:
                raise ValueError('run chua duoc nghiem thu: ' + rid)
        df = load_jsonl(paths['final'])
        if len(df) != side['checks']['n_snapshots'] or not df.run_id.eq(rid).all() or not df.design_content_sha256.eq(contract['design_content_sha256']).all():
            raise ValueError('raw identity/count mismatch: ' + rid)
        for event in side['events']:
            if df.iloc[event['tick']]['t_rel'] != event['t_rel']:
                raise ValueError('event clock mismatch: ' + rid)
        frames.append(df)
        tables.append(L.label_table(
            run_id=rid, n_snapshots=len(df), events=side['events'],
            warmup_ticks=int(contract['constants']['warmup_ticks']),
            split=record['split'], group=record['group'],
            fault=record.get('fault'), fault_target=record.get('fault_target'),
            seed=record.get('seed'),
            max_separation=side['checks'].get('max_separation')))
        cfg[rid] = config_id(record)
    df = pd.concat(frames, ignore_index=True, sort=False)
    assert_no_fabricated_zero_in_loss(df)
    df = L.attach_labels(df, tables)        # ghép theo (run_id, tick)
    df['config_id'] = df['run_id'].map(cfg)
    return df, tables


def load_split(root: Path | None = None, *, use_rolling: bool = False,
               rolling_window: int = 3, nan_policy: str = 'drop_train_keep_test'
               ) -> Split:
    """ĐƯỜNG DUY NHẤT để Phase 6 lấy dữ liệu.

    `nan_policy='drop_train_keep_test'` — chốt ở Lesson 5.6:
        TRAIN: bo dong con NaN o feature (IsolationForest khong nhan NaN),
               CO DEM, khong bo am tham. (DT4N-M1 tang 3)
        TEST : GIU dong NaN. Detector phai tra "unknown" va tick do tinh la
               FALSE NEGATIVE neu y=1.

        Vi sao KHONG loai tick NaN khoi mau danh gia: 8 o thieu cua ban la
        `counter_reset` tai dung tick 21/41 cua cac run degrade/shift — tuc
        thieu VI CO can thiep (MNAR CO CAU TRUC: 0.313% trong cua so fault vs
        0.055% o background, cao hon 5.7 lan). Loai chung = xoa dung mau kho
        -> recall phong. Do dung la cai bay Lesson 5.2 dung ra de chong.

        Quy mo nho (<=4/160 tick duong = 2.5%) nen chon cach khat khe gan nhu
        khong ton gi va KHONG THE bi che. Va no khop ban doi ung Phase 7:
        mot canh bao khong duoc phat LA mot lan bo sot.
    """
    if nan_policy != 'drop_train_keep_test':
        raise ValueError('unsupported nan_policy')
    root = Path(root or C.ROOT)
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    integrity = C.check_contract_integrity(contract)
    if not integrity['match']:
        raise ValueError('hop dong bi sua sau khi ky — dung lai')

    # T1: split ĐỌC từ contract đã ký, KHÔNG tính lại, KHÔNG shuffle
    train_ids = list(contract['split']['train'])
    test_ids = list(contract['split']['test'])
    if set(train_ids) & set(test_ids):
        raise ValueError('train va test giao nhau trong hop dong')

    warmup = int(contract['constants']['warmup_ticks'])
    tr_raw, tr_tables = _frames(contract, root, train_ids)
    te_raw, te_tables = _frames(contract, root, test_ids)

    if set(tr_raw.collector_version) | set(te_raw.collector_version) != {
            contract['constants']['collector_version']}:
        raise ValueError('tron collector_version — lossPct v1 va v2 la hai '
                         'dai luong khac nhau, khong duoc gop')

    tr, pol_tr = apply_policy(tr_raw, warmup_ticks=warmup)
    te, pol_te = apply_policy(te_raw, warmup_ticks=warmup)

    # T3: link_stats (scaler) FIT trên TRAIN, TRANSFORM cho TEST
    tr, link_stats = add_aggregate_features(tr, link_stats=None)
    te, _ = add_aggregate_features(te, link_stats=link_stats)

    # T4: chọn feature CHỈ từ train, CHỈ bằng luật không nhãn
    sel = select_features(tr)
    feats = [c for c in sel['features'] if c not in LABEL_COLS]

    # T2: feature thời gian — luôn groupby run_id, luôn shift
    tr = add_delta_features(tr, feats)
    te = add_delta_features(te, feats)
    feats = feats + sorted('d1.' + c for c in feats)
    if use_rolling:
        base = [c for c in feats if not c.startswith('d1.')]
        tr = add_rolling_features(tr, base, rolling_window)
        te = add_rolling_features(te, base, rolling_window)
        feats = feats + sorted('ma%d.%s' % (rolling_window, c) for c in base)
    if not feats:
        raise ValueError('no features selected from train')
    tr[feats] = tr[feats].apply(pd.to_numeric, errors='coerce').replace([float('inf'), -float('inf')], float('nan'))
    te[feats] = te[feats].apply(pd.to_numeric, errors='coerce').replace([float('inf'), -float('inf')], float('nan'))
    feats = sorted(set(feats))              # thứ tự cột TẤT ĐỊNH

    tr = tr.sort_values(['run_id', 'tick']).reset_index(drop=True)
    te = te.sort_values(['run_id', 'tick']).reset_index(drop=True)

    # NaN: train bỏ CÓ ĐẾM, test GIỮ
    n_tr_before = len(tr)
    tr_ok = tr.loc[tr[feats].notna().all(axis=1)].copy()
    te_nan = te[feats].isna().any(axis=1)

    meta = {
        'dataset_version': DATASET_VERSION,
        'label_convention_id': L.LABEL_CONVENTION_ID,
        'design_content_sha256': contract['design_content_sha256'],
        'collector_version': contract['constants']['collector_version'],
        'constants': contract['constants'],
        'split': {'train': train_ids, 'test': test_ids},
        'feature_names': feats,
        'n_features': len(feats),
        'feature_selection': sel['rules'],
        'n_features_dropped': len(sel['dropped']),
        'link_stats_fitted_on': 'train',
        'link_stats_n_columns': len(link_stats),
        'link_stats': link_stats,
        'feature_selection_dropped': sel['dropped'],
        'test_row_keys': te[['run_id','tick']].to_dict('records'),
        'unjudgeable_rows': [dict(run_id=row.run_id, tick=int(row.tick), is_fault=int(row.is_fault), missing_features=[c for c in feats if pd.isna(row[c])]) for _,row in te.loc[te_nan].iterrows()],
        'use_rolling': use_rolling,
        'rolling_window': rolling_window if use_rolling else None,
        'missing_policy_train': pol_tr,
        'missing_policy_test': pol_te,
        'nan_policy': nan_policy,
        'n_train_rows_before_nan_drop': n_tr_before,
        'n_train_rows': len(tr_ok),
        'n_train_rows_dropped_nan': n_tr_before - len(tr_ok),
        'n_test_rows': len(te),
        # Con số Phase 6 PHẢI báo cáo để giải thích recall bị mất đi đâu
        'n_test_rows_with_nan_feature': int(te_nan.sum()),
        'n_test_rows_with_nan_and_fault': int((te_nan & te.is_fault.eq(1)).sum()),
        'n_test_rows_with_nan_and_normal': int((te_nan & te.is_fault.eq(0)).sum()),
        'groups_train_run_n': tr_ok.run_id.nunique(),
        'groups_train_config_n': tr_ok.config_id.nunique(),
        'warning_train_has_no_faults': bool(
            'is_fault' in tr_ok and tr_ok.is_fault.sum() == 0),
    }
    if not meta['warning_train_has_no_faults']:
        raise ValueError('TRAIN chua fault — vi pham Nguyen tac 3 cua Lesson 5.3')

    return Split(
        X_train=tr_ok[feats], X_test=te[feats],
        y_test=te['is_fault'],
        eval_primary=te['eval_primary'], eval_sensitivity=te['eval_sensitivity'],
        groups_train_run=tr_ok['run_id'], groups_train_config=tr_ok['config_id'],
        feature_names=feats, meta=meta)
