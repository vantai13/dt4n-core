# Phase 4 — Notes (lệnh đã chạy, lỗi gặp + cách fix)


## Nghiệm thu bản Core 2026-09-15

Xem `results/report/ACCEPTANCE.md` và các log tương ứng. Bản Core kiểm chứng bằng Mininet thật, Ditto thật và namespace `org.dt4n.core`; import/test được đặt PYTHONPATH trỏ kho mới. Kết quả của phase này được tổng hợp khi suite hoàn tất, không dùng số kỳ vọng làm số đo.


### Kết quả chạy thực tế bản Core

Test bảo mật thật: {'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '4', 'time': '0.283', 'timestamp': '2026-09-15T08:29:37.521535+00:00', 'hostname': 'dt4n-research-01'}. Whitelist/payload/target/idempotency dùng audit log theo clientCorrelationId trong payload. Đã sửa test gửi timeout=0 cho phù hợp giao thức dashboard, không giảm các assert. Runtime ERROR/CRITICAL: 0 dòng trong acceptance_runtime.log. Bootstrap 20 client + 2 server đọc đủ 52 Thing, chưa xác định giới hạn capacity mạng tối đa.
