# Kết quả thực hiện DT4N Core

Cập nhật UTC: 2026-09-15T09:06:51.314737+00:00

Kho mới: `/home/ubuntu/dt4n-core`. Nguồn: commit `d45cf4ff26d8c6204a181f0fa77887e087a4d381`.

## Kết quả chạy

- Import: 22 module; xem `imports.json` để kiểm tra đường dẫn nạp từ kho mới.
- Pytest: xem `pytest.xml` và `../../logs/pytest.log`.
- Routing: xem `routing_comparison.json`; `../../logs/gen_routes.log` ghi kết quả không có vòng lặp.
- Ditto: namespace thí nghiệm `org.dt4n.core`, 18 Thing (5 host, 3 switch, 8 link, 1 path, 1 controller).
- Bootstrap mở rộng: 20 client + 2 server, 52 Thing; kết quả trong `bootstrap_scale.json`. Phép này chưa xác định số node tối đa ổn định trên Mininet.

## Số đo độ trễ

| Phép đo | n hợp lệ | p50 (ms) | p95 (ms) | Mục tiêu | File |
|---|---:|---:|---:|---|---|
| Đồng bộ LÊN | 30 | 992.31 | 1049.34 | < 2000 ms | latency_up.json |
| Lệnh vòng kín | 30 | 1002.51 | 1035.48 | < 2000 ms | latency_command.json |
| Hiển thị UI thật (click → SSE) | 60 | 990.41 | 1011.73 | < 3000 ms | dashboard_live.json |
| Luồng lệnh tự động | 60 | 864.00 | 872.00 | UI thật đo riêng | command_flow.json |

## Tổng kết nghiệm thu cuối

Test đơn vị: {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '4', 'tests': '27', 'time': '12.125', 'timestamp': '2026-09-15T08:47:51.618745+00:00', 'hostname': 'dt4n-research-01'}. Security live: {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '4', 'time': '0.283', 'timestamp': '2026-09-15T08:29:37.521535+00:00', 'hostname': 'dt4n-research-01'}.
Completeness vật lý: True. Accuracy trạng thái: 100.0%. Event fidelity: 100.0%.
Soak: 1800.09 giây; RSS đầu/cuối/max: 29244/29456/29456 KiB. Runtime ERROR/CRITICAL: 0. Tất cả mẫu accuracy tức thời 100%: False. Xem toàn bộ mẫu và ghi chú giai đoạn UI.

Accuracy chỉ đánh giá trạng thái 8 link, không chứng minh độ chính xác toàn bộ metric traffic/latency.

## Chạy dài

Đã lấy 31 mẫu; thời gian gần nhất 1800.05 giây; hoàn tất: True.

## Giới hạn và khác biệt so với hướng dẫn

- Số file và dung lượng thực tế khác 73 file / 756 KB do dashboard có dist và danh sách hiện tại có 50 file Python; manifest ghi số thực tế.
- PYTHONPATH ban đầu trỏ repo cũ; đã chạy lại import và test với đường dẫn kho mới.
- `mn -c` dừng Ryu: phải dọn trước rồi khởi động controller. Một lần khởi động thử trùng interface đã được dọn và chạy lại; chỉ log lần chạy hoàn tất dùng cho nghiệm thu.
- Đo flow mặc định chờ ack 3 giây tạo số đo cao giả; đã đổi timeout mặc định về 0 (giống dashboard), đo lại đủ 30 cặp; log cũ trong `logs/ack3_command_flow_measure.log`.
- `--long` trong run_sync chỉ có hiệu lực cùng `--verify`; duration của nhánh đó là phút. Lệnh 1800 trong hướng dẫn không chạy soak 30 phút. Script `scripts/run_acceptance.py` đo 1800 giây bằng đồng hồ monotonic và ghi RSS mỗi phút.
- Trong các phút đầu soak có khôi phục link sau security test và 30 cặp thao tác UI. Mẫu tức thời có thể khác twin do polling 1 giây; giữ nguyên mọi mẫu trong soak_progress/soak_30min, không bỏ mẫu lệch. Phép verify tĩnh và độ trễ phản ánh sau sự kiện được báo cáo riêng.
- Verify đã sửa phân trang size=200; test bảo mật đã gửi clientCorrelationId trong payload và timeout=0. Test hồi quy phân trang/cursor lặp đã bổ sung.
- Chưa đẩy GitHub: truy cập `vantai13/dt4n-core` báo Repository not found.
- Dashboard: http://localhost:5173 (forward cổng 5173 trong VS Code Remote SSH).
