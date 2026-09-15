#!/usr/bin/env python3
"""Lesson 5.2 — ngữ nghĩa dữ liệu thiếu: null ≠ 0, và cơ chế thiếu là gì.

HAI KÊNH THIẾU DỮ LIỆU TRONG DT4N (plan chỉ nêu kênh thứ nhất):

  Kênh A — TRUNG THỰC (collector đã làm đúng):
      qdisc_interval() trả lossPct=None + qdiscValid=False + qdiscReason
      -> pandas thấy NaN. Ta biết mình không biết.

  Kênh B — BỊA SỐ 0 (vẫn còn, chưa được canh):
      compute_rate() trả 0.0 khi prev_val is None / dt<=0 / counter reset.
      collect_link() trả rxRate=txRate=interfaceLossPct=0.0 khi prev is None.
      -> "không đo được" trông y hệt "đo được và bằng 0".

  Kênh B không tự khai. Cách duy nhất phát hiện: đối chiếu với bộ đếm cộng
  dồn rxBytes/txBytes. Lesson 5.1 LOẠI hai cột đó khỏi feature -- nhưng ta
  GIỮ chúng trong snapshot để làm CÔNG CỤ KIỂM TOÁN. Đó là lý do không xóa.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

WARMUP_REASONS = ('warmup',)
INVESTIGATE_REASONS = ('unavailable', 'counter_reset')


# ---------------------------------------------------------------- thống kê
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy Wilson cho tỉ lệ k/n.

    Vì sao không dùng công thức thường (p ± z·sqrt(p(1-p)/n)): với p nhỏ và n
    vừa, nó cho biên dưới ÂM — vô nghĩa cho một tỉ lệ. Tệ hơn: khi k=0 nó cho
    [0,0], tức "chắc chắn 0%", trong khi 0/480 chỉ loại trừ được mức trên
    ~0.8% nếu áp dụng mô hình binomial độc lập. Pilot không có độc lập
    giữa link/tick; CI ở đây chỉ mô tả công thức.
    """
    if not isinstance(k, int) or not isinstance(n, int) or n < 0 or k < 0 or k > n or not math.isfinite(z) or z <= 0:
        raise ValueError('Wilson yêu cầu 0 <= k <= n và z hữu hạn > 0')
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - half) / d), min(1.0, (c + half) / d))


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """p-value Fisher chính xác cho bảng 2x2, không cần scipy.

        [[a, b],     a = fault & thiếu      b = fault & có
         [c, d]]     c = normal & thiếu     d = normal & có

    Dùng Fisher chứ không chi-square vì số ô thiếu rất nhỏ (8-16); xấp xỉ
    chi-square không đáng tin khi kỳ vọng ô < 5.
    """
    if any(not isinstance(x, int) or x < 0 for x in (a, b, c, d)):
        raise ValueError('Fisher yêu cầu số đếm nguyên không âm')
    n = a + b + c + d
    row1, col1 = a + b, a + c
    p_obs = (math.comb(row1, a) * math.comb(n - row1, col1 - a)
             / math.comb(n, col1))
    total = 0.0
    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    for k in range(lo, hi + 1):
        p = (math.comb(row1, k) * math.comb(n - row1, col1 - k)
             / math.comb(n, col1))
        if p <= p_obs * (1 + 1e-9):
            total += p
    return min(1.0, total)


# ------------------------------------------------- kênh A: qdisc / lossPct
def loss_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.endswith('.traffic.lossPct'))


def valid_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.endswith('.traffic.qdiscValid'))


