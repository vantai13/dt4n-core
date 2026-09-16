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

## Lesson 5.1 — Feature audit

Đã hoàn tất trên nhánh `phase/5-dataset`: 150 snapshot × 158 cột; GIỮ 41, CHẤT VẤN 11, LOẠI 48, BỎ QUA 58. Gate đạt với 37 feature được giữ có auc_dist >0.5. `cycle_scan_ms` được bỏ qua như metadata nên số giữ thấp hơn hướng dẫn một cột. Thêm map hướng tham chiếu đủ 8 link và giữ nguyên dataset v2.

Kiểm thử: **51 passed, 4 skipped**, không lỗi; 4 skip cần môi trường live. Báo cáo: [01-feature-audit.md](docs/phase-5/01-feature-audit.md). Bảng: [feature_audit.csv](results/report/feature_audit.csv); JSON: [feature_audit_summary.json](results/report/feature_audit_summary.json); biểu đồ: [feature_audit_dist.png](results/report/feature_audit_dist.png); log: [phase5_pytest.log](logs/phase5_pytest.log).

Pilot chưa chứng minh hiệu quả mô hình; còn confound TCP/UDP và tải, injection không có baseline/onset, s2-s3 chưa tách biệt và chỉ một đoạn thu/profile. Kết quả triển khai5.2–5.4 xem các mục tiếp theo.

## Lesson 5.2 — Dữ liệu thiếu

Đã thêm rateValid/rateReason vào collector, giữ16 timestamp Thing và chính sách DT4N-M1 không fillna(0). Pilot thiếu24/1200 ô loss (2%), đều warmup tick0; bỏ3/150 dòng, còn147 và0 missing loss. Rate host có30 warmup zero, không thấy zero giả giữa run; rate link v2 chưa có counter/cờ để kiểm toán.

Test **80 passed,4 skipped**. Audit mới150×174, GIỮ41/CHẤT VẤN11/LOẠI48/BỎ QUA74;37 ứng viên mạnh không đổi. Báo cáo: [02-missing-data.md](docs/phase-5/02-missing-data.md); output: [missing_analysis.json](results/report/missing_analysis.json), [log](logs/missing_analysis.log), [biểu đồ](results/report/missing_analysis.png). CI/Fisher theo ô chỉ mô tả vì mẫu phụ thuộc; không kết luận MNAR tổng quát.

## Lesson5.3 — Ma trận đã khóa trước thu

18run:8train normal,2test-control,8test-fault;4loại fault. Base rate test nominal160/590=27,1%, hypothesis coverage8/8link. Thêm LinkAdminDown, seeded scenario đúng target, varying load và cleanup process group. Train varying lịchA hai seed; test-control lịchB.

Test116 passed/4skipped; audit và missing giữ số. Đây là số thiết kế trước thu; nghiệm thu thu thật ở Lesson5.4. [Báo cáo](docs/phase-5/03-experiment-matrix.md), [JSON](results/report/experiment_matrix.json), [bảng](docs/phase-5/03-experiment-matrix.generated.md), [timeline](results/report/experiment_matrix.png), [log](logs/phase53_pytest.log). CSV audit chỉnh sẵn được giữ local.

## Lesson5.4 — Chiến dịch thu thật đã nghiệm thu

Đã bổ sung runner/launcher và sửa namespace host/policy, lỗi health sau forced refresh, cổng log và resume. Smoke admin-down đạt trước khi chạy chiến dịch. Giữ lịch sử 7 lần thu bị loại do health ERROR; thu lại 5 run sau sửa, không đổi hợp đồng hoặc ghi đè dữ liệu.

**18/18 run đạt; 1080 snapshot raw, 1062 sau warmup; base rate test 27.12%; 0 ERROR/CRITICAL/Traceback trong 18 log được chấp nhận.** Tất cả 8 run fault separation ≥1, normal/control không down ngoài dự kiến. Test163passed/4skipped.

Audit: {'BO_QUA': 106, 'LOAI': 65, 'GIU': 34, 'CHAT_VAN': 18}; 2 cột state_up của link admin-down thay đổi. Loss thiếu raw 1.7593%; còn 8 ô sau warmup, giữ NaN/dòng và giải thích counter_reset. Không kết luận MNAR tổng quát. Ngưỡng đơn biến cũ của pilot không đạt:0feature cóauc_dist>0.5 trên nhãn point-wise gộp; chưa chứng minh hiệu quả detector.

[Báo cáo và file kết quả](docs/phase-5/04-data-generation.md) · [Manifest](results/report/ml_dataset_manifest.json) · [Nghiệm thu](results/report/campaign_acceptance.json) · [Audit](results/report/campaign_feature_audit.csv) · [Missing](results/report/campaign_missing_analysis.json). Raw ở data/phase5/raw; backup local: /home/ubuntu/dt4n-core-phase5-raw-20260915.tar.gz, SHA và kiểm archive trong [receipt](results/report/campaign_raw_backup.json). Raw không được đưa vào GitHub theo quy tắc đã chốt.


Lesson 5.5 hoàn thành: 13/13 gate; 18 run/1.080 nhãn; chính160/590=27,12%; độ nhạy80/494=16,19%. Onset tối đa10 tick, recovery tối đa2 tick; giữ kết quả grace2 không đạt và công thức y cũ. [Báo cáo](docs/phase-5/05-ground-truth.md), [JSON](results/report/ground_truth.json), [biểu đồ](results/report/label_overlay.png).


**Cập nhật Lesson 5.5b:** phép đo cũ chỉ xét onset của kênh mạnh nhất. Quét tất cả kênh dự kiến cho thấy onset sớm nhất **0 tick ở cả 8 run F**, bao gồm degrade s2–s3 trên txRate; lossPct mạnh nhất vẫn onset10. Chốt lại grace onset2/recovery2, độ nhạy144/558=25,81%; chính160/590 không đổi. Bản trước giữ ở `ground_truth_witness_grace10.json`; không diễn giải first-crossing trên nhiều kênh như bằng chứng nhân quả hay khả năng phát hiện chắc chắn của mô hình.
