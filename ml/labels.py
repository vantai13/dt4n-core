#!/usr/bin/env python3
"""Lesson 5.5 — NHÃN GROUND TRUTH: nguồn chân lý DUY NHẤT về "tick nào có sự cố".

VÌ SAO FILE NÀY TỒN TẠI VÀ VÌ SAO KHÔNG ĐỂ Ở ml/campaign.py:
    ml/campaign.py là logic của CHIẾN DỊCH THU: quarantine, resume, manifest,
    gate chấp nhận. Phase 6 không cần biết gì về những thứ đó — nó cần đúng
    một câu trả lời: "tick này có sự cố không?".

    Nếu nhãn tiếp tục sống trong campaign.py, mọi consumer phải import cả bộ
    máy thu. Và rồi sẽ có ngày ai đó (kể cả bạn, ba tuần sau) viết lại một
    vòng `for t in range(21, 41)` ở chỗ khác cho tiện. Từ đó repo có HAI định
    nghĩa nhãn, và lúc số liệu lệch thì không ai biết bên nào đúng.

    Một khái niệm -> một chỗ định nghĩa -> một test ghim.

BA MẢNG, BA Ý NGHĨA KHÁC NHAU — KHÔNG ĐƯỢC TRỘN:
    y[t]                : nhãn can thiệp theo tick (không phải phép đo trạng thái vật lý liên tục)
    eval_primary[t]      : tick t có vào chỉ số CHÍNH không. <- chỉ loại warmup
    eval_sensitivity[t]  : tick t có vào phân tích ĐỘ NHẠY.  <- loại thêm chuyển tiếp

    Nhồi grace vào y là nói "lỗi không tồn tại ở tick 21", trong khi sự thật
    là "lỗi tồn tại nhưng ta chưa đo được hậu quả". Đó ĐÚNG là kiểu nhầm lẫn
    mà cả Phase 5 sinh ra để chống: nhầm "không đo được" với "không có".
    Xem docs/phase-5/02-missing-data.md — cùng một nguyên tắc.

STDLIB-ONLY — CÓ LÝ DO:
    runner chạy dưới `sudo /usr/bin/python3`, không có numpy/pandas. Giữ file
    này thuần thư viện chuẩn để CẢ runner VÀ pipeline train đều dùng được
    CÙNG MỘT định nghĩa. Helper cần pandas import lazy ở cuối file.
"""
from __future__ import annotations

# --- hằng số mặt nạ: đặt tên để không ai nhầm với giá trị nhãn -------------
# Bẫy đã tránh: nếu cả nhãn và mặt nạ đều là 0/1 trần, một ngày nào đó bạn sẽ
# truyền nhầm mặt nạ vào chỗ nhận nhãn và không có gì báo lỗi.
EVAL = 1        # tick ĐƯỢC tính vào chỉ số
IGNORE = 0      # tick bị LOẠI khỏi chỉ số — KHÁC hẳn "nhãn 0"

# --- dải chuyển tiếp: GIÁ TRỊ ĐỀ XUẤT, phải được verify_labels.py biện minh -
# Không phải hằng số thần thánh. scripts/verify_labels.py ĐO onset delay thật
# trên 8 run fault; nếu có run nào vượt con số này, gate sẽ FAIL và bạn phải
# xem lại — chứ không âm thầm dùng một tham số không ai kiểm chứng.
GRACE_ONSET_TICKS = 10      # sau inject: mạng cần thời gian để hậu quả lộ ra
GRACE_RECOVERY_TICKS = 2   # sau revert: TCP slow-start lại, hàng đợi rút

# --- chuỗi ĐÃ ĐÓNG DẤU vào 18 sidecar lúc thu (Lesson 5.4). BẤT BIẾN. ------
# KHÔNG sửa, KHÔNG xóa. Sửa nó = làm 18 sidecar trên đĩa nói khác code, tức
# là tự phá bằng chứng của lesson trước. test/test_ml_labels.py ghim đẳng
# thức "công thức y của DT4N-L1 == công thức mô tả trong chuỗi này".
LABEL_CONVENTION_COLLECTED = (
    'point-wise; label[t]=1 iff inject_tick < t <= revert_tick; grace=2 ticks')

