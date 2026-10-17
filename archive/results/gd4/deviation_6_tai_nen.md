# GĐ4 — Sai lệch 6: C1 lần 2 không đo được vì luồng tải nền chết giữa chừng (viết trước khi chạy lần 3)

Thời điểm: 17/10/2026, khoảng 01:10 UTC.

Chuyện gì xảy ra. C1 lần 2 (bắt đầu 16/10 23:37 UTC, sau sai lệch 5) chạy được 3 lượt đầu, cả
3 chọn đúng thủ phạm. Từ lượt 03, cả 17 lượt bị hủy ở bước kiểm trạng thái sạch, vì detector
công bố act liên tục dù flood đã dừng và băng thông đã trả về 20 Mbps. Receipt của lần 2 ghi
`localization_pass: true` chỉ vì lượt hủy không bị tính là lượt sai mục tiêu. Với 17/20 lượt
hủy, kết quả này không được dùng.

Chẩn đoán. Một lần chạy riêng (`scripts/diag_gd4cl_c1.py`, 17/10 00:57-01:02 UTC, không ghi
results/report) lặp lại 3 lượt đầu với cùng seed và thứ tự, ghi từng giây những cột detector
thấy vượt biên và chụp tiến trình iperf sau mỗi lượt. Nhật ký ở `logs/gd4cl_diag/` trên máy
GCP và trong bản chép về máy làm việc.

- Luồng TCP nền của h1 (`iperf -c 10.0.0.4 -p 5001`) thoát ở giây 150, trong lượt 01 (h1
  flood srv2), với `write failed: Connection timed out`. Luồng của h3 thoát theo cùng cách ở
  giây 269, trong lượt 02 (h3 flood srv1). Ở cả hai lượt, máy flood bị controller giới hạn 7
  Mbps và luồng UDP flood của chính nó chiếm hết phần băng thông đó, nên luồng TCP nền của nó
  hết thời gian chờ. Bộ tạo tải không bật lại luồng đã thoát.
- Sau lượt 02, h1 và h3 không còn gửi. Detector 2.1 thấy đúng 18 cột tốc độ dưới biên dưới
  (k_rate = 18), trong khi luật act cần k_rate > 18. Ở lần chẩn đoán, detector vì vậy trở về
  normal, sát ngưỡng. Ở C1 lần 2, danh sách bất thường sau flood có thêm link s2-s3, đủ để
  vượt ngưỡng, và detector kẹt ở act.
- Detector 1.0.0 của Phase 8 có biên dưới bằng 0 cho tốc độ của h1 và h3, nên hiện tượng này
  không làm nó báo động.

Đánh giá. Đây là lỗi của bộ tạo tải trên testbed, không thuộc đối tượng đo. Thiết kế của C1
giả định mỗi lượt bắt đầu với tải nền bình thường gồm ba luồng TCP và luồng UDP srv1 tới srv2.

Sửa. Chạy C1 lần 3 bằng `scripts/run_gd4cl_c1_lan3.py`. Script gọi lại nguyên `run_one` và
`main` của `run_gd4cl_c1.py`, chỉ thêm một bước trước mỗi lượt là khởi động lại tải nền bằng
`start_profile_background` với cùng tham số như lúc dựng môi trường, và ghi số tiến trình iperf
client còn sống trước và sau bước này. Detector 2.1, luật chọn ứng viên theo chiều, bốn kịch
bản, seed 20260921, thứ tự lượt, tiêu chí (results/report/gd4cl_prereg.json) và cách chấm không
đổi. Receipt của lần 2 được đổi tên thành `results/report/gd4cl_c1_lan2.json` và giữ lại, nhật
ký của lần 2 chuyển sang `logs/gd4cl_c1_lan2/`.
