# Phase 7.6 — Ổn định live, race S11, contention và soak

## 0. Hiệu chỉnh Phase 7.5 bằng v2

Bản v1 được giữ nguyên. `phase7_e2e_latency_v2.json` chỉ thay hai trường chẩn
đoán qua `supersedes_field_only`; dữ liệu gốc và verdict không đổi. Lỗi v1 là
lấy `(tA-tick trước)/span`, trong khi chính `net_lock` kéo dài `span`, và một
tick có thể nằm trong `(tA,tB]`. Vì thế pha bị nén về 0 và span 2 s bị diễn giải
sai thành mất tick. Pha danh nghĩa v2 là `(tA-tick trước) mod 1 s`, cho phân bố
quý `[4,11,3,7]`; ba trial 4, 11, 24 có tick trong cửa sổ lệnh.

Đây là sửa định nghĩa hợp lệ vì verdict không đổi, dữ liệu thô không đổi, lý do
kiểm chứng độc lập từ vòng lặp Collector, và v1 vẫn tồn tại. Một sửa đổi làm số
đẹp hơn nhưng không thỏa cả bốn điều kiện sẽ là chỉnh hậu nghiệm và không được
phép.

Khi sắp `phys_obs` theo offset, snapshot đầu bắt được khi flood chiếm hơn khoảng
50–58% chu kỳ. Offset 0.053/0.082 cho 615/583 ms; offset 0.162/0.233 trượt
snapshot đầu và cho 1502/1433 ms. Rate trung bình chu kỳ làm loãng flood mới,
trong khi envelope cần nhiều cột cùng vượt biên.

## 1. S11: ba nhánh và verdict

Thí nghiệm dùng admin-down s1-s2 hoặc s1-s3, mỗi rep có thứ tự ngẫu nhiên:

- `log_first`: ghi InterventionLog trước rồi POST lệnh — treatment đúng WAL.
- `log_late`: POST, đợi detector đã chấm hậu quả rồi mới ghi — đối chứng âm.
- `no_log`: POST không ghi — chứng minh hành động thực sự có thể gây act.

Phát lại offline đã cho: `log_first` khoảng 21 tick suppressed và 0 act;
`log_late` một alarm nhưng 0 act; `no_log` một lần vào act. Kết quả live sẽ
được điền từ `phase7_s11_live.json` sau khi commit dự đoán.

## 2. Race và debounce

Chỉ POST rồi ghi ngay sau đó không ép được race vì command-agent xử lý bất đồng
bộ. Nhánh `log_late` đợi một tick hậu quả đã được detector đọc, tạo quan hệ
happens-before tất định. `n_act=2` là bộ đệm: một tick chưa suppress có thể tạo
suspect, rồi log tới trước tick kế tiếp reset bộ đếm, nên dự kiến không vào act.
Điều này không thay thế quy tắc bắt buộc “ghi trước, làm sau”.

## 3. Lease và fail noisy

Can thiệp mở chỉ suppress tối đa `MAX_OPEN_S=120`. Sau expiry, gate yêu cầu
`stale_intervention` xuất hiện trong 2 s và không còn tick suppressed. Published
có thể vẫn `normal` vì dữ liệu train s1008 chứa luồng chết hoàn toàn ở biên dưới
envelope bằng 0; gate không đòi alarm quay lại. Dashboard đã được sửa để cause
khác rỗng không bao giờ được tuyên bố “All systems normal”.

## 4. Residual trong can thiệp

Residual/conservation không bị InterventionLog suppress theo amendment 8. Báo
cáo riêng đếm `residual_only` và `held` trong các nhánh `log_first`; S11 yêu cầu
không có lần vào act do các tick này.

## 5. Contention ABBA và S5

Thiết kế ON, OFF, OFF, ON giữ nguyên Mininet, sync-agent, command-agent, Ditto và
Chromium; OFF vẫn chạy cùng Collector nhưng callback rỗng. So sánh gồm p95
`cycle_scan_ms`, nhịp tick, gap, CPU process và log overrun. S5 đo đúng
`observe()+step()` và lấy p95 của block ON xấu nhất để so với 50 ms và số offline
6R 0.943 ms.

