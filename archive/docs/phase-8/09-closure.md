# Phase 8.9 — Hồ sơ đóng và quyết định phát hành

Phase 8.9 không đạt điều kiện bật vòng kín tự động. Nghiệm thu chặt hơn trả
`C1 = FAIL` và `acceptance_pass = false`; cấu hình phù hợp với bằng chứng hiện
có là **đề xuất hành động, con người duyệt**, không phải tự động tác động.

## 1. Ba phát hiện khi đóng

1. Policy cũ chỉ fail-closed một tick sau `probe_target_changed`; recovery
   burst ở tick kế có thể bị re-latch như thủ phạm mới. Điều này lệch quy tắc
   LATCH của prereg 8.1.
2. Evaluator C1 cũ chỉ kiểm `n_inject > 0`, không kiểm link được nhắm có đúng
   thủ phạm hay không.
3. Audit gốc nằm ngoài Git, nên verdict không thể kiểm độc lập trên clone sạch.

Audit hồi cứu 145 file/408 inject không thấy target sai và không thấy
`probe_target_changed`; lỗi A2 vì vậy là lỗi tiềm ẩn, được tìm bằng đọc code,
không phải bằng chọn số live (`phase8_target_audit.json`).

## 2. Amendment A2

Sau `probe_target_changed`, policy về `IDLE` và cách ly đúng `probe_w_s = 14 s`,
tái dùng `window_end_mono`. Trong cách ly, controller chỉ trả về rỗng; bản vá
thu hẹp tập trạng thái có thể phát lệnh và không thể tạo hành động mới.

Test mới cho thấy policy cũ fail 2/4 và inject nhầm `h3-s1`; policy A2 pass 4/4.
Replay soak cũ đạt **2101/2101**, replay C3 đạt **567/567** quyết định bit-exact;
mô phỏng 2.000 seed cũ/mới trùng hoàn toàn. C10-v3 trên audit mới đạt
**1803/1803** (`phase8_c10_v3.json`).

## 3. E1 — C1 có đối chứng

E1 chạy 20 trial, 0 aborted, kết quả prereg **KN3**:

| Kịch bản | Đúng | Sai mục tiêu | Im lặng |
|---|---:|---:|---:|
| h3 → srv1, culprit h3 | 1 | 4 | 0 |
| h2 → srv2, culprit h2 | 5 | 0 | 0 |
| h1 → srv2, culprit h1 (out-of-sample) | 1 | 4 | 0 |
| stop-in-probe, culprit h1 | 1 | 4 | 0 |

Tổng cộng **12 wrong-target**; các lượt sai đều inject `h2-s1`. Có 6 lượt đúng
với thủ phạm khác h1, nhưng điều đó không cứu gate vì chỉ cần một wrong-target
là C1 FAIL. Cả 5 stop-in-probe đều có `n_probe_target_changed = 0`: bảo đảm A2
dựa trên unit test tất định; live chưa kích hoạt điều kiện đó.

## 4. E3 — chế độ ức chế

Ba run flood độc lập 600 s đều là `SUPPRESSION`: lần lượt **561, 556, 552**
tick suppressed; không run nào đổi mode giữa chừng. Tải nền vẫn sống
(median proxy 2,154 Mbps; 0 mẫu dưới 1 Mbps). Trên n=3, cả H0-OUTLIER,
H-FEEDBACK và H-BISTABLE như prereg đều không phù hợp. C6-a lặp lại với 14
actions/run, `min_hold` 15–16 s và không vi phạm T0.

C12 phải được đọc theo chế độ: run suppression có blind fraction gần toàn bộ
cửa sổ sự cố; các campaign cũ không suppression không đại diện cho mode này.

## 5. E4 — second flood