# --- quy ước được PHÊ CHUẨN ở Lesson 5.5 ----------------------------------
LABEL_CONVENTION_ID = 'DT4N-L1'
LABEL_CONVENTION = (
    'DT4N-L1 | intervention y[t]=1 iff inject_tick < t <= revert_tick; '
    'collector monotonic event/snapshot anchors; actuation may cross measurement boundaries. '
    'Primary: strict point-wise after warmup only. '
    'Sensitivity: exclude onset=%d, recovery=%d ticks; grace never changes y. '
    'No point-adjust for primary evaluation.'
) % (GRACE_ONSET_TICKS, GRACE_RECOVERY_TICKS)


# =========================================================================
# 1. ĐỌC SỰ KIỆN — kiểm tra chặt, vì mọi thứ sau đó dựa vào đây
# =========================================================================
def event_ticks(n_snapshots, events):
    """Trả (inject_tick, revert_tick), hoặc None nếu run này không có sự cố.

    VÌ SAO KIỂM TRA GẮT ĐẾN THẾ: nếu events hỏng mà hàm này trả về một cái gì
    "tạm được", toàn bộ nhãn sai và Phase 6 sẽ báo một con số recall sai mà
    không có gì bất thường. Thà nổ ở đây còn hơn sai ở đó.

    `isinstance(x, bool)` phải loại riêng: trong Python, True là int (True == 1).
    Không loại thì events={'tick': True} lọt qua và thành tick 1.
    """
    if not isinstance(n_snapshots, int) or isinstance(n_snapshots, bool) or n_snapshots < 0:
        raise ValueError('n_snapshots phai la so nguyen khong am, nhan %r' % (n_snapshots,))
    if events is None or events == []:
        return None                      # run normal: hợp lệ, không có sự kiện
    if not isinstance(events, (list, tuple)) or not all(isinstance(e, dict) for e in events):
        raise ValueError('events must be a sequence of mappings')
    kinds = [e.get('kind') for e in events]
    if len(events) != 2 or kinds != ['inject', 'revert']:
        raise ValueError(
            'nhan can DUNG 2 su kien theo thu tu [inject, revert]; nhan %r' % (kinds,))
    inject, revert = (e.get('tick') for e in events)
    for name, t in (('inject', inject), ('revert', revert)):
        if not isinstance(t, int) or isinstance(t, bool):
            raise ValueError('tick cua %s phai la int, nhan %r' % (name, t))
    if not 0 <= inject < revert < n_snapshots:
        raise ValueError('tick su kien ngoai day snapshot: inject=%d revert=%d n=%d'
                         % (inject, revert, n_snapshots))
    return inject, revert


# =========================================================================
# 2. NHÃN y — sự thật vật lý, không pha quy ước đánh giá
# =========================================================================
def labels_from_events(n_snapshots, events):
    """y[t] in {0,1}. Công thức suy ra từ ngữ nghĩa cửa sổ đo, không phải chọn bừa.

    DẪN DẮT (viết ra để 3 tuần sau không phải suy lại):
        bridge/collector.py: rate[t] = (counter[t] - counter[t-1]) / dt
            -> rate[t] mô tả KHOẢNG (t-1, t], không phải THỜI ĐIỂM t.
        scripts/generate_ml_dataset.py: inject nằm trong on_tick, mà collector
        gọi on_tick SAU khi đã logf.write + flush snapshot tick n.
            -> snapshot[inject_tick] là trạng thái TRƯỚC sự cố  -> y=0
            -> tick tiếp theo được gán nhãn can thiệp -> y=1
            -> khoảng (revert_tick-1, revert_tick] vẫn dưới fault      -> y=1
            -> khoảng (revert_tick, revert_tick+1] đã revert           -> y=0
        => y[t] = 1 <=> inject_tick < t <= revert_tick

    NẾU BẠN ĐỔI COLLECTOR sang cửa sổ tương lai [t, t+1), công thức này PHẢI
    đổi thành inject_tick <= t < revert_tick. Nên test_ml_labels.py có một
    test ghim ngữ nghĩa cửa sổ để buộc bạn nhớ.
    """
    window = event_ticks(n_snapshots, events)
    labels = [0] * n_snapshots
    if window is None:
        return labels
    inject, revert = window
    for tick in range(inject + 1, revert + 1):
        labels[tick] = 1
    return labels


