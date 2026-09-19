# Phase 7.3 — Async detector runner

## 1. Kiến trúc hai luồng

```text
COLLECTOR THREAD (1 Hz, không gọi mạng)
Collector.run -> contract A -> scorer -> FSM -> guard -> document -> audit
                                                               |
                                                        mailbox một ô
                                                               |
WRITER THREAD                                                  v
take latest -> một PATCH, timeout 2 s, không retry -> sent/failed
```

Luồng đo và luồng ghi là hai bulkhead. Callback collector chỉ làm công việc
cục bộ có giới hạn rồi `Mailbox.put()`, thao tác này không bao giờ chờ HTTP.
Audit đầy đủ được ghi trực tiếp trong luồng collector; twin chỉ nhận trạng thái
mới nhất qua mailbox.

Golden 7.2 được replay qua release thành một tick `warming_up` rồi 14 tick
`normal`. Δt nằm trong 1.000019–1.000097 s, `cycle_scan_ms` nằm trong
67.906–76.669 ms, và `run.git_hash=aa525c6…`, đúng commit đã niêm phong hợp
đồng trước khi chụp fixture.

## 2. Vì sao mailbox một ô

Document detector là state hiện tại, không phải event phải giao đủ. Nếu dùng
hàng đợi tám ô khi mỗi PATCH chậm 5 giây, Little's law cho độ cũ tiềm năng:

```text
8 document × 5 s/document = 40 s
```

Sau khi Ditto hồi phục, hàng đợi sẽ phát lại các state cũ với `seq` liên tục
tăng, làm consumer tưởng dữ liệu cũ là heartbeat mới. Mailbox một ô gộp các
state trung gian, chỉ giao bản mới nhất và tăng `overwritten` cho mọi bản bị đè.

`dropped = overwritten + failed`, tức số tick có document không bao giờ tới
Ditto. Lịch sử đầy đủ vẫn còn trong audit local.

## 3. Vì sao không dùng retry của pusher

Pusher chung có thể giữ một state cũ khoảng:

```text
4 request × timeout 5 s + backoff 1+2+4 s ≈ 27 s
```

Retry state cũ là sai khi đã có state mới hơn. Runner dùng transport riêng:
một PATCH, timeout `WRITE_TIMEOUT_S=2.0`, không retry. Timeout nhỏ hơn TTL 3 s;
tick tiếp theo chính là lần gửi state mới hợp lệ.

## 4. Ma trận lỗi và supervision

| Sự cố | Runner xử lý | Consumer thấy |
|---|---|---|
| Ditto chậm | Collector tiếp tục; mailbox gộp state | STALE rồi state mới nhất |
| Ditto chết | PATCH fail, `failed` tăng | STALE |
| Scorer exception | Tạo scorer/FSM/guard và `bootId` mới | restart + warming_up |
| Collector exception | Supervisor chờ 1 s rồi tạo incarnation mới | STALE ngắn rồi warming_up |
| Topology lạ | `FatalContract`, ngừng heartbeat | STALE vĩnh viễn + ERROR |
| Hơn 5 exception/60 s | `CrashLoop`, ngừng reset | STALE + ERROR |
| Dừng chủ động | `StopRunner` ở tick kế tiếp | STALE sau TTL |

Stream state được tạo lại qua `release.build()`. `InterventionLog` là world
state nên giữ nguyên qua restart.

Bug hồi quy đã được ghim bằng test: tick đầu là `warming_up`, vì vậy
`detectedAt` phải dùng `self.detected_at or now`. Nếu để rỗng, oracle ném lỗi
mỗi tick và cơ chế restart cũ sẽ tạo crash-loop im lặng. Runner hiện dừng hẳn
sau exception thứ sáu trong 60 giây.

## 5. Thí nghiệm offline và prereg live

Thí nghiệm offline phát lại flood với Ditto giả chậm 5 giây/PATCH trong cửa sổ
logic `[18,32)`, đúng lúc fault bắt đầu:

| Chỉ số | Sync | Async runner |
|---|---:|---:|
| Tick được xử lý | 48/60 | 60/60 |
| Tick bị mất | 12 | 0 |
| Tick mất trong fault window | 10 | 0 |
| Collector overrun | 3 | 0 |
| Document tới Ditto | 48 | 48 |
| `act` tới Ditto | 15 | 19 |
| `unknown(gap)` tới Ditto | 3 | 0 |
| p95 `on_tick` | 1.623 ms | 1.706 ms |
| Document bị gộp/thất bại | 0 | 12 |

Artifact offline SHA-256:
`6b8a62c43a4ef0f94f85dfa13e48fc78cc7280c211c09b378c2cf786bd5483a4`.

### Dự đoán live — ghi trước khi chạy chaos test

| Chỉ số | Dự đoán | Lý do |
|---|---:|---|
| `dt_over_1_5_s` | 0 | Collector detector không chờ HTTP |
| `dt_max_s` | khoảng 1.0x s | chỉ có jitter thu thập bình thường |
| `published_gap_unknown` | 0 | không có sampling gap |
| `stats.failed` | khoảng 2–3 | pause 5 s, timeout mỗi PATCH 2 s |
| `stats.overwritten` | khoảng 2–3 | tick mới đè state lúc writer đang chờ |
| sync-agent log | có cảnh báo mạng/retry | sync-agent vẫn dùng đường HTTP đồng bộ |

Dự đoán này được commit trước khi pause container Ditto.

## 6. Giới hạn

- Thí nghiệm offline dùng Ditto giả và nén thời gian; chi phí CPU scorer không
  nén nên phép đo thiên về bi quan.
- Chưa đo runner dưới tranh chấp CPU dài hạn; việc đó thuộc Lesson 7.6.
- Lịch sử state trung gian trên twin bị gộp; lịch sử đầy đủ chỉ có trong audit.
- `WRITE_TIMEOUT_S=2.0` là tham số vận hành mới, không phải tham số mô hình.
- Live audit xoay vòng 50 MiB × 3; giới hạn dung lượng đổi lấy lịch sử hữu hạn.
- 15 tick golden chứng minh hợp đồng nhưng chưa chứng minh false-positive rate;
  soak 30 phút ở 7.6 mới trả lời câu hỏi đó.

Kết quả live sẽ được bổ sung sau khi chạy, không sửa bảng dự đoán phía trên.

### Kết quả live — chạy sau commit `dab2ccd`

Chaos test pause `dt4n-aoi-smoke-nginx-1` từ 20.0003 đến 25.0666 giây.
Container đã được unpause và trở lại trạng thái running sau phép đo.

| Chỉ số | Dự đoán | Đo được | Đối chiếu |
|---|---:|---:|---|
| `dt_over_1_5_s` | 0 | **0** | khớp |
| `dt_max_s` | khoảng 1.0x s | **1.000129 s** | khớp |
| `published_gap_unknown` | 0 | **0** | khớp |
| `stats.failed` | khoảng 2–3 | **2** | khớp |
| `stats.overwritten` | khoảng 2–3 | **1** | thấp hơn dự đoán một tick |
| sync-agent | cảnh báo/retry | **`Cycle overran: 4.82s > 1.0s`** | khớp |

Runner xử lý đủ 60 tick: một `warming_up`, 59 `normal`, 57 PATCH thành công,
hai PATCH thất bại và một document bị mailbox đè. Không restart, không
exception, không vi phạm hợp đồng và guard không bật. p95 toàn callback
`on_tick` là 2.756 ms; phần đo/scorer trước build document trong audit có p95
1.677 ms. Writer p95 trên các PATCH thành công là 20.695 ms.

Kết quả chứng minh đường sync-agent bị block gần năm giây trong lúc đường đo
detector vẫn giữ Δt dưới 1.001 giây. Artifact live content SHA-256:
`d61b83fd1be68ac79d8c76d1e72fbfc1285d5797d3f7ccc1652bae9da761033a`.

Artifact máy đọc nằm tại
`results/report/phase7_runner_backpressure_live.json`; audit đầy đủ 60 tick
nằm cục bộ tại `logs/phase7_detector_audit.jsonl` và không commit vì là runtime
state có cơ chế rotation.