Cả **5/5** lượt đều phát hiện, 0 censored. `t_masked_s` là
**[1,54; 1,74; 18,34; 21,95; 24,15]**, median **18,34 s**. Hai lượt nhanh có
1–2 mẫu suppressed; ba lượt chậm có 80–103 mẫu suppressed. Dữ liệu ủng hộ dự
đoán hai cụm latency gắn với suppression, nhưng n=5 chỉ cho kết luận định tính.

## 6. Việc không làm và vì sao

- Không sửa localization/evaluator sau KN3 và không chạy lại E1 để tìm kết quả
  đẹp; đó sẽ vi phạm prereg.
- Không hạ ngưỡng C10; bằng chứng mới đã vượt ngưỡng 1.000 quyết định.
- Không đổi suppression sang theo từng thực thể; đây là thay đổi thiết kế cho
  Phase 9+, cần prereg và đánh giá an toàn riêng.
- Không gắn tag `phase-8-complete` khi gate C1 đang FAIL. Audit vẫn được đóng
  gói tất định tại `results/evidence/phase8/phase8_audits.tar.gz` để người khác
  có thể kiểm lại kết luận.

Receipt nghiệm thu cuối: `results/report/phase8_acceptance.json` — 15 PASS,
1 FAIL, 1 INVALID không-gate, 1 PASS-with-model-correction; 32/32 content SHA
và 15/15 dependency khớp.

## 7. Chẩn đoán hậu kiểm (không đổi verdict)

Receipt: `results/report/phase8_closure_diagnostics.json`.

**D1 — E1 bị ô nhiễm nền.** Sau hai flood h2→srv2 liên tiếp (trial 03, 04),
h2 nằm trong `affected` lúc detector `normal` ở mọi trial còn lại. 12 trial bẩn
trùng 1-1 với 12 wrong-target. Bằng chứng phân biệt **sạch** chỉ gồm trial 00–03
(4/4 đúng, gồm out-of-sample h1→srv2), n = 4. `n_correct_nonh1_culprit = 6`
thổi phồng khả năng phân biệt: 4 lượt h2→srv2 sau trial 04 bị gây nhiễu.

**Cơ chế.** Mơ hồ ở tick act đầu → fail-closed suốt flood (không bảo vệ) →
flood dừng, detector còn `act` do hysteresis, `affected` chỉ còn h2 → policy
định vị lại ở IDLE → phạt người ngoài cuộc. Đây là lần lệch thứ hai khỏi LATCH
của prereg 8.1; A2 chỉ vá đường PROBING.

**D3 — phản thực tế.** Chốt theo episode đúng như prereg chuyển 12/12 wrong
thành im lặng và giữ nguyên 8/8 kết quả đúng. Kết quả này in-sample; im lặng
không đồng nghĩa với bảo vệ.

**Lỗi harness.** `require_clean` kiểm `state == normal`, không kiểm tập
`affected`. Trạng thái `normal` không đồng nghĩa với phiên sạch.

**D2 — chế độ ức chế là thuộc tính của phiên.** Tỷ lệ tick `normal` có
`link-s2-s3` là 100% ở A/B và E1, nhưng chỉ 0–10% ở bốn stability-flood có
552–561 tick suppressed. Các phiên Poisson không suppression cũng có tỷ lệ
99,98–100%. Dữ liệu cho thấy baseline `s2-s3` của phiên quyết định phần lớn
mode. Tương quan với thời lượng luồng nền (H-DURATION) chưa được kiểm và được
chuyển sang Phase 9.

**Vì sao C1 = FAIL vẫn đúng.** Host có bất thường nhẹ kéo dài tồn tại trong
mạng thật; hệ hiện tại có thể phạt chúng khi một sự cố không liên quan kết
thúc. Chẩn đoán này sửa cách hiểu nguyên nhân, không sửa verdict.

Con số test chính thức là worktree sạch: **1782 passed, 11 skipped**. Workspace
có log/dữ liệu cục bộ nên chạy thêm các test phụ thuộc hiện vật và cho
1796 passed, 4 skipped; chỉ con số worktree sạch là thứ clone mới tái lập được.
