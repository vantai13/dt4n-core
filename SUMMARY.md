# Tổng kết DT4N Core — 15/09/2026

## Đã thực hiện

- Tách phần lõi bốn lớp Mininet → Bridge → Eclipse Ditto → Vue Dashboard từ repo DT4N; giữ nguồn gốc tại `PROVENANCE.md`.
- Giữ đầy đủ phụ thuộc Python và stub Mininet, kiểm tra 22 module đều nạp từ repo mới.
- Bổ sung cấu hình Ditto/nginx và image digest để dựng lại môi trường đã đo.
- Chạy kiểm tra định tuyến, bootstrap lần đầu/lặp lại và bootstrap mở rộng 20 client + 2 server.
- Kiểm tra Mininet thật, topology cấu hình 5 client, normal/flood và thu dữ liệu snapshot.
- Đo đồng bộ lên, lệnh vòng kín, luồng lệnh tự động và UI qua trình duyệt thật.
- Kiểm chứng completeness, accuracy trạng thái link, event fidelity, 4 test bảo mật live và chạy dài 30 phút.
- Kiểm tra UI sau F5, HISTORY/ALERTS, điều khiển khớp mạng thật và giữ trạng thái sau khi runner dừng; lưu ảnh/video.
- Sửa verify để phân trang Ditto với page size 200; bổ sung hai test hồi quy phân trang/cursor lặp.
- Điều chỉnh timeout biên nhận flow về 0 theo dashboard, chạy đo lại và giữ bằng chứng lần thử trước.
- Sửa script tổng kết đọc đúng cấu trúc JSON verify; cập nhật notes phase 0–4, runbook và trang kết quả.

## Kết quả chạy và đo

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Import | 0/22 lỗi; module từ repo mới | `results/report/imports.json` |
| Unit test | 23 passed, 4 skipped, 0 failed, 0 errors | `results/report/pytest.xml`, `logs/pytest.log` |
| Routing | Sinh lại khớp, không vòng lặp | `results/report/routing_comparison.json`, `logs/gen_routes.log` |
| Bootstrap mở rộng | 52/52 Thing đọc được; chạy lặp không tạo trùng | `results/report/bootstrap_scale.json` |
| Normal / flood | 60 snapshot mỗi kịch bản | `logs/snapshots_normal.jsonl`, `logs/snapshots_flood.jsonl` |
| Verify | Đủ 5 host, 3 switch, 8 link; accuracy link 100%; 20/20 sự kiện | `docs/phase-2/verify_report.json` |
| Security live | 4 passed, không skip | `results/report/security_live.xml` |
| UI | 60 thao tác khớp mạng thật; giữ 8 node/8 link sau runner dừng | `results/report/dashboard_live.json`, `dashboard_last_known.json` |
| Soak | 1.800,09 giây; 31 mẫu; 0 ERROR/CRITICAL; RSS 29.244 → 29.456 KiB | `results/report/soak_30min.json`, `logs/acceptance_runtime.log` |

| Phép đo | n hợp lệ | p50 (ms) | p95 (ms) | File trong `results/report/` |
|---|---:|---:|---:|---|
| Đồng bộ lên | 30 | 992,31 | 1.049,34 | `latency_up.json` |
| Lệnh vòng kín | 30 | 1.002,51 | 1.035,48 | `latency_command.json` |
| UI click → SSE | 60 | 990,41 | 1.011,73 | `dashboard_live.json` |
| Luồng lệnh tự động | 60 | 864,00 | 872,00 | `command_flow.json` |

Các độ trễ đồng bộ/lệnh/UI đạt mục tiêu p95 tương ứng 2/2/3 giây. Accuracy verify chỉ đánh giá trạng thái 8 link. Soak có một mẫu đầu 7/8 link khi khôi phục sau test bảo mật; 30 mẫu sau đạt 8/8. RSS tăng 212 KiB trong kỳ đo, chưa đủ để kết luận không rò bộ nhớ ở mọi thời lượng. Bootstrap mở rộng chưa xác định số node tối đa ổn định.

## Xem kết quả

- Báo cáo: [results/report/ACCEPTANCE.md](results/report/ACCEPTANCE.md).
- JSON tổng hợp: [results/report/final_summary.json](results/report/final_summary.json).
- Trang kết quả: `report.html`; phục vụ từ gốc repo qua `python3 -m http.server 8765`, mở http://localhost:8765/report.html.
- Dashboard: http://localhost:5173 khi Vite đang chạy.
- Ảnh: `results/report/results_overview.png`, `results_screen.png`, `dashboard_*.png`.
- Video: `results/report/demo_video/`.
- Hướng dẫn bằng chứng/chạy tiếp: [runbooks/core-acceptance-status.md](runbooks/core-acceptance-status.md).

Trong VS Code Remote SSH, forward cổng 8765 và 5173. Kho DT4N cũ giữ nguyên lịch sử nghiên cứu.

## Bổ sung trước ML — v2

Đã sửa nguồn loss, profile đa client, injection không tranh shell, đo pha ngẫu nhiên, kiểm tra timeout=3, giản lược Swagger và bổ sung attribution/README/UTC. Test hiện tại 29 passed, 4 skipped; security live 4 pass. 60 normal + 60 flood + 30 inject; các gate feature đều đạt: True.

Độ trễ randomized-settle: đồng bộ p50/p95 682.14/1017.11 ms, lệnh 674.70/984.19 ms. HTTP timeout=3: [408, 408], trạng thái vẫn phản ánh [True, True].

Báo cáo, bảng so sánh và giới hạn: [ML_PREFLIGHT.md](results/report/ML_PREFLIGHT.md). JSON: [ml_dataset_summary.json](results/report/ml_dataset_summary.json). Đây là kiểm chứng dữ liệu trước ML, chưa huấn luyện mô hình.
