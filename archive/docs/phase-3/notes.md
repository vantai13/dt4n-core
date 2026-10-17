# Phase 3 — Notes (lệnh đã chạy, lỗi gặp + cách fix)


## Nghiệm thu bản Core 2026-09-15

Xem `results/report/ACCEPTANCE.md` và các log tương ứng. Bản Core kiểm chứng bằng Mininet thật, Ditto thật và namespace `org.dt4n.core`; import/test được đặt PYTHONPATH trỏ kho mới. Kết quả của phase này được tổng hợp khi suite hoàn tất, không dùng số kỳ vọng làm số đo.


### Kết quả chạy thực tế bản Core

Dashboard hiển thị 8 node/8 link, F5 giữ topology. Đã bấm UI 30 cặp disable/enable, p50/p95: {'n': 60, 'mean_ms': 991.0389578833474, 'p50_ms': 990.414193499987, 'p95_ms': 1011.7309460001707, 'p99_ms': 1118.0967919999603, 'max_ms': 1118.0967919999603, 'min_ms': 864.3003869999575}; runtime khớp: True. HISTORY, ALERTS, last-known được lưu ảnh và JSON trong results/report. Video UI ở results/report/demo_video/.

## Kiểm chứng trước ML — v2

run_sync mặc định profile normal đa client tới hai server; có normal/flood/server-only/idle. Trang report.html đã thêm dữ liệu/độ trễ v2 và nhãn riêng v1. Ảnh bảng mới: results/report/ml_results_overview.png. Kiểm chứng 60 thao tác UI và last-known trước đây giữ nguyên là bằng chứng nghiệm thu v1.