# =========================================================================
# 3. MẶT NẠ ĐÁNH GIÁ — quy ước của người đánh giá, KHÔNG phải sự thật
# =========================================================================
def warmup_mask(n_snapshots, warmup_ticks):
    """IGNORE các tick warmup. KHÔNG phải quy ước — là lọc CẤU TRÚC.

    Tick 0 không có mẫu trước nên rate=0 và rateValid=False. Nó không mang
    thông tin mạng. Luật này đã chốt ở Lesson 5.2 (DT4N-M1 tầng 1) và có bản
    đối ứng ở Phase 7 (detector ghi status="warming_up", không im lặng).
    """
    event_ticks(n_snapshots, None)
    if not isinstance(warmup_ticks, int) or isinstance(warmup_ticks, bool) or warmup_ticks < 0:
        raise ValueError('warmup_ticks phai la so nguyen khong am')
    return [IGNORE if t < warmup_ticks else EVAL for t in range(n_snapshots)]


def transition_mask(n_snapshots, events,
                    onset=GRACE_ONSET_TICKS, recovery=GRACE_RECOVERY_TICKS):
    """IGNORE dải chuyển tiếp hai đầu sự cố. ĐÂY LÀ QUY ƯỚC, KHÔNG PHẢI NHÃN.

    Vì sao cần, và vì sao ĐỐI XỨNG:

      onset (sau inject): mạng cần thời gian để hậu quả lộ ra ở đại lượng ta
          đo. tc hạ băng thông -> hàng đợi phải ĐẦY mới drop; TCP cần 1-3 RTT
          để nhận ra mất gói và giảm cửa sổ. Nhãn đúng là 1 (lỗi tồn tại),
          nhưng đòi mô hình bắt được ở đây là không công bằng.

      recovery (sau revert): link đã lành nhưng TCP đang slow-start lại và
          hàng đợi đang rút. Nhãn đúng là 0, nhưng dữ liệu vẫn trông bất
          thường -> mô hình bị tính false positive cho một transient mà nó
          không gây ra. Hầu hết đồ án bỏ sót đầu này. Bỏ sót nó làm FPR bị
          báo cao hơn thực tế -> tự làm xấu kết quả của mình.

    LƯU Ý KHI DÙNG: mặt nạ này CHỈ dùng cho chỉ số PHỤ. Chỉ số CHÍNH không
    loại tick nào ngoài warmup. Lý do: mọi tham số loại trừ là một chỗ để bị
    chê "chọn quy ước có lợi". Báo CẢ HAI thì khoảng cách giữa chúng chính là
    nội dung khoa học, không phải chỗ để nghi ngờ.
    """
    for name, g in (('onset', onset), ('recovery', recovery)):
        if not isinstance(g, int) or isinstance(g, bool) or g < 0:
            raise ValueError('grace %s phai la so nguyen khong am, nhan %r' % (name, g))
    window = event_ticks(n_snapshots, events)
    mask = [EVAL] * n_snapshots
    if window is None:
        return mask                      # run normal: không có chuyển tiếp
    inject, revert = window
    for t in range(inject + 1, min(inject + 1 + onset, n_snapshots)):
        mask[t] = IGNORE
    for t in range(revert + 1, min(revert + 1 + recovery, n_snapshots)):
        mask[t] = IGNORE
    return mask


