# GĐ4 — Sai lệch 4: lần khởi chạy đầu của vòng kín bị hủy vì lỗi hạ tầng (viết trước khi chạy lại)

Thời điểm: 16/10/2026, khoảng 10:35 UTC.

**Chuyện gì xảy ra.** Lần khởi chạy đầu (bắt đầu 10:24:52 UTC) dùng dịch vụ Ryu của máy GCP
(`dt4n-controller.service`, thư mục `~/dt4n-core`), còn thí nghiệm chạy trong `~/dt4n-core-cl`.
Ryu đọc bảng cổng từ `ditto/port_map.json` theo đường dẫn tương đối với thư mục của nó, nên
không thấy bảng cổng do Mininet của thí nghiệm ghi ra ("s2 has no port map yet; route install
skipped"). Mỗi switch chỉ có flow mặc định, gói không được chuyển tiếp, detector ở mức cần hành
động liên tục từ giây đầu (35/36 cột tốc độ ngoài biên, residual ở s2 bằng 1,0).

**Ảnh hưởng.** Ba lượt A/B đầu (khối 0, lượt 0-2) đều bị hủy ở bước kiểm trạng thái sạch, trước
khi gây flood. Không lượt nào đo được kết cục; tệp kết quả gd4cl_ab.json chưa được ghi. Lần chạy
được dừng bằng tay lúc khoảng 10:35 UTC. Nhật ký giữ ở `logs/gd4cl_attempt1/` trên máy GCP.

**Sửa.** Chạy Ryu riêng trong chính thư mục thí nghiệm (như launcher của các chiến dịch thu dữ
liệu), rồi chạy lại từ đầu với cùng code, cùng tiêu chí (results/report/gd4cl_prereg.json) và
cùng seed. Luật chọn ứng viên, detector và thiết kế không đổi.
