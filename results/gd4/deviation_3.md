# GĐ4 — Sai lệch 3: hai run chạy nền thay vì ba, thu lại một run tải cao (viết trước khi thu)

Thời điểm: 16/10/2026, trước khi thu bất kỳ run nào dưới đây.

**1. R-S: 2 run thay vì 3.** Theo quyết định của chủ nhiệm đề tài, chỉ thu hai run chạy nền
60 phút. Hai run được chọn theo thứ tự chạy đã khóa trong hợp đồng gd4r: `RS-soak2M-s5001-r1`
(vị trí 16) và `RS-soak2M-s5003-r3` (vị trí 17). `RS-soak2M-s5002-r2` (vị trí 23) không thu.
S2 tính trên hai run này (khoảng 2 giờ), mục tiêu không đổi (cận trên 95% ≤ 3 lần/giờ).
Với 0 lần trong 2 giờ, cận trên là khoảng 1,5 lần/giờ, nên S2 vẫn đo được.

**2. Thu lại `RN-load8M-s5014-r2`.** Run này có h1 và h3 = 0 Mbps suốt run, không qua cổng lưu
lượng máy khách (kiểm ở lần chấm 1, results/report/gd4_acceptance_v21.json). Lý do thu lại là
dữ liệu đầu vào hỏng, không phải kết quả của detector. Lần thử hỏng được chuyển vào thư mục cách
ly với hậu tố `.attempt-…` và vẫn được báo cáo. Thu lại tối đa hai lần; dùng lần đầu tiên qua
cổng lưu lượng; mọi lần thử đều báo cáo. Kết quả S10 của lần thử hỏng (59/59 giây báo động, bộ
chặn vùng tải không bật) đã được xem trước khi quyết định thu lại; S10 chỉ để báo cáo, không có
mục tiêu.

**3. Script chấm** thêm tùy chọn `--runs` để chấm đúng các run mới thu (hai run R-S và lần thu
lại của R-N), không chấm lại các run đã chấm.