## 6. Soak và dự đoán khóa trước live

| Chỉ số | Dự đoán trước live |
|---|---:|
| `log_first` act entries | 0/4 |
| `log_first` suppressed | khoảng 20 tick/lần |
| residual-only p50 / max | 0 / ≤2 tick |
| `log_late` alarm / act | khoảng 1 / 0 mỗi lần |
| `no_log` có act | ít nhất 3/4 lần |
| lease stale sau expiry | ≤1 tick; published có thể normal |
| S5 live p95 | 1–3 ms, dưới 50 ms |
| chênh p95 cycle scan ON–OFF | <5 ms |
| tick trễ / gap | khoảng 0 ở cả hai |
| CPU ON−OFF | +0.3–1 điểm phần trăm |
| ΔRSS sau 30 phút | <1 MiB; slope nửa sau gần 0 |
| ERROR/CRITICAL | 0 |

Soak lấy RSS hiện tại từ `/proc/self/statm`, bắt đầu sau warmup, lấy mẫu 30 s,
đo slope nửa sau và kiểm tra UI vẫn FRESH. Bảng live S11, ABBA và soak sẽ được
cập nhật sau ba campaign chạy tuần tự.

## 7. Giới hạn

- Suppression so sánh wall clock; controller và collector phải cùng máy hoặc có
  nguồn thời gian đồng bộ không step trong can thiệp.
- InterventionLog hiện là bộ nhớ cùng process, không phải IPC đa tiến trình và
  không được thiết kế cho nhiều writer.
- RSS là của process tích hợp gồm detector, collector và đối tượng Mininet.
- Journal MongoDB/Ditto có thể tăng dài hạn; 30 phút không đủ kết luận.
- S11 chỉ thử một loại hành động admin-down trên hai link backbone.

## 8. Kết quả live (sau commit dự đoán `b30fee8`)

Môi trường: Ryu `controller_static` (env `sdn_net`) khởi động riêng trước mỗi
campaign (vì `close(cleanup_mn=True)` gọi `mn -c`, lệnh này kill cả `ryu-manager`),
Ditto stack `dt4n-aoi-smoke`, vite dev server, Chromium headless. Lần chạy S11 đầu tiên
treo vì chưa có controller ở 6653 và không sinh artifact nào; đã dừng và chạy lại.

### 8.1 S11 live — `phase7_s11_live.json` (seed 7006, 4 rep × 3 nhánh + lease)

| Nhánh | n | act entries | alarm entries | env_alarm | suppressed | bắt đầu từ normal |
|---|---:|---:|---:|---:|---:|---|
| `log_first` | 4 | **0** | 0 | 0 | 84 (21/lần) | 4/4 |
| `log_late` | 4 | 4 | 4 | 8 (2/lần) | 84 | 4/4 |
| `no_log` | 4 | 4 | 4 | 85 | 0 | 4/4 |

Verdict: `S11_live_pass = true`, `race_negative_shows_alarm = true`,
`control_shows_act = true`, `lease_pass = true`, ERROR/CRITICAL = 0 (2 WARNING).
`log_first` và `no_log` khớp từng tick với bản phát lại offline
(`{suppressed 21, normal 17}` và `{act 1, env_alarm 21, held 2, normal 15}`).

**Dự đoán sai: `log_late` act = 0.** Cả 4 lần đều vào act. Nguyên nhân là lỗi của
harness, không phải của FSM: `LiveController._wait_consequence` lọc `seq > seq_before`,
trong khi `runner.seq` là seq **sắp** được gán. Tick đầu tiên được chấm sau quyết định
(`seq == seq_before`) bị bỏ qua, nên log thực chất trễ **2 tick** (đo được
`t_log − t_post` = 1.13–1.69 s), đủ để `n_act = 2` vào act. Test offline không bắt được
vì `FakeRunner.seq = 10` nhưng tick lại đặt ở seq 11.

