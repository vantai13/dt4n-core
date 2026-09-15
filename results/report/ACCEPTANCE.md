# Kết quả thực hiện DT4N Core

Cập nhật UTC: 2026-09-15T15:08:23.914108+00:00

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
- Repo đã xuất bản: https://github.com/vantai13/dt4n-core (nghiệm thu v1 ở commit 8660edf).
- Dashboard: http://localhost:5173 (forward cổng 5173 trong VS Code Remote SSH).


## Bổ sung trước ML: dữ liệu v2

Normal TCP 2 Mbps/client; flood UDP 50 Mbps/client; mọi client tới hai server luân phiên. UDP srv1→srv2 2 Mbps giữ tải s2-s3.

| Link | Normal (Mbps) | Flood (Mbps) | Max qdisc drop flood (%) |
|---|---:|---:|---:|
| link-h1-s1 | 2.16 | 20.00 | 62.931 |
| link-h2-s1 | 2.16 | 20.00 | 62.929 |
| link-h3-s1 | 2.15 | 19.85 | 62.931 |
| link-s1-s2 | 4.30 | 20.00 | 50.030 |
| link-s1-s3 | 2.15 | 20.00 | 0.000 |
| link-s2-s3 | 2.16 | 2.16 | 0.000 |
| link-s2-srv1 | 4.30 | 20.00 | 0.000 |
| link-s3-srv2 | 4.30 | 20.00 | 9.781 |

Tốc độ là trung bình max(rxRate, txRate) theo mỗi snapshot. Loss v2 là local leaf-qdisc egress hai chiều, không phải loss đường đi. Bỏ mẫu đầu; qdiscValid phải true.
Gate kiểm chứng: {'normal_flood_have_60_snapshots': True, 'all_8_links_active_in_normal': True, 'all_clients_flood_rate_exceeds_normal_2x': True, 'flood_qdisc_loss_observed': True, 'injection_qdisc_loss_observed': True, 'all_v2_qdisc_samples_valid_after_warmup': True}. Xem ml_dataset_summary.json và ML_PREFLIGHT.md. Pilot này chưa chứng minh kết quả mô hình ML.

### Độ trễ: fixed-settle v1 và randomized-settle v2

Các mẫu v1 chụm gần một chu kỳ, phù hợp với nghi vấn khóa pha do settle cố định. Không coi v1 là giới hạn worst-case đã được chứng minh. V2 thêm jitter seed cố định trên [0, period]; collector v2 cũng thêm đọc qdisc nên đây không phải thí nghiệm chỉ thay đổi một yếu tố.

| Phép đo randomized-settle | n | p50 (ms) | p95 (ms) | File |
|---|---:|---:|---:|---|
| latency_up_randomized | 30 | 682.14 | 1017.11 | latency_up_randomized.json |
| latency_command_randomized | 30 | 674.70 | 984.19 | latency_command_randomized.json |

### Biên nhận lệnh

HTTP timeout=3 trả các status: [408, 408]. Trạng thái mạng vẫn phản ánh: [True, True]. Xem SSE gốc trong command_ack_timeout3.json.
HTTP outbox POST của agent là thông báo mới, không phải Ditto Protocol response tương quan cho inbox. timeout=0 xác nhận tiếp nhận HTTP; phép đo vòng kín vẫn chờ trạng thái thật. Chi tiết và nguồn chính thức trong ML_PREFLIGHT.md.

## Lesson 5.1 — Feature audit

150 snapshot × 174 cột; quyết định: {'BO_QUA': 74, 'LOAI': 48, 'GIU': 41, 'CHAT_VAN': 11}.
Gate: 37 feature được GIỮ có auc_dist >0.5; kết quả True.
Test Lesson 5.1: 51 passed, 4 skipped; xem phase5_pytest.xml. Chưa train hoặc impute. Báo cáo: ../../docs/phase-5/01-feature-audit.md; CSV/JSON/plot: feature_audit*.
Pilot còn confound protocol/tải và thứ tự run; injection không có onset/baseline. AUC này là thống kê đơn biến trên dữ liệu đã audit.

## Lesson 5.2 — Dữ liệu thiếu

Kiểm thử: 80 passed, 4 skipped.
Missing loss: 2.0%; bỏ 3/150 dòng warmup, giữ 147; còn 0 ô loss thiếu.
Collector thêm rateValid/rateReason; flatten giữ timestamp Thing. Audit GIỮ41/CHẤT VẤN11/LOẠI48, BỎ QUA74 (16 timestamp mới).
MAR cho warmup quan sát được, chưa kết luận cơ chế tổng quát. Wilson/Fisher theo ô chỉ mô tả vì link/tick phụ thuộc. Chưa triển khai detector inference.
Báo cáo: ../../docs/phase-5/02-missing-data.md; JSON: missing_analysis.json; log: ../../logs/missing_analysis.log.

## Lesson5.3 — Thiết kế thí nghiệm

18 run dự kiến: 8train/10test; base rate test 27.1%; coverage giả thuyết 8/8link.
Test: 116 passed, 4 skipped. GATE PASS: True.
Đã có LinkAdminDown, seeded fault target và varying load cleanup process group; chưa thu18run hoặc train mô hình.
Báo cáo: ../../docs/phase-5/03-experiment-matrix.md; hợp đồng: experiment_matrix.json; timeline: experiment_matrix.png.

## Lesson5.4 — Harness chuẩn bị

Integrity match: True; 18plan,iperf75s,t_rel_end70s.
Test 152 passed, 4 skipped. Python hệ thống không nạp numpy/pandas/matplotlib.
Collector hook/metadata/monotonic, flatten tick check vàpre-roll đã triển khai; chưa thu chiến dịch hoặc có runner đầy đủ.
Báo cáo: ../../docs/phase-5/04-data-generation.md; JSON:phase54_prechecks.json; log:../../logs/phase54_prechecks.log.