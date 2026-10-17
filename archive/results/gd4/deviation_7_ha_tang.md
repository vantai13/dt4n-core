# GĐ4 — Sai lệch 7: C1 lần 3 hủy 12/20 lượt vì hạ tầng (viết trước khi chạy lần 4)

Thời điểm: 17/10/2026, khoảng 02:00 UTC.

Kết quả lần 3 (results/report/gd4cl_c1_lan3.json, 01:06-01:32 UTC). 20 lượt, 8 lượt chạy
được và cả 8 chọn đúng thủ phạm (mỗi kịch bản 2 lượt), 0 lượt sai mục tiêu. 12 lượt bị hủy,
nên phép đo chưa đạt mức hủy tối đa 20% mà thí nghiệm A/B dùng. Kết quả này được giữ và báo
cáo, không bị thay.

Nguyên nhân của 12 lượt hủy, đều thuộc hạ tầng:

1. Lượt 02 và 08: bước khởi động lại tải nền thêm ở lần 3 (sai lệch 6) có lúc chỉ để lại 2
   hoặc 3 trên 4 tiến trình iperf client (`background_restart.clients_after` trong receipt).
   Lượt bắt đầu thiếu luồng nền, detector công bố act, bước kiểm trạng thái sạch hủy lượt.
2. Lượt 10 đến 19: container MongoDB của Ditto dùng 97-99% trần bộ nhớ 256 MiB, Ditto trả
   ReadTimeout và HTTP 503, bước kiểm sức khỏe hạ tầng hủy lượt. Ditto đã chạy liên tục
   khoảng 15 giờ qua A/B, C1 lần 2, lần chẩn đoán và C1 lần 3 mà không được khởi động lại,
   trái với ràng buộc đã ghi ở docs/phase-8/07-stability.md, mục 6. Trần 256 MiB lấy từ cấu
   hình mẫu của Ditto. Với trần này, MongoDB 7.0 đặt bộ đệm WiredTiger bằng đúng 256 MiB nên
   luôn chạy sát trần.

Sửa.

- Hạ tầng: nâng trần bộ nhớ của MongoDB lên 1 GiB và đặt `--wiredTigerCacheSizeGB 0.25`, trên
  máy GCP (`docker update` cho container đang chạy, sửa cả docker-compose.yml, bản cũ lưu ở
  docker-compose.yml.bak-20261017) và trong `ditto/docker-compose.yml` của repo. Máy GCP có 32
  GiB RAM. Khởi động lại MongoDB và các dịch vụ Ditto trước khi chạy lần 4, ghi bộ nhớ trước
  và sau.
- Runner: `scripts/run_gd4cl_c1_lan4.py` gọi lại nguyên `run_one` và `main` của
  `run_gd4cl_c1.py`, chỉ đổi phần chuẩn bị giữa hai lượt. Tải nền được khởi động lại tới khi
  đủ 4 tiến trình iperf client và cả ba máy khách gửi ít nhất 1,5 Mbps trên twin trong 3 giây
  liên tiếp (tối đa 5 lần thử). Nếu Ditto không khỏe hoặc MongoDB dùng từ 95% trần, MongoDB
  được khởi động lại trước lượt kế tiếp, không bao giờ giữa một lượt, và sự kiện được ghi
  vào dòng của lượt đó.

Detector 2.1, luật chọn ứng viên theo chiều, bốn kịch bản, seed 20260921, thứ tự lượt, tiêu
chí (results/report/gd4cl_prereg.json) và cách chấm không đổi. Receipt của lần 3 đổi tên
thành `results/report/gd4cl_c1_lan3.json`, nhật ký chuyển sang `logs/gd4cl_c1_lan3/`.
