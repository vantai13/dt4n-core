# Kiểm chứng trước Phase ML — dữ liệu v2

Unit test: **29 passed, 4 skipped, 0 failed, 0 errors**. Live security: 4 test, 0 failed, 0 skipped.

## Các thay đổi đã hoàn tất

- Collector đọc `tc -j -s qdisc` trong namespace thật của từng interface, ở cả hai đầu link; chỉ cộng leaf qdisc để tránh đếm drop lặp giữa HTB và netem.
- `lossPct` là tỷ lệ drop egress tại qdisc, tính từ delta drop và delta packet gửi. Giữ `interfaceLossPct` để đối chiếu. Không đại diện cho loss đường đi; không cộng thêm interface drop vào qdisc drop.
- Mẫu warmup/unavailable/reset trả `lossPct: null`, `qdiscValid: false` và lý do; adapter gửi xóa loss cũ khi qdisc không hợp lệ. ML phải kiểm tra flag này.
- Normal giới hạn TCP 2 Mbps/client; flood UDP 50 Mbps/client. Mọi client dùng hai server luân phiên; UDP srv1→srv2 2 Mbps giữ tải s2-s3. `run_sync` có profile normal/flood/server-only/idle.
- TrafficFlood/CongestionShift dùng `run_host_shell` qua mnexec, không tranh shell tương tác host với collector. Đã chạy TrafficFlood trong lúc sync hoạt động.
- Đo thêm độ trễ với jitter settle U(0,1s), seed 20260915; giữ số đo fixed-settle v1 riêng. Xác nhận reset up trước mỗi trial, ghi timeout và mẫu giây gốc.
- Đã thử inbox `timeout=3` với correlation-id chỉ ở header và cả trong payload; giữ HTTP response/SSE gốc.
- Bỏ Swagger/OpenAPI khỏi cây Git hiện tại và loại service docs khỏi Compose; 74 static asset còn giữ khớp source Ditto 3.9.1, có SHA-256, license/notice và attribution. Không viết lại lịch sử commit cũ.
- README có lệnh tạo nginx.htpasswd từ example; audit timestamp đổi sang UTC có timezone.

## Dữ liệu mạng thật

60 snapshot normal, 60 flood, 30 inject flood cùng Sync Agent. Mỗi dataset loại mẫu đầu khi tính delta. Tốc độ dưới đây là trung bình max(rxRate,txRate) theo snapshot, không phải tổng hai chiều.

| Link | Normal (Mbps) | Flood (Mbps) | Max qdisc drop flood (%) | Interface loss flood (%) |
|---|---:|---:|---:|---:|
| link-h1-s1 | 2.16 | 20.00 | 62.931 | 0.000 |
| link-h2-s1 | 2.16 | 20.00 | 62.929 | 0.000 |
| link-h3-s1 | 2.15 | 19.85 | 62.931 | 0.000 |
| link-s1-s2 | 4.30 | 20.00 | 50.030 | 0.000 |
| link-s1-s3 | 2.15 | 20.00 | 0.000 | 0.000 |
| link-s2-s3 | 2.16 | 2.16 | 0.000 | 0.000 |
| link-s2-srv1 | 4.30 | 20.00 | 0.000 | 0.000 |
| link-s3-srv2 | 4.30 | 20.00 | 9.781 | 0.000 |

### Gate feature

- `normal_flood_have_60_snapshots`: **True**
- `all_8_links_active_in_normal`: **True**
- `all_clients_flood_rate_exceeds_normal_2x`: **True**
- `flood_qdisc_loss_observed`: **True**
- `injection_qdisc_loss_observed`: **True**
- `all_v2_qdisc_samples_valid_after_warmup`: **True**

Runtime ERROR/CRITICAL: 0 dòng. Số liệu và SHA-256 từng dataset ở [ml_dataset_summary.json](ml_dataset_summary.json).

## Độ trễ fixed-settle và randomized-settle

