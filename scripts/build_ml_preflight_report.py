import json
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=root/'results/report'
def read(name):return json.loads((out/name).read_text())
s=read('ml_dataset_summary.json')
up=read('latency_up_randomized.json')['result']
cmd=read('latency_command_randomized.json')['result']
ack=read('command_ack_timeout3.json')
unit=ET.parse(out/'ml_preflight_pytest.xml').getroot().find('testsuite').attrib
security=ET.parse(out/'ml_security_live.xml').getroot().find('testsuite').attrib
passed=int(unit['tests'])-sum(int(unit[x]) for x in ['skipped','failures','errors'])
lines=['# Kiểm chứng trước Phase ML — dữ liệu v2','',
 f"Unit test: **{passed} passed, {unit['skipped']} skipped, {unit['failures']} failed, {unit['errors']} errors**. Live security: {security['tests']} test, {security['failures']} failed, {security['skipped']} skipped.",'',
 '## Các thay đổi đã hoàn tất','',
 '- Collector đọc `tc -j -s qdisc` trong namespace thật của từng interface, ở cả hai đầu link; chỉ cộng leaf qdisc để tránh đếm drop lặp giữa HTB và netem.',
 '- `lossPct` là tỷ lệ drop egress tại qdisc, tính từ delta drop và delta packet gửi. Giữ `interfaceLossPct` để đối chiếu. Không đại diện cho loss đường đi; không cộng thêm interface drop vào qdisc drop.',
 '- Mẫu warmup/unavailable/reset trả `lossPct: null`, `qdiscValid: false` và lý do; adapter gửi xóa loss cũ khi qdisc không hợp lệ. ML phải kiểm tra flag này.',
 '- Normal giới hạn TCP 2 Mbps/client; flood UDP 50 Mbps/client. Mọi client dùng hai server luân phiên; UDP srv1→srv2 2 Mbps giữ tải s2-s3. `run_sync` có profile normal/flood/server-only/idle.',
 '- TrafficFlood/CongestionShift dùng `run_host_shell` qua mnexec, không tranh shell tương tác host với collector. Đã chạy TrafficFlood trong lúc sync hoạt động.',
 '- Đo thêm độ trễ với jitter settle U(0,1s), seed 20260915; giữ số đo fixed-settle v1 riêng. Xác nhận reset up trước mỗi trial, ghi timeout và mẫu giây gốc.',
 '- Đã thử inbox `timeout=3` với correlation-id chỉ ở header và cả trong payload; giữ HTTP response/SSE gốc.',
 '- Bỏ Swagger/OpenAPI khỏi cây Git hiện tại và loại service docs khỏi Compose; 74 static asset còn giữ khớp source Ditto 3.9.1, có SHA-256, license/notice và attribution. Không viết lại lịch sử commit cũ.',
 '- README có lệnh tạo nginx.htpasswd từ example; audit timestamp đổi sang UTC có timezone.',
 '', '## Dữ liệu mạng thật','',
 '60 snapshot normal, 60 flood, 30 inject flood cùng Sync Agent. Mỗi dataset loại mẫu đầu khi tính delta. Tốc độ dưới đây là trung bình max(rxRate,txRate) theo snapshot, không phải tổng hai chiều.', '',
 '| Link | Normal (Mbps) | Flood (Mbps) | Max qdisc drop flood (%) | Interface loss flood (%) |',
 '|---|---:|---:|---:|---:|']
for key,n in s['normal_v2']['links'].items():
 f=s['flood_v2']['links'][key]
 lines.append(f"| {key} | {n['mean_peak_direction_mbps']:.2f} | {f['mean_peak_direction_mbps']:.2f} | {f['loss_max_pct']:.3f} | {f['mean_interface_loss_pct']:.3f} |")
lines+=['','### Gate feature','']
lines += [f"- `{key}`: **{value}**" for key,value in s['gates'].items()]
lines+=['',f"Runtime ERROR/CRITICAL: {len(s['runtime_error_lines'])} dòng. Số liệu và SHA-256 từng dataset ở [ml_dataset_summary.json](ml_dataset_summary.json).",
 '', '## Độ trễ fixed-settle và randomized-settle','',
 '| Phép đo | Cách đo | n | p50 (ms) | p95 (ms) | Timeout |', '|---|---|---:|---:|---:|---:|']
for label,name,typ in [('Đồng bộ lên','latency_up','fixed-settle v1'),('Đồng bộ lên','latency_up_randomized','randomized-settle v2'),
                       ('Lệnh vòng kín','latency_command','fixed-settle v1'),('Lệnh vòng kín','latency_command_randomized','randomized-settle v2')]:
 x=read(name+'.json')['result'];lines.append(f"| {label} | {typ} | {x['n']} | {x['p50_ms']:.2f} | {x['p95_ms']:.2f} | {x.get('timeouts',0)} |")
