# GĐ4 — Sai lệch 1 so với tiêu chí đã ghi (viết trước khi chấm)

Thời điểm: 16/10/2026, khoảng 04:05 UTC, trong lúc thu đợt gd4r.

**Thay đổi.** Theo yêu cầu của chủ nhiệm đề tài, ba run chạy nền R-S (3 × 60 phút) được
để lại, chủ nhiệm sẽ tự thu sau bằng đúng hợp đồng gd4r (cùng máy, cùng launcher). Các run
còn lại được thu trước.

**Cách chấm.** Tiêu chí, ngưỡng và code chấm không đổi. Việc chấm tách hai lần:
- lần 1: S1, S4 (10 run R-D) và S10 (6 run R-N), ngay khi các run này thu xong;
- lần 2: S2 (3 run R-S), sau khi chủ nhiệm thu xong ba run này.
Mỗi run vẫn chỉ được chấm một lần. Lúc chấm lần 1, dữ liệu R-S chưa tồn tại nên không thể
ảnh hưởng tới lần chấm đó. R-C và R-O được thu nhưng không vào S1, S2, S4, S10 (như đã ghi).

**Lần thử bị dừng.** Run `RS-soak2M-s5001-r1` (vị trí 16 trong thứ tự chạy) được dừng ngay
khi bắt đầu bằng tín hiệu TERM. Tệp dở của nó được launcher lưu vào thư mục cách ly với hậu tố
`.attempt-…` ở lần chạy sau; khi thu lại, run này bắt đầu từ đầu.

**Script chấm.** Thêm tùy chọn `--groups` (chỉ chấm khi mọi run của các nhóm được chọn đều
đạt cổng thu) và kiểm cổng lưu lượng máy khách cho từng run. Sau thay đổi, script vẫn tái lập
đúng số 6R (bản 1.0.0 trên 25 run cũ), ở cả chế độ đủ nhóm và chế độ R-D + R-N.