# =========================================================================
# 4. BẢNG NHÃN MỘT RUN — artifact để đọc, kiểm chứng, và trích vào báo cáo
# =========================================================================
def label_table(run_id, n_snapshots, events, warmup_ticks,
                split=None, group=None, fault=None, fault_target=None,
                seed=None, max_separation=None):
    """Gói mọi thứ Phase 6 cần biết về nhãn của MỘT run.

    `max_separation` được mang sang từ sidecar checks CÓ Ý: nó là BIẾN ĐỒNG
    HÀNH (covariate) cho phân tích lỗi ở Phase 6. Nhãn của ta là intervention
    label — "tôi đã gây lỗi" — không bảo đảm lỗi gây hậu quả ĐO ĐƯỢC. Một run
    degrade separation 11.5 và một run admin_down separation 100 có cùng nhãn
    nhưng độ khó khác nhau một trời một vực. Không mang số này sang thì Phase 6
    chỉ báo được "recall 78%" thay vì giải thích ĐƯỢC 78% đó đến từ đâu.
    """
    y = labels_from_events(n_snapshots, events)
    wm = warmup_mask(n_snapshots, warmup_ticks)
    tm = transition_mask(n_snapshots, events)
    eval_primary = list(wm)                                   # chỉ loại warmup
    eval_sensitivity = [a & b for a, b in zip(wm, tm)]        # loại thêm chuyển tiếp
    window = event_ticks(n_snapshots, events)

    def _count(mask, value):
        return sum(1 for m, lab in zip(mask, y) if m == EVAL and lab == value)

    return {
        'run_id': run_id, 'split': split, 'group': group,
        'fault': fault, 'fault_target': fault_target, 'seed': seed,
        'max_separation': max_separation,
        'convention_id': LABEL_CONVENTION_ID,
        'n_snapshots': n_snapshots, 'warmup_ticks': warmup_ticks,
        'inject_tick': window[0] if window else None,
        'revert_tick': window[1] if window else None,
        'grace_onset_ticks': GRACE_ONSET_TICKS,
        'grace_recovery_ticks': GRACE_RECOVERY_TICKS,
        'ticks': list(range(n_snapshots)),
        'y': y,
        'eval_primary': eval_primary,
        'eval_sensitivity': eval_sensitivity,
        'counts': {
            'primary_fault_ticks': _count(eval_primary, 1),
            'primary_normal_ticks': _count(eval_primary, 0),
            'sensitivity_fault_ticks': _count(eval_sensitivity, 1),
            'sensitivity_normal_ticks': _count(eval_sensitivity, 0),
            'ticks_dropped_warmup': n_snapshots - sum(wm),
            'ticks_dropped_transition': sum(wm) - sum(eval_sensitivity),
        },
    }


# =========================================================================
# 5. BASE RATE — tổng, VÀ theo từng loại fault
# =========================================================================
def base_rate(tables, mask_key='eval_primary', splits=('test',)):
    """Base rate trên các run thuộc `splits`, theo mặt nạ `mask_key`.

    VÌ SAO TÁCH THEO LOẠI FAULT: Phase 6 sẽ có recall tổng, nhưng con số đó
    che mất điều thú vị nhất. Nếu recall 100% trên admin_down (separation 100)
    và 45% trên degrade (separation 11.5), thì gộp lại thành "78%" là làm mất
    kết luận. Mẫu số theo từng loại phải có sẵn từ Phase 5, không tính sau.

    CẢNH BÁO: base rate được thiết kế, không phải tần suất mạng thật.

    Ví dụ giả định khi giữ TPR/FPR cố định: base rate ~27% là DO THIẾT KẾ
    (8/10 run test có fault). Nếu base rate giả định ~0.1%, precision thay đổi; không suy ra
    chặn trên thực nghiệm. Domain shift có thể đổi recall/FPR -> dùng các chỉ số
    đó để so sánh. Đây là base rate fallacy.
    """
    if mask_key not in ('eval_primary', 'eval_sensitivity'):
        raise ValueError('mask_key phai la eval_primary hoac eval_sensitivity')
    tables = list(tables)
    _validate_tables(tables)
    usable = anomalous = 0
    by_fault: dict = {}
    per_run: dict = {}
    for tb in tables:
        if splits is not None and tb.get('split') not in splits:
            continue
        run_usable = run_anom = 0
        for lab, m in zip(tb['y'], tb[mask_key]):
            if m != EVAL:
                continue
            run_usable += 1
            run_anom += lab
        usable += run_usable
        anomalous += run_anom
        key = tb.get('fault') or 'none'
        slot = by_fault.setdefault(key, {'usable': 0, 'anomalous': 0, 'runs': []})
        slot['usable'] += run_usable
        slot['anomalous'] += run_anom
        slot['runs'].append(tb['run_id'])
        per_run[tb['run_id']] = {
            'usable_ticks': run_usable, 'anomalous_ticks': run_anom,
            'max_separation': tb.get('max_separation')}
    for slot in by_fault.values():
        slot['base_rate'] = (round(slot['anomalous'] / slot['usable'], 4)
                             if slot['usable'] else None)
    return {
        'mask': mask_key,
        'splits': list(splits) if splits is not None else None,
        'usable_test_ticks': usable,
        'anomalous_test_ticks': anomalous,
        'base_rate_measured': round(anomalous / usable, 4) if usable else None,
        'dumb_always_normal_accuracy': (round(1 - anomalous / usable, 4)
                                        if usable else None),
        'by_fault': by_fault,
        'per_run': per_run,
    }


