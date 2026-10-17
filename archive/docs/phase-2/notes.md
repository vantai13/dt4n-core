# Phase 2 — Notes (lệnh đã chạy, lỗi gặp + cách fix)


## Nghiệm thu bản Core 2026-09-15

Xem `results/report/ACCEPTANCE.md` và các log tương ứng. Bản Core kiểm chứng bằng Mininet thật, Ditto thật và namespace `org.dt4n.core`; import/test được đặt PYTHONPATH trỏ kho mới. Kết quả của phase này được tổng hợp khi suite hoàn tất, không dùng số kỳ vọng làm số đo.


### Kết quả chạy thực tế bản Core

Completeness vật lý: True. Accuracy trạng thái link: 100.0%; event fidelity: {'detected': 20, 'total': 20, 'fidelity_pct': 100.0, 'log': [{'i': 1, 'detected': True, 'latency_s': 0.518}, {'i': 2, 'detected': True, 'latency_s': 1.017}, {'i': 3, 'detected': True, 'latency_s': 0.964}, {'i': 4, 'detected': True, 'latency_s': 1.015}, {'i': 5, 'detected': True, 'latency_s': 1.016}, {'i': 6, 'detected': True, 'latency_s': 1.018}, {'i': 7, 'detected': True, 'latency_s': 0.963}, {'i': 8, 'detected': True, 'latency_s': 1.017}, {'i': 9, 'detected': True, 'latency_s': 0.967}, {'i': 10, 'detected': True, 'latency_s': 0.961}, {'i': 11, 'detected': True, 'latency_s': 1.025}, {'i': 12, 'detected': True, 'latency_s': 1.014}, {'i': 13, 'detected': True, 'latency_s': 0.959}, {'i': 14, 'detected': True, 'latency_s': 1.016}, {'i': 15, 'detected': True, 'latency_s': 0.961}, {'i': 16, 'detected': True, 'latency_s': 1.015}, {'i': 17, 'detected': True, 'latency_s': 1.02}, {'i': 18, 'detected': True, 'latency_s': 1.021}, {'i': 19, 'detected': True, 'latency_s': 1.015}, {'i': 20, 'detected': True, 'latency_s': 0.961}]}. Báo cáo docs/phase-2/verify_report.json. Độ trễ p50/p95 xem results/report/latency_up.json và latency_command.json. Soak thực chạy 1800.09 giây; RSS đầu/cuối 29244/29456 KiB. Accuracy này chỉ đánh giá trạng thái link.

## Kiểm chứng trước ML — v2

Collector đọc leaf-qdisc cả hai đầu link, giữ interfaceLossPct. Flood client có max qdisc drop khoảng 62,93%, interface loss vẫn 0. Mẫu đầu/reset/unavailable không được coi là loss=0. Latency randomized-settle 30 mẫu mỗi phép, seed 20260915; số gốc trong latency_up_randomized.json và latency_command_randomized.json. HTTP timeout=3 trả 408 cả khi correlation-id có trong payload; twin vẫn phản ánh link down. Giới hạn SSE/HTTP reply ghi trong ML_PREFLIGHT.md.
