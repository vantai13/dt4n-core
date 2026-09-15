# Phase 5 — Chuẩn bị dữ liệu ML

Đã hoàn tất pilot v2: 60 normal, 60 flood, 30 inject; cả 6 gate feature đạt. Thống kê độ lệch chuẩn và SHA-256 ở results/report/ml_dataset_summary.json. Chưa huấn luyện mô hình; cần đa dạng hóa tải/seed/fault và chia train/test theo lần chạy. Bỏ feature hằng hoặc không hợp lệ, kiểm tra qdiscValid; không trộn loss v1/v2 trực tiếp.

Lesson 5.1 hoàn tất: 150×158, GIỮ41/CHẤT VẤN11/LOẠI48/BỎ QUA58, gate 37 ứng viên mạnh; test51 pass4 skip. Chi tiết và giới hạn: [01-feature-audit.md](01-feature-audit.md). Null giữ nguyên; chưa impute hoặc train. Map hướng8 link được thêm và test, snapshot v2 gốc vẫn giữ alphabetical_fallback.

Lesson5.2 hoàn tất: collector thêm validity rate, flatten giữ t_source từng Thing;24/1200 loss missing warmup, bỏ3 dòng còn147. Audit41/11/48 không đổi, cột tăng174 với16 timestamp metadata. Test80 pass4 skip. Chi tiết [02-missing-data.md](02-missing-data.md); cần chạy lại sau5.4 và thiết kế nhiều run ở5.3.

Lesson5.3:18run8train/10test,27,1%base rate dự kiến,coveragehypothesis8/8;116pass4skip. [03-experiment-matrix.md](03-experiment-matrix.md). JSON commit trước thu; campaign chưa chạy.

Lesson5.4 phần chuẩn bị: campaign logic và3patch xong;matchTrue,18plan,75s/t_rel70;152pass4skip. [04-data-generation.md](04-data-generation.md). Chưa chạy chiến dịch.