# =========================================================================
# 6. GHÉP NHÃN VÀO DataFrame — theo KHÓA, tuyệt đối không theo thứ tự dòng
# =========================================================================
def attach_labels(df, tables):
    """Gắn is_fault / eval_primary / eval_sensitivity vào df theo (run_id, tick).

    VÌ SAO KHÔNG `df['is_fault'] = labels_from_events(len(df), events)`:
        Gán theo VỊ TRÍ chỉ đúng khi df có đúng n dòng, đúng thứ tự tick
        0..n-1, và đúng một run. Ba giả định. Ngày nào một cái vỡ — warmup đã
        bị lọc, groupby đã sắp lại, concat đã gộp nhiều run — nhãn dịch đi và
        PANDAS KHÔNG BÁO GÌ. Bạn được một con số recall sai mà trông hoàn toàn
        bình thường.

        Ghép theo KHÓA + validate='one_to_one' biến lỗi im lặng thành lỗi ồn ào.
        Đây là bài học chung cho cả sự nghiệp: ghép bảng bằng khóa, không bao
        giờ bằng vị trí, và luôn bật validate.

    pandas import LAZY để ml/labels.py vẫn nạp được dưới sudo python hệ thống.
    """
    import pandas as pd
    from numbers import Integral
    tables = list(tables)
    _validate_tables(tables)
    if set(df.columns) & {"is_fault", "eval_primary", "eval_sensitivity"}:
        raise ValueError("label columns already exist")

    if 'run_id' not in df.columns or 'tick' not in df.columns:
        raise ValueError('df phai co ca run_id va tick de ghep nhan')
    if df[['run_id', 'tick']].isna().any().any():
        raise ValueError('run_id/tick khong duoc co NaN')
    if not all(isinstance(t, Integral) and not isinstance(t, bool) and t >= 0 for t in df['tick']):
        raise ValueError('tick keys must be nonnegative integers')
    if not all(isinstance(x, str) and x for x in df['run_id']):
        raise ValueError('run_id keys must be nonempty strings')
    if df.duplicated(['run_id', 'tick']).any():
        raise ValueError('(run_id, tick) phai duy nhat truoc khi ghep nhan')

    rows = [{'run_id': tb['run_id'], 'tick': t, 'is_fault': lab,
             'eval_primary': mp, 'eval_sensitivity': ms}
            for tb in tables
            for t, lab, mp, ms in zip(tb['ticks'], tb['y'],
                                      tb['eval_primary'], tb['eval_sensitivity'])]
    if not rows:
        raise ValueError('khong co bang nhan nao de ghep')
    labels = pd.DataFrame(rows)

    have = set(map(tuple, labels[['run_id', 'tick']].to_numpy()))
    want = set(map(tuple, df[['run_id', 'tick']].to_numpy()))
    missing = want - have
    if missing:
        raise ValueError('thieu nhan cho %d (run_id, tick); vi du: %r'
                         % (len(missing), sorted(missing)[:3]))

    n_before = len(df)
    out = df.merge(labels, on=['run_id', 'tick'], how='left', validate='one_to_one')
    if len(out) != n_before:
        raise ValueError('merge lam doi so dong: %d -> %d' % (n_before, len(out)))
    if out[['is_fault', 'eval_primary', 'eval_sensitivity']].isna().any().any():
        raise ValueError('con NaN sau merge — nhan khong phu het du lieu')
    out['is_fault'] = out['is_fault'].astype('int8')
    out['eval_primary'] = out['eval_primary'].astype('int8')
    out['eval_sensitivity'] = out['eval_sensitivity'].astype('int8')
    return out


def _validate_tables(tables):
    seen = set()
    for tb in tables:
        rid = tb['run_id']
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError('invalid or duplicate run_id')
        seen.add(rid)
        n = tb['n_snapshots']
        event_ticks(n, None)
        if tb['ticks'] != list(range(n)):
            raise ValueError('table ticks must match snapshot sequence')
        for key in ('y', 'eval_primary', 'eval_sensitivity'):
            if len(tb[key]) != n or any(type(x) is not int or x not in (0, 1) for x in tb[key]):
                raise ValueError('invalid label/mask shape or value: ' + key)