Artifact chính được giữ nguyên, vì nó được sinh bởi code đúng như đã commit. Lỗi đã sửa
(`>=`, kèm test hồi quy `test_controller_log_late_counts_first_tick_scored_after_decision`,
test này fail trên code cũ). Đã chạy bổ sung **chỉ nhánh `log_late`** →
`phase7_s11_live_offbyone_fix.json`: 4/4 lần cho **alarm 1, act 0, env_alarm 1,
suppressed 21, normal 17**, và `t_log − t_post` = 0.68–1.03 s (trễ 1 tick). Timeline của
rep 0: tick seq 10 (`act_rule = true`) → `suspect`; từ seq 11 trở đi đều
`suppressed_intervention`. Như vậy luận điểm §2 (log trễ dưới 2 tick chỉ gây suspect)
được xác nhận live; luận điểm bổ sung là **log trễ 2 tick thì vào act**. Từ lần này,
row của S11 lưu thêm `ticks` (timeline trong cửa sổ) để chẩn đoán được cơ chế.

**Lease:** `stale_intervention` xuất hiện 0.29 s sau khi hết hạn (tick đầu tiên),
8 tick sau hạn mang cause này (cửa sổ quan sát sau hạn khoảng 8 s), 0 tick bị suppress sau hạn (120 tick trước hạn).
`published` sau hạn là `{act, suspect}`: báo động **có** quay lại trong lần chạy này.
Gate không đòi điều đó (§3, di sản s1008), và đây chỉ là một lần quan sát.

### 8.2 Residual — `phase7_residual_intervention.json`

`residual_only` theo từng lần `log_first` là `[0, 0, 0, 0]` (p50 0, max 0); `held` là
`[0, 0, 0, 0]`. Không có lần vào act nào đến từ residual. Khớp dự đoán 0 / ≤ 2.

### 8.3 Contention ABBA — `phase7_contention.json` (block 300 s)

| Block | tick | Δt p95 (ms) | trễ >1.05 s | gap >1.5 s | cycle_scan p50/p95 (ms) | CPU % | overran | S5 p95 (ms) |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| ON | 300 | 1004.9 | 0 | 0 | 67.3 / 72.7 | 3.57 | 0 | 1.621 |
| OFF | 300 | 1003.7 | 0 | 0 | 67.5 / 70.6 | 3.21 | 0 | — |
| OFF | 300 | 1003.9 | 0 | 0 | 68.5 / 72.2 | 3.25 | 0 | — |
| ON | 300 | 1003.8 | 0 | 0 | 70.0 / 73.5 | 3.53 | 0 | 1.640 |

- **S5 live p95 (block xấu nhất) = 1.64 ms ≤ 50 ms → PASS**, trong khoảng dự đoán
  1–3 ms. Cao hơn số 0.943 ms của 6R (offline, chỉ detector), cùng định nghĩa
  `observe() + step()`.
- p95 `cycle_scan` trung bình: ON 73.1 ms, OFF 71.4 ms → chênh **+1.7 ms** (< 5 ms).
- CPU tiến trình: ON 3.55 %, OFF 3.23 % → **+0.32 điểm %** (dự đoán +0.3–1).
- Tick trễ / gap / `Cycle overran`: 0 ở cả hai điều kiện. ERROR = 0 (4 WARNING).
- Xu hướng theo thời gian nhỏ so với hiệu ứng: hai block OFF chênh 1.6 ms p95.

### 8.4 Soak 30 phút — `phase7_soak_live.json`

- **S6 = FAIL theo định nghĩa đăng ký trước:** ΔRSS = **2.77 MiB** (> 1 MiB), độ dốc
  nửa sau **66.9 KiB/phút**, peak 95.3 MiB. Dự đoán (< 1 MiB, dốc ≈ 0) sai.
