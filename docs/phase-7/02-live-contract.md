# Phase 7.2 — Hợp đồng live của detector

## 1. Phát hiện được kiểm chứng

Các kiểm tra được chạy với `detector-release-1.0.0` đã đóng băng:

```text
snapshot không có run:
  tick 0 -> warming_up(warmup)
  tick 1.. -> unknown(collector_version)

tick normal -> ValueError: payload thieu truong truy vet: ['reason']
expected_entities(model) = 16
F-flood-h1_to_srv1: 8/28 tick act có reading.act=False
F-degrade-s1-s2: unknown(missing_data) tại tick 21 và 41
```

Kết luận:

- F7-1 được xác nhận: collector live thiếu `run.collector_version` khiến
  detector `unknown` vĩnh viễn sau warmup.
- `release.payload()` không thể tạo heartbeat ở tick normal, nên hợp đồng live
  cần `build_document()` riêng và dùng payload đóng băng làm oracle ở tick
  không normal.
- Snapshot phải đến từ một `Collector.run` riêng. Dùng vòng `sync_agent` sẽ
  đưa retry/HTTP vào chu kỳ lấy mẫu; đọc lại từ Ditto sẽ gặp giá trị cũ do
  merge-patch bỏ `None` và mất thay đổi nhỏ do differ.
- Producer tự khai `v3-qdisc-ratevalid`; hai nguồn đo được ghim SHA. Không
  chép version từ release sang snapshot.
- Topology phải khớp chính xác 16 entity model biết.
- Consumer hành động theo `decision.state`, không theo `evidence.actRule`, vì
  FSM có quán tính và 8/28 tick `act` không còn `actRule` tức thời.

## 2. Hợp đồng A — snapshot live

| Điều khoản | Yêu cầu |
|---|---|
| A0 | `Collector.run` riêng, interval 1 s, dùng chung `net_lock` với `sync_agent` |
| A1 | `t_source` là số hữu hạn |
| A2 | Tập entity khớp chính xác 16 entity của model |
| A3 | `run.collector_version` do producer cấp |
| A4 | Snapshot có `tick` |

A0 tái tạo đúng đường lấy mẫu từng tạo dữ liệu train: collector lấy snapshot
trực tiếp từ Mininet và không bị HTTP Ditto chặn. `bridge/collector.py` và
`twin/link_direction.py` lần lượt được ghim SHA-256
`f98979a82f8f347a227b2bddb81b00eb5081dedda442f01b2d7799979b4193cf`
và `046698b02895843e0d2b04f3457ddc9eca778bbc85ea52e55b6c06c27c83c7d2`.

## 3. Hợp đồng B — Thing `org.dt4n:detector`

Một PATCH nguyên tử chứa bốn feature:

```text
decision   state, cause, reason, detectedAt
evidence   envelopeValid, conservationValid, envelope, conservation,
           actRule, conservationSwitch, affected[], unattributed
freshness  bootId, seq, heartbeatAt, ttlTicks, tickIntervalMs, dropped
provenance modelVersion, artifactSha256, releaseVersion, releaseSha256,
           conservationSha256, collectorVersion
```

Bốn quyết định khác plan ban đầu:

1. `affected` thuộc evidence của tick hiện tại, không thuộc decision có quán tính.
2. Envelope và conservation có validity riêng.
3. FSM state trước guard chỉ vào audit local, không công bố lên Ditto.
4. Guard chỉ ghi đè `normal`, `suspect`, `act`; giữ nguyên `warming_up` và
   `unknown` có nguyên nhân nền tảng hơn.

Document không chứa `None`, vì JSON Merge Patch coi `null` là lệnh xóa. Khi
bootstrap, detector bắt đầu ở `unknown/never_started`, `seq=-1`, không bao giờ
giả vờ là normal.

## 4. Hợp đồng C — freshness và S12

1. PATCH freshness mỗi tick, kể cả normal.
2. Khóa sống là `(bootId, seq)`; restart sinh `bootId` mới.
3. Consumer tính TTL 3 giây bằng đồng hồ monotonic của chính nó.
4. Detector không công bố cờ `stale`.
5. Lần đầu thấy khóa chỉ ARM; chỉ khi khóa đổi mới CONFIRM còn sống.

Ngân sách trường hợp xấu nhất:

```text
TTL                              3000 ms
Ditto -> SSE p95                 1017 ms
chu kỳ kiểm tra consumer          250 ms
                                 -------
tổng                             4267 ms <= S12 5000 ms
biên còn lại                      733 ms
```

## 5. Kết quả niêm phong, kiểm thử và giới hạn

```text
Trước seal: 15 pass, 2 skip
Sau seal:   16 pass, 1 skip (golden live cần Mininet + Ditto)
Sau golden: 17 pass, 0 skip
Bootstrap Phase 2.5: 51 pass, 0 fail
Contract SHA-256: 6ff8b6e246abd90ff8468ecddeec7f9824e36f75a3399707b7bb02cddc3f9c9d
```

Golden được chụp từ Mininet + Ryu + Ditto thật sau commit niêm phong hợp đồng:

```text
file: test/fixtures/phase7_live_snapshots.jsonl
snapshots: 15 (tick 0..14)
entities/snapshot: 16
contract violations: 0
Delta t min/median/max: 1.000019 / 1.000073 / 1.000097 s
size: 116953 bytes
SHA-256: 00679dd4e5f17d1be899152395cdabca2d6b0870950ce5d563ae2f3c4c32a7d2
```

Giới hạn đã biết:

- Biên S12 chỉ khoảng 0.7 giây; độ trễ thật sẽ được đo lại ở 7.4/7.6.
- STALE không chứng minh process detector chết. Nó có thể do detector, luồng
  ghi, Ditto, SSE hoặc tab consumer bị chậm/ngắt.
- Heartbeat thêm một PATCH/s; chi phí so với delta sync hiện tại chưa được đo.
- Collector live sinh khoảng 8 KB/tick, xấp xỉ 700 MB/ngày; runner 7.3 phải
  rotation hoặc giới hạn dung lượng.
- Bootstrap scale sau thay đổi có thêm detector Thing, nên tổng kỳ vọng tăng
  từ 52 lên 53; evidence lịch sử không bị sửa.

Artifact máy đọc: `results/report/phase7_contract.json`.