| Phép đo | Cách đo | n | p50 (ms) | p95 (ms) | Timeout |
|---|---|---:|---:|---:|---:|
| Đồng bộ lên | fixed-settle v1 | 30 | 992.31 | 1049.34 | 0 |
| Đồng bộ lên | randomized-settle v2 | 30 | 682.14 | 1017.11 | 0 |
| Lệnh vòng kín | fixed-settle v1 | 30 | 1002.51 | 1035.48 | 0 |
| Lệnh vòng kín | randomized-settle v2 | 30 | 674.70 | 984.19 | 0 |

Fixed-settle 2s đồng bộ với nhịp scan 1s có thể làm sự kiện lặp cùng pha; số v1 chụm gần một chu kỳ phù hợp với cơ chế đó. Không có phép đo pha từng event nên không gọi v1 là giới hạn worst-case đã chứng minh. V2 thêm jitter, không ép kết quả theo một phân phối lý thuyết.
Hai lần chạy cũng khác collector (v2 đọc qdisc), nên so sánh v1/v2 không cô lập riêng hiệu ứng khóa pha. Tải lúc đo v2 là UDP srv1→srv2 2 Mbps, client idle. Mẫu gốc/seed/period nằm trong latency_up_randomized.json và latency_command_randomized.json.

## Biên nhận HTTP timeout=3

| Correlation-id trong payload | HTTP status | HTTP + kiểm tra phản ánh (s) | Twin về down |
|---|---:|---:|---|
| False | 408 | 3.022 | True |
| True | 408 | 3.021 | True |

SSE endpoint message trong lần chạy này chuyển payload mà không kèm protocol header correlation-id; clientCorrelationId trong payload giúp audit/dedup nhưng không tự tạo kênh trả lời Ditto Protocol.
Agent POST sang HTTP outbox với timeout=0 tạo một thông báo mới. HTTP 202 của outbox xác nhận tiếp nhận thông báo, không chứng minh HTTP inbox đang chờ đã nhận response tương quan. Known limitation: transport SSE/HTTP hiện tại hỗ trợ điều khiển và xác nhận trạng thái qua twin, chưa cung cấp correlated reply cho timeout dương.
Tài liệu chính thức phân biệt inbox/outbox gửi message và hướng dẫn WebSocket khi cần nhận/trả lời: [HTTP Messages API](https://eclipse.dev/ditto/httpapi-messages.html), [Messages Protocol](https://eclipse.dev/ditto/protocol-specification-things-messages.html). Response protocol phải giữ topic/correlation-id và có status. Không coi timeout=0 là biên nhận thực thi; phép đo vòng kín vẫn chờ mạng thật phản ánh.
HTTP response/SSE gốc: [command_ack_timeout3.json](command_ack_timeout3.json).

## File kết quả và bước tiếp theo

- Raw JSONL: `logs/ml_normal_v2.jsonl`, `ml_flood_v2.jsonl`, `ml_injection_v2.jsonl`.
- `ml_dataset_summary.json`: thống kê, độ lệch chuẩn, gate và SHA-256.
- `ml_qdisc_flood_raw.json`, `ml_normal_iperf.json`, `ml_flood_iperf.json`: kiểm tra nguồn tc và iperf.
- `latency_up_randomized.json`, `latency_command_randomized.json`: 30 mẫu gốc mỗi phép và timeout.
- `ml_preflight_pytest.xml`, `ml_security_live.xml`: kết quả test.
- `logs/ml_preflight_runtime.log`, `ml_preflight_stdout.log`: log cả suite.
- `ditto_asset_provenance.json`: source release và SHA-256 asset; license/notice ở `ditto/upstream/`.

Các gate trên chỉ chứng minh feature đã có tín hiệu và khác biệt giữa profile pilot. Chưa huấn luyện ML, chưa có train/test độc lập, chưa chứng minh recall/precision hoặc khả năng phân biệt trên tải chưa thấy. s2-s3 vẫn có tải cố định 2 Mbps; kiểm tra phương sai và chọn feature trước khi train. Dùng s1-s3 ở profile này không chứng minh failover tự động.
Bước tiếp theo của ML cần thiết kế nhiều lần chạy/seed, mức tải normal đa dạng và các fault độc lập; chia train/test theo lần chạy để tránh leakage. Dữ liệu v1 giữ nguyên để đối chiếu, không trộn loss v1/v2 trực tiếp.