def missing_by_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Tỉ lệ thiếu ở HAI mức: theo Ô (cell) và theo DÒNG (row).

    Hai mức này khác nhau, và plan chỉ nói tới mức dòng. Phân biệt quan
    trọng: nếu 1/8 link mất phép đo, bỏ cả dòng nghĩa là ném đi 7 phép đo
    tốt. Và nếu missing độc lập giữa link thì P(dòng bị bỏ) = 1-(1-p)^n_link, nên tỉ lệ hy sinh XẤU DẦN khi
    topology lớn lên — 1% thiếu ở 50 link làm mất 39.5% số dòng.
    """
    loss = loss_columns(df)
    if not loss:
        raise ValueError('không có cột lossPct để kiểm toán')
    recs = []
    for profile, g in df.groupby('profile', sort=False):
        cells = g[loss]
        n_cell = int(cells.size)
        k_cell = int(cells.isna().to_numpy().sum())
        rows_bad = cells.isna().any(axis=1)
        k_row, n_row = int(rows_bad.sum()), int(len(g))
        lo_c, hi_c = wilson_ci(k_cell, n_cell)
        recs.append({
            'profile': str(profile),
            'is_fault': int(g['is_fault'].iloc[0]),
            'n_rows': n_row, 'rows_missing': k_row,
            'pct_rows_missing': round(100 * k_row / n_row, 3),
            'n_cells': n_cell, 'cells_missing': k_cell,
            'pct_cells_missing': round(100 * k_cell / n_cell, 3),
            'cell_ci95_lo_pct': round(100 * lo_c, 3),
            'cell_ci95_hi_pct': round(100 * hi_c, 3),
        })
    return pd.DataFrame(recs)


def missing_reasons(df: pd.DataFrame) -> pd.DataFrame:
    """Đếm qdiscReason theo profile. LÝ DO QUAN TRỌNG HƠN TỈ LỆ.

    'warmup' là cơ chế BIẾT TRƯỚC, tiền định, không đọc gì về mạng ->
        theo định nghĩa Rubin đây là MAR, chứng minh được bằng mã nguồn.
    'unavailable' / 'counter_reset' là cơ chế CHƯA BIẾT -> phải điều tra,
        và chính chúng mới có thể gây MNAR.
    """
    recs = []
    for profile, g in df.groupby('profile', sort=False):
        for vcol in valid_columns(df):
            rcol = vcol.replace('qdiscValid', 'qdiscReason')
            if rcol not in g.columns:
                continue
            bad = g[vcol].astype('object').eq(False)
            for reason, cnt in g.loc[bad, rcol].value_counts().items():
                recs.append({'profile': str(profile),
                             'link': vcol.split('.')[0],
                             'reason': str(reason), 'count': int(cnt)})
    if not recs:
        return pd.DataFrame(columns=['profile', 'link', 'reason', 'count'])
    return pd.DataFrame(recs)


def missing_by_tick_position(df: pd.DataFrame, n_head: int = 1) -> dict:
    """Thiếu tập trung ở ĐẦU run hay rải khắp run?

    Vị trí đầu run là một bằng chứng; cần đối chiếu cờ và lý do từng ô.
    Vị trí tự nó không xác định được cơ chế missingness.
    """
    loss = loss_columns(df)
    out = {}
    for profile, g in df.groupby('profile', sort=False):
        bad_ticks = sorted(int(t) for t in g.loc[g[loss].isna().any(axis=1), 'tick'])
        out[str(profile)] = {
            'bad_ticks': bad_ticks,
            'all_within_head': bool(all(t < n_head for t in bad_ticks)),
            'n_head': n_head,
        }
    return out


def mnar_evidence(df: pd.DataFrame) -> dict:
    """Bằng chứng về cơ chế thiếu: MCAR / MAR / MNAR.

    HAI LOẠI BẰNG CHỨNG, và loại thứ hai MẠNH HƠN:
      1. Tương quan: tỉ lệ thiếu ở fault vs normal (Fisher exact + Wilson CI)
      2. Cơ chế: mọi mẫu thiếu có giải thích tiền định không (warmup ở tick 0)

    Biết CƠ CHẾ mạnh hơn mọi test tương quan. Test tương quan trên n nhỏ có
    công suất (power) thấp -> "p = 1.0" KHÔNG chứng minh không có MNAR.
    """
    loss = loss_columns(df)
    cells = df[loss]
    fault = df['is_fault'].astype(bool)
    a = int(cells[fault].isna().to_numpy().sum())
    b = int(cells[fault].notna().to_numpy().sum())
    c = int(cells[~fault].isna().to_numpy().sum())
    d = int(cells[~fault].notna().to_numpy().sum())
    p = fisher_exact_two_sided(a, b, c, d) if (a + b) and (c + d) else float('nan')

    # KHỬ NHIỄU GÂY LẪN (confounder): thiếu tập trung ở đầu run, nên run NGẮN
    # có tỉ lệ thiếu CAO hơn chỉ vì 1 tick warmup chiếm phần lớn hơn. Nếu không
    # khử, "fault thiếu nhiều hơn normal" là ảo giác do độ dài run, không phải
    # MNAR. So lại sau khi bỏ warmup.
    post = df.loc[df.groupby('run_id')['tick'].transform('min') != df['tick']]
    pc = post[loss]
    pf = post['is_fault'].astype(bool)
    pa = int(pc[pf].isna().to_numpy().sum())
    pb = int(pc[pf].notna().to_numpy().sum())
    pcc = int(pc[~pf].isna().to_numpy().sum())
    pd_ = int(pc[~pf].notna().to_numpy().sum())

    pos = missing_by_tick_position(df)
    reasons = missing_reasons(df)
    accounted = 0
    observed_reasons = set()
    for lcol in loss:
        missing = df[lcol].isna()
        vcol = lcol.replace('lossPct', 'qdiscValid')
        rcol = lcol.replace('lossPct', 'qdiscReason')
        if vcol not in df or rcol not in df:
            continue
        observed_reasons.update(str(x) for x in df.loc[missing, rcol].dropna().unique())
        accounted += int((missing & df[vcol].eq(False) & df[rcol].eq('warmup')).sum())
    complete = accounted == a + c and a + c > 0
    only_warmup = bool(complete and len(reasons) and
                       set(reasons.reason.unique()) <= set(WARMUP_REASONS))
    all_head = all(v['all_within_head'] for v in pos.values())
    return {
        'table_fault_missing_vs_present': [[a, b], [c, d]],
        'pct_missing_fault': round(100 * a / (a + b), 3) if a + b else None,
        'pct_missing_normal': round(100 * c / (c + d), 3) if c + d else None,
        'ci95_fault_pct': [round(100 * x, 3) for x in wilson_ci(a, a + b)],
        'ci95_normal_pct': [round(100 * x, 3) for x in wilson_ci(c, c + d)],
        'fisher_p_two_sided': round(p, 6) if np.isfinite(p) else None,
        'note_confounder': ('tỉ lệ thô bị LẪN bởi độ dài run: thiếu dồn ở đầu run '
                            'nên run ngắn có tỉ lệ cao hơn. Xem khối post_warmup.'),
        'post_warmup': {
            'table_fault_missing_vs_present': [[pa, pb], [pcc, pd_]],
            'pct_missing_fault': round(100 * pa / (pa + pb), 3) if pa + pb else None,
            'pct_missing_normal': round(100 * pcc / (pcc + pd_), 3) if pcc + pd_ else None,
            'ci95_fault_pct': [round(100 * x, 3) for x in wilson_ci(pa, pa + pb)],
            'ci95_normal_pct': [round(100 * x, 3) for x in wilson_ci(pcc, pcc + pd_)],
        },
        'reasons_seen': sorted(observed_reasons | (set(reasons.reason.unique()) if len(reasons) else set())),
        'all_missing_cells_accounted_for': complete,
        'missing_cells_with_warmup_flag': accounted,
        'statistical_unit_caveat': 'Wilson/Fisher cell results assume independent samples; links share warmup and ticks are serially dependent. Descriptive only, not calibrated inference for this pilot.',
        'only_structural_warmup': only_warmup,
        'all_missing_in_run_head': all_head,
        'mechanism_identified': bool(only_warmup and all_head),
        'conclusion': ('MAR cho warmup quan sát được — mọi ô thiếu có cờ/lý do warmup ở tick 0; không kết luận cơ chế tổng quát'
                       if (only_warmup and all_head) else
                       'CHƯA KẾT LUẬN — có lý do ngoài warmup, phải điều tra'),
        'power_caveat': ('Fisher p lớn KHÔNG chứng minh không có MNAR. Với pilot '
                         'chỉ có warmup, phép test gần như không có công suất. '
                         'PHẢI chạy lại sau Lesson 5.4 với fault mạnh hơn.'),
    }


# ------------------------------------------ kênh B: rate bị bịa số 0
def rate_fabrication_audit(df: pd.DataFrame) -> dict:
    """Dùng bộ đếm cộng dồn (đã LOẠI khỏi feature) làm công cụ kiểm toán.

    Bịa số 0 = báo rate == 0 nhưng bộ đếm cộng dồn THẬT có tăng.
    Chỉ làm được cho host, vì snapshot chỉ phơi rxBytes/txBytes ở host.
    Link không có bộ đếm cộng dồn trong snapshot -> KHÔNG kiểm toán được,
    và đó là lý do phải vá collector chứ không thể chỉ kiểm toán downstream.
    """
    hosts = sorted({c.split('.')[0] for c in df.columns
                    if c.startswith('host-') and c.endswith('.traffic.rxBytes')})
    findings = []
    for run_id, g in df.groupby('run_id', sort=False):
        profile = g['profile'].iloc[0]
        g = g.sort_values('tick').reset_index(drop=True)
        for h in hosts:
            for side in ('rx', 'tx'):
                cnt_col, rate_col = f'{h}.traffic.{side}Bytes', f'{h}.traffic.{side}Rate'
                if cnt_col not in g or rate_col not in g:
                    continue
                delta = g[cnt_col].diff()
                first = g.index[0]
                if g.loc[first, rate_col] == 0.0:
                    findings.append({'profile': str(profile), 'run_id': str(run_id), 'thing': h,
                                     'field': f'{side}Rate',
                                     'tick': int(g.loc[first, 'tick']),
                                     'kind': 'warmup_no_prev'})
                mid = (g[rate_col] == 0.0) & (delta > 0)
                for i in g.index[mid]:
                    findings.append({'profile': str(profile), 'run_id': str(run_id), 'thing': h,
                                     'field': f'{side}Rate',
                                     'tick': int(g.loc[i, 'tick']),
                                     'kind': 'zero_but_counter_advanced',
                                     'counter_delta': float(delta[i])})
    kinds = {}
    for f in findings:
        kinds[f['kind']] = kinds.get(f['kind'], 0) + 1
    return {
        'n_findings': len(findings),
        'by_kind': kinds,
        'findings': findings[:40],
        'auditable_things': hosts,
        'limitation': ('link-*.traffic.rxRate/txRate KHÔNG kiểm toán được: '
                       'snapshot không phơi bộ đếm cộng dồn của link. '
                       'Đã vá bằng cờ rateValid trong collector.'),
    }


# ------------------------------------------------------- chính sách bỏ mẫu
def apply_policy(df: pd.DataFrame, warmup_ticks: int = 1,
                 feature_cols: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Chính sách DT4N-M1. Ba tầng, và mỗi tầng PHẢI có bản đối ứng inference.

      Tầng 1 (CẤU TRÚC, tiền định): bỏ `warmup_ticks` tick đầu MỖI run.
          Đối ứng Phase 7: detector không phát trong N tick đầu và ghi
          status="warming_up" lên twin, thay vì im lặng.

      Tầng 2 (SÓT LẠI, sau warmup): KHÔNG bỏ dòng. Giữ NaN + cột đếm
          `n_loss_missing` làm missing indicator.
          Vì sao không bỏ: Phase 7 phải ra quyết định MỖI tick — không có
          quyền "bỏ tick". Train bỏ mà inference không bỏ được =
          training-serving skew: mô hình chưa từng thấy loại dòng nó sẽ gặp.

      Tầng 3 (CHỈ LÚC TRAIN): dòng còn NaN ở feature train thì bỏ, vì
          IsolationForest không nhận NaN. Nhưng bỏ ở ĐÂY, CÓ ĐẾM, chứ không
          bỏ âm thầm ở tầng đọc dữ liệu.
          Đối ứng Phase 7: detector TỪ CHỐI phán quyết —
          anomalyStatus="unknown" + reason + detectedAt, KHÔNG ghi "normal".

    TUYỆT ĐỐI không fillna(0) ở bất kỳ tầng nào.
    """
    if not isinstance(warmup_ticks, int) or warmup_ticks < 0:
        raise ValueError('warmup_ticks phải là số nguyên không âm')
    if df.run_id.isna().any() or df.tick.isna().any() or df.duplicated(['run_id', 'tick']).any():
        raise ValueError('run_id/tick phải đầy đủ và duy nhất trong run')
    assert_no_fabricated_zero_in_loss(df)
    df, rate_report = mask_invalid_rates(df)
    loss = loss_columns(df)
    out = df.copy()
    out['n_loss_missing'] = out[loss].isna().sum(axis=1).astype('int16')
    rate_cols = [c for c in out if c.endswith(('.traffic.rxRate', '.traffic.txRate'))]
    out['n_rate_missing'] = out[rate_cols].isna().sum(axis=1).astype('int16')
    out['is_warmup'] = out.groupby('run_id')['tick'].transform(
        lambda s: s.rank(method='first') <= warmup_ticks)

    n_before = len(out)
    kept = out.loc[~out['is_warmup']].copy()
    report = {
        'policy': 'DT4N-M1',
        'invalid_rate_mask': rate_report,
        'warmup_ticks': warmup_ticks,
        'rows_before': n_before,
        'rows_dropped_warmup': int(n_before - len(kept)),
        'rows_after_warmup_drop': int(len(kept)),
        'rows_with_residual_missing': int((kept['n_loss_missing'] > 0).sum()),
        'cells_missing_after': int(kept[loss].isna().to_numpy().sum()),
        'rule_text': ('bỏ tick đầu mỗi run (warmup, tiền định); giữ mọi dòng '
                      'còn lại kèm n_loss_missing; không bao giờ fillna(0)'),
    }
    if feature_cols is not None:
        absent = [c for c in feature_cols if c not in kept.columns]
        report['absent_feature_columns'] = absent
        features = kept.reindex(columns=feature_cols).apply(pd.to_numeric, errors='coerce').replace([np.inf, -np.inf], np.nan)
        trainable = kept.loc[features.notna().all(axis=1)]
        report['rows_dropped_train_nan'] = int(len(kept) - len(trainable))
        report['rows_trainable'] = int(len(trainable))
    return kept, report


