#!/usr/bin/env python3
"""Lesson 5.6 — TẬP FEATURE: chọn bằng luật KHÔNG NHÃN, và feature suy diễn.

VÌ SAO FILE NÀY TỒN TẠI:
    Lesson 5.1 sinh ra `campaign_feature_audit.csv` với cột `auc_dist` và
    quyết định GIU/CHAT_VAN. `auc_dist` được tính từ `is_fault` trên TOÀN BỘ
    18 run — GỒM 10 run TEST. Nếu tập feature của mô hình lấy từ cột
    `quyet_dinh` đó, thì việc chọn feature đã dùng nhãn test.

    Đó là FEATURE SELECTION LEAKAGE. Hậu quả không phải "recall lệch chút";
    là recall MẤT NGHĨA, vì tập feature đã được tối ưu trên chính tập dùng
    để đo.

    File này phân đôi các luật theo NGUỒN THÔNG TIN:
      - Luật CẤU TRÚC (kind): không cần dữ liệu, không cần nhãn.   -> CHỌN
      - Luật TRAIN-ONLY (nunique, pct_null trên TRAIN):            -> CHỌN
      - Luật auc_dist:                              cần nhãn test  -> KHÔNG
    `auc_dist` xuống hạng thành phân tích MÔ TẢ HẬU NGHIỆM, ghi trong báo
    cáo với nhãn "in-sample", không bao giờ quyết định tập feature.

NGUYÊN TẮC "MỘT CỔNG, MỘT HƯỚNG":
    Thông tin từ test được phép chảy RA (thành số báo cáo), không bao giờ
    chảy VÀO (thành quyết định thiết kế). Mọi hàm ở đây chỉ nhận DataFrame
    TRAIN khi cần thống kê. Chữ ký hàm là hàng rào: không có tham số nào
    nhận nhãn.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.schema import REASON, column_kind, is_feature_candidate

# --- trần tỉ lệ thiếu, ĐO TRÊN TRAIN. 20% là quy ước, ghi vào manifest ----
NULL_LIMIT_PCT_TRAIN = 20.0

# --- ngưỡng "có loss đáng kể" cho feature đếm. 1% là quy ước vận hành -----
# Chọn 1% vì đó cũng là ngưỡng baseline luật mà Phase 6 sẽ so sánh -> hai
# thứ dùng cùng một định nghĩa "loss đáng kể", không phải hai con số rời.
LOSS_ALERT_PCT = 1.0


# =========================================================================
# 1. CHỌN FEATURE — chỉ bằng luật không nhãn + thống kê TRAIN
# =========================================================================
FAULT_INDICATOR_SUFFIX = ('.lossPct', '.qdiscDropDelta', '.state_up',
                          '.loss_max', '.loss_n_above_alert', '.links_down')


def select_features(train_df: pd.DataFrame,
                    null_limit_pct: float = NULL_LIMIT_PCT_TRAIN) -> dict:
    """Choose IF columns and envelope bounds using structure and train only.

    Constant fault indicators remain visible to envelope, not IF. Other
    constants are unused (dead); this does not prove they have no domain value.
    """
    if not np.isfinite(null_limit_pct) or not 0 <= null_limit_pct <= 100:
        raise ValueError('null_limit_pct must be between 0 and 100')
    dropped, dead, envelope, kept = {}, {}, {}, []
    for col in train_df.columns:
        kind = column_kind(col)
        if not is_feature_candidate(col):
            dropped[col] = REASON['meta'] if kind == 'meta' else REASON['text']
            continue
        if kind in ('cumulative', 'config'):
            dropped[col] = REASON[kind]
            continue
        values = pd.to_numeric(train_df[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
        pct_null = 100.0 * values.isna().mean()
        if not values.notna().any() or pct_null > null_limit_pct:
            dropped[col] = '%s (train: %.2f%%)' % (REASON['mostly_null'], pct_null)
            continue
        constant = values.nunique(dropna=True) <= 1
        if constant and not col.endswith(FAULT_INDICATOR_SUFFIX):
            dead[col] = '%s (constant train; outside registered indicator families)' % REASON['constant']
            continue
        envelope[col] = {'min': float(values.min()), 'max': float(values.max()),
                         'n_train': int(values.notna().sum()),
                         'reason': 'constant fault indicator; envelope only' if constant else 'variable on train'}
        if not constant:
            kept.append(col)
    return {'features': sorted(kept), 'envelope': dict(sorted(envelope.items())),
            'dead': dict(sorted(dead.items())), 'dropped': dict(sorted(dropped.items())),
            'rules': {'structural': ['meta','text','cumulative','config'],
                      'train_only': {'null_limit_pct': null_limit_pct,
                                     'constant_on_train': 'indicator families to envelope; others unused'},
                      'fault_indicator_suffix': list(FAULT_INDICATOR_SUFFIX),
                      'label_based_rules_used': [],
                      'note': 'Audit/test labels never select model columns or bounds.'}}


def envelope_exceedance_counts(df, envelope, features=None):
    """Strict violations of fitted bounds; return counts and missingness separately.

    A partial count on a missing row is not a normal decision. The consumer
    must report unknown according to its declared missing-data protocol.
    """
    cols = sorted(envelope) if features is None else list(features)
    if not cols or len(cols) != len(set(cols)):
        raise ValueError('envelope columns must be nonempty and unique')
    counts = pd.Series(0, index=df.index, dtype='int32')
    missing = pd.Series(0, index=df.index, dtype='int32')
    for col in cols:
        if col not in envelope or col not in df:
            raise ValueError('missing envelope column: ' + col)
        lo, hi = envelope[col]['min'], envelope[col]['max']
        if not np.isfinite(lo) or not np.isfinite(hi) or lo > hi:
            raise ValueError('invalid envelope bounds: ' + col)
        values = pd.to_numeric(df[col], errors='coerce').replace([np.inf,-np.inf], np.nan)
        counts += ((values < lo) | (values > hi)).astype('int32')
        missing += values.isna().astype('int32')
    return pd.DataFrame({'k': counts, 'n_missing': missing})


def envelope_alarm_threshold(train_df, envelope, features):
    """Fit K on train. With same-sample min/max, K=0 is a tautology.

    No held-out FPR guarantee; keep missing counts for consumer decisions.
    """
    if train_df.empty:
        raise ValueError('cannot calibrate on empty train')
    measured = envelope_exceedance_counts(train_df, envelope, features)
    maximum = int(measured.k.max())
    return {'K': maximum, 'k_train_max': maximum,
            'k_train_mean': round(float(measured.k.mean()),4),
            'n_envelope_columns': len(features),
            'n_train_rows': len(train_df),
            'n_train_rows_with_missing': int(measured.n_missing.gt(0).sum()),
            'rule': 'alarm iff strict bound violation count > K; missing status handled separately',
            'calibration_note': 'same-sample min/max implies K=0; held-out FPR unmeasured'}


# =========================================================================
# 2. FEATURE TỔNG HỢP — bất biến vị trí, giữ cực trị
# =========================================================================
def _cols_ending(df, suffix):
    return sorted(c for c in df.columns if c.startswith('link-') and c.endswith(suffix))


def add_aggregate_features(df: pd.DataFrame,
                           link_stats: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Thêm cột tổng hợp trên các link. Trả (df_mới, thống_kê_để_tái_dùng).

    VÌ SAO CẦN — TRẦN TOÁN HỌC CỦA FEATURE ĐƠN:
        "fault o link X" va "fault o link Y" la CUNG mot hien tuong vat ly
        nhung hien o HAI cot khac nhau. Voi 8 run fault chia 4 vi tri, moi
        vi tri chi co 2 run — qua it de hoc. Do la vi sao auc_dist cao nhat
        trong audit cua ban chi 0.368: mot cot lossPct chi "thay" 2/8 run
        fault, nen tran AUC don bien bi chan boi CAU TRUC thi nghiem.

        Cot tong hop bieu dien vi tri; mo hinh fit chi tren normal train.

    VÌ SAO `max`/`count` CHỨ KHÔNG `mean`:
        1 link loss 53%, 7 link loss 0  ->  mean = 6.6% (dim 8 lan)
                                            max  = 53%  (nguyen ven)
        Luat L2 cua Lesson 5.1 ("khong gop 8 link thanh trung binh") van
        duoc ton trong: cot per-link GIU NGUYEN de dinh vi; cot tong hop la
        THEM VAO de phat hien.

    `link_stats` LÀ SCALER TRONG LỐT FEATURE:
        max_abs_z can mean/std tung link. Chung PHAI fit tren TRAIN.
        - link_stats=None  -> tinh tu df nay (CHI goi voi df TRAIN)
        - link_stats=dict  -> dung lai (goi voi df TEST)
        Chuan hoa theo cua so truoc-inject dua vao nhan khong thuoc pipeline:
        de biet "dau la baseline" phai biet inject o dau, tuc dung nhan. Va
        o Phase 7 real-time ban KHONG biet -> feature do khong ton tai duoc
        luc inference. Kiem tra chung: feature nao khong tinh duoc o Phase 7
        thi la leakage o Phase 6.
    """
    out = df.copy()
    loss = _cols_ending(df, '.traffic.lossPct')
    state = _cols_ending(df, '.status.state_up')
    rates = _cols_ending(df, '.traffic.rxRate') + _cols_ending(df, '.traffic.txRate')
    rates = sorted(rates)

    if loss:
        L = out[loss].apply(pd.to_numeric, errors='coerce')
        # skipna=True CÓ Ý: một link không đo được không được phép xóa bằng
        # chứng từ bảy link còn lại. Nhưng nếu TẤT CẢ đều NaN -> vẫn NaN,
        # detector trả "unknown". Đúng: không biết thì nói không biết.
        out['agg.loss_max'] = L.max(axis=1, skipna=True)
        out['agg.loss_n_above_alert'] = L.gt(LOSS_ALERT_PCT).sum(axis=1).astype('int16')
        out['agg.loss_n_measured'] = L.notna().sum(axis=1).astype('int16')
    if state:
        S = out[state].apply(pd.to_numeric, errors='coerce')
        out['agg.links_down'] = S.eq(0).sum(axis=1).astype('int16')
        out['agg.links_state_measured'] = S.notna().sum(axis=1).astype('int16')

    stats = {} if link_stats is None else dict(link_stats)
    if rates:
        if link_stats is None:
            for col in rates:
                s = pd.to_numeric(out[col], errors='coerce')
                mu = float(s.mean())
                sd = float(s.std(ddof=1))
                # sàn: std=0 trên train -> chia 0. 1.0 byte/s là sàn trung tính.
                stats[col] = {'mean': mu if np.isfinite(mu) else 0.0, 'std': sd if np.isfinite(sd) and sd > 0 else 1.0}
        zs = []
        for col in rates:
            if col not in stats:
                continue
            s = pd.to_numeric(out[col], errors='coerce')
            zs.append(((s - stats[col]['mean']) / stats[col]['std']).abs())
        if zs:
            Z = pd.concat(zs, axis=1)
            out['agg.rate_absz_max'] = Z.max(axis=1, skipna=True)
            out['agg.rate_absz_n_above_3'] = Z.gt(3.0).sum(axis=1).astype('int16')
    return out, stats


