# GĐ4 — Sai lệch 5: phép thử định vị (C1) lần đầu không chạy được lượt nào vì Ryu đã bị dừng (viết trước khi chạy lại)

Thời điểm: 16/10/2026, phát hiện lúc 23:35 UTC.

Chuyện gì xảy ra. Wrapper chạy A/B rồi C1 nối tiếp, với một tiến trình Ryu bật bằng tay trong
`~/dt4n-core-cl` (sai lệch 4). A/B xong lúc 12:01:40 UTC (32/32 lượt, không lượt nào bị hủy). Khi
runner A/B đóng môi trường, bước dọn Mininet (`mn -c`) dừng luôn mọi tiến trình `ryu-manager`, như
đã ghi ở docstring của `EnvRunner.close` và `scripts/launch_ml_dataset.py`. Ở Phase 8, Ryu chạy
dưới dịch vụ systemd nên được bật lại; ở lần này Ryu bật bằng tay nên không ai bật lại. Runner C1
khởi động lúc 12:01:41 UTC, Mininet báo "Unable to contact the remote controller at
127.0.0.1:6653" và đứng chờ, vì runner không có thời hạn cho bước dựng mạng.

Ảnh hưởng. C1 chưa chạy lượt nào: chưa gây flood, chưa có audit, tệp `gd4cl_c1.json` chưa được
ghi. Kết quả A/B (`gd4cl_ab.json`) không bị ảnh hưởng, vì toàn bộ 32 lượt chạy khi Ryu còn sống.
Tiến trình C1 và wrapper được dừng bằng tay lúc 23:37 UTC. Nhật ký giữ ở
`logs/gd4cl_c1_attempt1/` trên máy GCP.

Sửa. Bật lại Ryu trong cùng thư mục, rồi chạy riêng C1 với cùng code, cùng tiêu chí
(results/report/gd4cl_prereg.json) và cùng seed 20260921. Detector, luật chọn ứng viên, kịch bản
và cách chấm không đổi.
