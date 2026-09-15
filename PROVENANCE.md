# Nguồn gốc mã nguồn

- Kho gốc: https://github.com/vantai13/dt4n
- Commit: d45cf4ff26d8c6204a181f0fa77887e087a4d381
- Ngày tách (UTC): 2026-09-15T08:12:06.938068+00:00
- Trạng thái nguồn: sạch khi copy.

Kho mới giữ phần lõi bốn lớp của đề tài. Lịch sử phát triển vẫn ở kho gốc. Các sửa đổi để kiểm chứng được ghi trong báo cáo nghiệm thu.

## Điều chỉnh sau khi tách để kiểm chứng trên môi trường thật

- `bridge/verify.py`: dùng page size 200 và theo cursor; Ditto đang chạy từ chối size 500 bằng HTTP 400.
- `measurements/measure_command_flow.py`: timeout biên nhận mặc định 0, giống dashboard; tránh cộng 3 giây chờ ack vào phép đo phản ánh trạng thái.
- `measurements/measure_latency.py`, `measure_command_latency.py`: thêm mẫu gốc và số timeout vào dữ liệu trả về cho các lần chạy lại. Đợt nghiệm thu đầu lưu thống kê toàn độ chính xác và từng mẫu làm tròn trong log.
- `test/test_command_security.py`: gửi clientCorrelationId trong payload (SSE không trả header này trên stack hiện tại), timeout 0 và dùng namespace môi trường; giữ nguyên các assert về whitelist/payload/target/idempotency.
- `test/test_phase2_5.py`: thêm hai test hồi quy cho phân trang >200 Thing và cursor lặp.
- Thêm cấu hình Ditto cùng các file nginx phụ thuộc, script nghiệm thu, README và bằng chứng kết quả.

Mọi lần chạy thử chưa đạt được giữ log hoặc JSON với tiền tố `first_`/`ack3_`; báo cáo cuối phân biệt các lần chạy đó với phép đo hoàn tất.

Cấu hình Compose đã đổi đường dẫn bind mount tài liệu sang ditto/static trong kho, bổ sung các tài nguyên phụ thuộc, mặc định Ditto 3.9.1 và thêm override digest của tám image chạy thật. Không thay đổi stack đang chạy.

## Kiểm chứng dữ liệu trước ML — v2 (2026-09-15)

Sửa qdisc counters/validity, profile đa client, injection mnexec, jitter settle và xác nhận reset latency; giữ dataset và thống kê v1. Thêm pilot mạng thật, HTTP timeout=3 probe, test hồi quy, tổng kết và ảnh v2. Bỏ optional Swagger/OpenAPI khỏi cây Git hiện tại; service docs cũng được bỏ khỏi Compose. 74 static asset còn giữ khớp byte với source release Eclipse Ditto 3.9.1, SHA-256 trong ditto_asset_provenance.json; license/notice upstream được bảo tồn trong ditto/upstream.

Không viết lại commit 8660edf; tài liệu upstream của bản v1 vẫn có trong lịch sử. Pilot v2 chưa phải nghiệm thu hiệu quả mô hình ML.