- ERROR/CRITICAL = 0 → PASS. UI cuối soak: `fresh`. Runner: 1808 seq, 0 failed,
  0 overwritten, 0 restart, 0 exception; `on_tick` p95 2.06 ms; ghi Ditto p95 7.9 ms.
- S5 trên toàn soak: p95 1.62 ms, max 1.80 ms. Nhịp tick: 0 trễ, 0 gap, Δt max 1022 ms.
- RSS toàn hệ (điều kiện triển khai, không phải SLO): mongod 203 → 225 MiB,
  container MongoDB 229 → 251 MiB trong 30 phút (journal Ditto; §7 giới hạn).

**Chẩn đoán (không đổi verdict).** RSS tăng gần tuyến tính suốt 30 phút, không có bậc,
khoảng 1.1 KiB/tick. `DetectorRunner.timeline` và `.writes` là deque có giới hạn
(`TIMELINE_SAMPLES = 4096`), nhưng 30 phút chỉ có 1808 tick: deque **chưa đầy** trong
suốt soak, và phải khoảng 68 phút mới chạm trần. Đo offline, riêng các deque của runner
tốn khoảng **1.0 KiB/tick** (1.79 MiB cho 1800 tick, trần ≈ 4.1 MiB). Soak chẩn đoán
có `tracemalloc` (`phase7_soak_live_tracemalloc.json`, tag riêng, không đè artifact
chính): phần tăng heap Python lớn nhất là `bridge/detector_runner.py` **+1725 KiB**
(≈ 0.95 KiB/tick); mọi file khác cộng lại khoảng +0.3 MiB. RSS của lần chạy đó
(5.4 MiB) bị `tracemalloc` thổi phồng (hiệu ứng đầu dò), nên không dùng làm số S6.

Kết luận: bằng chứng chỉ ra việc **lấp đầy ring buffer có giới hạn**, không phải rò bộ
nhớ. Nhưng điều này **chưa được chứng minh**, vì chưa quan sát được RSS phẳng lại sau khi
deque đầy. Muốn xác nhận cần soak dài hơn 68 phút (ví dụ 90 phút) và thấy độ dốc về 0
sau khoảng tick 4096. Ngoài ra, trần thiết kế của hai deque (khoảng 4 MiB) tự nó đã
vượt ngưỡng S6 = 1 MiB. Nghĩa là một soak 30 phút với ngưỡng 1 MiB **không thể đạt**
với thiết kế runner 7.3, dù có rò hay không. Cần quyết định ở 7.7: giảm trần deque hay
định nghĩa lại S6 theo độ dốc sau khi deque đầy. Đây là quyết định trước khi đo lại,
không phải chỉnh hậu nghiệm.

### 8.5 Đối chiếu dự đoán

| Chỉ số | Dự đoán | Đo được | |
|---|---|---|---|
| `log_first` act | 0/4 | 0/4 | ✅ |
| `log_first` suppressed | ~20/lần | 21/lần | ✅ |
| residual-only p50 / max | 0 / ≤2 | 0 / 0 | ✅ |
| `log_late` alarm / act | ~1 / 0 | 1 / **1** (harness lỗi, trễ 2 tick); bản sửa: 1 / 0 | ❌ → ✅ bổ sung |
| `no_log` act | ≥3/4 | 4/4 | ✅ |
| lease stale sau hạn | ≤1 tick | tick đầu, 0.29 s | ✅ |
| lease published sau hạn | có thể normal | act/suspect | (không phải gate) |
| S5 live p95 | 1–3 ms | 1.64 ms | ✅ |
| cycle_scan ON−OFF | <5 ms | +1.7 ms | ✅ |
| tick trễ / gap | ~0 | 0 / 0 | ✅ |
| CPU ON−OFF | +0.3–1 | +0.32 | ✅ |
| ΔRSS 30 phút | <1 MiB, dốc ≈0 | 2.77 MiB, 66.9 KiB/phút | ❌ |
| ERROR/CRITICAL | 0 | 0 | ✅ |
