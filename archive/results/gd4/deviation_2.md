# GĐ4 — Bổ sung cách chấm, chốt TRƯỚC khi đọc dữ liệu gd4r

Thời điểm: 16/10/2026, sau khi thu xong 22 run nhanh của gd4r, trước khi chạy detector trên
bất kỳ run nào của gd4r. Các bổ sung dưới đây đến từ nhận xét của người hướng dẫn đọc Chương 4.
Tiêu chí S1, S2, S4, S10 và code chấm của chúng không đổi.

1. **R-C (4 run flood và dịch nút cổ chai) được chấm, chỉ để mô tả.** Mỗi sự cố: có phát hiện
   hay không và thời gian phát hiện, kênh envelope_only và combined, chế độ with_log như 6R
   (ml.acceptance_metrics.incident). Báo kết quả dù tốt hay xấu. Đây là bằng chứng độc lập
   duy nhất cho các loại sự cố khác giảm băng thông. R-O (2 run) vẫn không chấm.
2. **Tải cao (R-N): báo hai cách.** (a) S10 đúng như đã ghi: trạng thái FSM, chưa áp bộ chặn
   vùng tải. (b) Như khi vận hành: áp bộ chặn vùng tải của bridge/detector_runner.py
   (ml.operating_range.OperatingRangeGuard, ngưỡng 4,3126 Mbps từ phase7_prereg.json; trạng
   thái công bố là "không rõ" khi bộ chặn bật, như bridge/detector_contract.py). Báo số giây
   bộ chặn bật và số giây còn công bố báo động. Số giây bộ chặn bật được báo cho mọi run đã chấm.
3. **Thời gian phát hiện báo bằng mọi giá trị** và trung vị [nhỏ nhất; lớn nhất]. Với n ≤ 11,
   p95 theo hạng gần nhất trùng giá trị lớn nhất; phán quyết S4 vẫn tính như đã ghi, và báo
   cáo gọi đúng là "giá trị lớn nhất".
4. **Cổng lưu lượng máy khách** được kiểm cho cả 22 run đã thu (kể cả R-C, R-O), chỉ báo cáo.
5. **Tập phát triển (đã mở), chỉ mô tả, làm với bản 2.1:** (a) độ dài cụm báo nhầm sau khi
   gỡ sự cố, so với 7 giây của bản cũ; cửa sổ ức chế 8 s giữ nguyên dù kết quả thế nào;
   (b) chạy lại Isolation Forest trên tập train sạch, cùng cấu hình và 5 seed như Phase 6,
   sau khi tái lập đúng số Phase 6 trên tập train cũ.