# =========================================================================
# 3. FEATURE THỜI GIAN — chỉ dùng QUÁ KHỨ, và luôn groupby run_id
# =========================================================================
def add_delta_features(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """x[t] - x[t-1] TRONG CÙNG RUN. Chỉ tốn 1 tick priming/run.

    VÌ SAO ƯU TIÊN DELTA HƠN ROLLING cho bài toán này:
        rolling(5).shift(1) can 6 tick priming/run -> 10.2% tick thanh NaN
        (48/472 train, 60/590 test). Delta can 1 tick -> 1.7%.
        Va tin hieu cua ban la THAY DOI DOT NGOT (bang thong sup, loss xuat
        hien), dung loai ma delta bat tot nhat. Rolling mean lam muot -> lam
        CHAM phat hien, trong khi onset vat ly da chi 0-2 tick.

    `groupby('run_id')` BẮT BUỘC: khong co no, delta o tick 0 cua run k se
    la (x cua run k tick 0) - (x cua run k-1 tick 59) -> tron hai lan chay
    khac nhau thanh mot con so vo nghia.
    """
    if 'run_id' not in df.columns or 'tick' not in df.columns:
        raise ValueError('can run_id va tick de tinh delta trong tung run')
    out = df.sort_values(['run_id', 'tick']).copy()
    g = out.groupby('run_id', sort=False)
    for col in cols:
        s = pd.to_numeric(out[col], errors='coerce')
        out['d1.' + col] = s.groupby(out['run_id'], sort=False).diff()
    return out


def add_rolling_features(df: pd.DataFrame, cols: list[str], window: int = 3
                         ) -> pd.DataFrame:
    """Rolling mean CHỈ DÙNG QUÁ KHỨ. KHÔNG bật mặc định — dành cho ablation.

    HAI MẤU CHỐT, thiếu một là leakage:
        .shift(1)          -> cua so KET THUC TRUOC diem hien tai. Thieu no
                              la dung chinh diem dang du doan de tinh feature
                              cho no.
        groupby('run_id')  -> cua so khong vat qua ranh gioi giua hai run.

    Ham nay ton tai DU KHONG DUNG MAC DINH: khi Phase 6 muon ablation, no
    phai dung ham DA DUOC TEST GHIM, khong tu viet lai. Co che, khong ky luat.
    """
    if not isinstance(window, int) or isinstance(window, bool) or window < 2:
        raise ValueError('window phai >= 2')
    out = df.sort_values(['run_id', 'tick']).copy()
    for col in cols:
        s = pd.to_numeric(out[col], errors='coerce')
        out['ma%d.%s' % (window, col)] = s.groupby(out['run_id'], sort=False
            ).transform(lambda x: x.rolling(window).mean().shift(1))
    return out