lines+=['', 'Fixed-settle 2s đồng bộ với nhịp scan 1s có thể làm sự kiện lặp cùng pha; số v1 chụm gần một chu kỳ phù hợp với cơ chế đó. Không có phép đo pha từng event nên không gọi v1 là giới hạn worst-case đã chứng minh. V2 thêm jitter, không ép kết quả theo một phân phối lý thuyết.',
 'Hai lần chạy cũng khác collector (v2 đọc qdisc), nên so sánh v1/v2 không cô lập riêng hiệu ứng khóa pha. Tải lúc đo v2 là UDP srv1→srv2 2 Mbps, client idle. Mẫu gốc/seed/period nằm trong latency_up_randomized.json và latency_command_randomized.json.',
 '', '## Biên nhận HTTP timeout=3','',
 '| Correlation-id trong payload | HTTP status | HTTP + kiểm tra phản ánh (s) | Twin về down |', '|---|---:|---:|---|']
for x in ack:lines.append(f"| {x['payload_correlation_id']} | {x['http_status']} | {x['http_elapsed_s']} | {x['reflected_down']} |")
lines+=['', 'SSE endpoint message trong lần chạy này chuyển payload mà không kèm protocol header correlation-id; clientCorrelationId trong payload giúp audit/dedup nhưng không tự tạo kênh trả lời Ditto Protocol.',
 'Agent POST sang HTTP outbox với timeout=0 tạo một thông báo mới. HTTP 202 của outbox xác nhận tiếp nhận thông báo, không chứng minh HTTP inbox đang chờ đã nhận response tương quan. Known limitation: transport SSE/HTTP hiện tại hỗ trợ điều khiển và xác nhận trạng thái qua twin, chưa cung cấp correlated reply cho timeout dương.',
 'Tài liệu chính thức phân biệt inbox/outbox gửi message và hướng dẫn WebSocket khi cần nhận/trả lời: [HTTP Messages API](https://eclipse.dev/ditto/httpapi-messages.html), [Messages Protocol](https://eclipse.dev/ditto/protocol-specification-things-messages.html). Response protocol phải giữ topic/correlation-id và có status. Không coi timeout=0 là biên nhận thực thi; phép đo vòng kín vẫn chờ mạng thật phản ánh.',
 'HTTP response/SSE gốc: [command_ack_timeout3.json](command_ack_timeout3.json).',
 '', '## File kết quả và bước tiếp theo','',
 '- Raw JSONL: `logs/ml_normal_v2.jsonl`, `ml_flood_v2.jsonl`, `ml_injection_v2.jsonl`.',
 '- `ml_dataset_summary.json`: thống kê, độ lệch chuẩn, gate và SHA-256.',
 '- `ml_qdisc_flood_raw.json`, `ml_normal_iperf.json`, `ml_flood_iperf.json`: kiểm tra nguồn tc và iperf.',
 '- `latency_up_randomized.json`, `latency_command_randomized.json`: 30 mẫu gốc mỗi phép và timeout.',
 '- `ml_preflight_pytest.xml`, `ml_security_live.xml`: kết quả test.',
 '- `logs/ml_preflight_runtime.log`, `ml_preflight_stdout.log`: log cả suite.',
 '- `ditto_asset_provenance.json`: source release và SHA-256 asset; license/notice ở `ditto/upstream/`.',
 '', 'Các gate trên chỉ chứng minh feature đã có tín hiệu và khác biệt giữa profile pilot. Chưa huấn luyện ML, chưa có train/test độc lập, chưa chứng minh recall/precision hoặc khả năng phân biệt trên tải chưa thấy. s2-s3 vẫn có tải cố định 2 Mbps; kiểm tra phương sai và chọn feature trước khi train. Dùng s1-s3 ở profile này không chứng minh failover tự động.',
 'Bước tiếp theo của ML cần thiết kế nhiều lần chạy/seed, mức tải normal đa dạng và các fault độc lập; chia train/test theo lần chạy để tránh leakage. Dữ liệu v1 giữ nguyên để đối chiếu, không trộn loss v1/v2 trực tiếp.']
(out/'ML_PREFLIGHT.md').write_text('\n'.join(lines)+'\n')
p=root/'SUMMARY.md'
old=p.read_text().split('\n## Bổ sung trước ML — v2')[0]
p.write_text(old+'\n## Bổ sung trước ML — v2\n\n'+
 f"Đã sửa nguồn loss, profile đa client, injection không tranh shell, đo pha ngẫu nhiên, kiểm tra timeout=3, giản lược Swagger và bổ sung attribution/README/UTC. Test hiện tại {passed} passed, {unit['skipped']} skipped; security live {security['tests']} pass. 60 normal + 60 flood + 30 inject; các gate feature đều đạt: {all(s['gates'].values())}.\n\n"+
 f"Độ trễ randomized-settle: đồng bộ p50/p95 {up['p50_ms']:.2f}/{up['p95_ms']:.2f} ms, lệnh {cmd['p50_ms']:.2f}/{cmd['p95_ms']:.2f} ms. HTTP timeout=3: {[x['http_status'] for x in ack]}, trạng thái vẫn phản ánh {[x['reflected_down'] for x in ack]}.\n\n"+
 'Báo cáo, bảng so sánh và giới hạn: [ML_PREFLIGHT.md](results/report/ML_PREFLIGHT.md). JSON: [ml_dataset_summary.json](results/report/ml_dataset_summary.json). Đây là kiểm chứng dữ liệu trước ML, chưa huấn luyện mô hình.\n')
print(out/'ML_PREFLIGHT.md')