def mask_invalid_rates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Đổi rate BỊA thành NaN, dựa trên cờ `rateValid` mới của collector.

    Vì sao việc này ở ĐÂY mà không ở `flatten.py`: flatten là phép DỊCH
    (JSON -> bảng), phải trung thực tuyệt đối với file. Che giá trị là một
    CHÍNH SÁCH. Trộn hai thứ thì sau này không biết NaN đến từ file hay từ
    quyết định của mình.

    Vì sao không sửa `rxRate` thành null ngay trong collector: dashboard và
    mọi artifact đã nghiệm thu đang đọc `rxRate` là số. Đổi kiểu = phá hợp
    đồng đã chứng minh. Thêm cờ rồi che ở tầng ML = có sự thật mà không phá
    gì. Đây là một đánh đổi kỹ thuật, và nó phải được ghi vào báo cáo.
    """
    out = df.copy()
    masked = {}
    for vcol in (c for c in df.columns if c.endswith('.rateValid')):
        thing = vcol[:-len('.rateValid')]          # vd 'link-h1-s1.traffic'
        invalid = ~out[vcol].eq(True).fillna(False)
        for side in ('rxRate', 'txRate'):
            rcol = f'{thing}.{side}'
            if rcol in out.columns:
                out[rcol] = pd.to_numeric(out[rcol], errors='coerce').astype(float)
                n = int((invalid & out[rcol].notna()).sum())
                if n:
                    out.loc[invalid, rcol] = np.nan
                    masked[rcol] = n
    return out, {'n_columns_masked': len(masked), 'cells_masked': masked,
                 'total_cells_masked': int(sum(masked.values()))}


def assert_no_fabricated_zero_in_loss(df: pd.DataFrame) -> None:
    """Bất biến phải đúng ở MỌI tầng: qdiscValid=False thì lossPct PHẢI là NaN.

    Nếu ai đó thêm fillna(0), hàm này nổ. Đây là cách biến lời khuyên
    'đừng fillna' thành cơ chế.
    """
    for vcol in valid_columns(df):
        lcol = vcol.replace('qdiscValid', 'lossPct')
        if lcol not in df.columns:
            continue
        invalid = df[vcol].astype('object').eq(False)
        if invalid.any() and df.loc[invalid, lcol].notna().any():
            offending = df.loc[invalid & df[lcol].notna(), [c for c in ('tick', lcol) if c in df]]
            raise AssertionError(
                f'{lcol} có giá trị ở nơi {vcol} là False -> đã bị bịa số:\n{offending}')
