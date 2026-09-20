# Phase 8.4 — Đóng vòng: runtime, reconcile và các chế độ hỏng

Nhánh `phase/8-closed-loop`. Đây là lesson đầu tiên có `controller/runner.py`:
từ đây hệ thật sự là vòng kín.

---

## 1. Edge cho quyết định, level cho duy trì

| | Edge-triggered | Level-triggered |
|---|---|---|
| Phản ứng với | sự kiện thay đổi | trạng thái hiện tại |
| Bỏ lỡ một sự kiện | sai **vĩnh viễn** | tự sửa ở nhịp sau |
| Dùng ở đây cho | **chọn mục tiêu** (latch tại sườn lên) | **thực thi** (`bw` có đang bằng 7 không?) |

Vì sao phần thực thi phải là level: trong hệ này sự kiện **có thể mất ở bốn chỗ
đã biết**, và mất sự kiện là chuyện bình thường, không phải bug:

| Chỗ mất | Bằng chứng |
|---|---|
| mailbox **ghi đè** bản cũ khi writer chậm | `detector_runner.py:56,61` (`overwritten`) |
| PATCH **không retry** | `DittoTransport` — *"PATCH một lần, không retry"* (`:74`) |
| SSE reconnect có thể trả bản cũ | lý do `MonotonicFreshness` tồn tại (7.4) |
| R3 **bỏ cả bản tin** khi seq lùi | `TwinReader.apply` → `dropped += 1` |

Vì sao phần chọn mục tiêu phải là edge: **recovery burst** (8.1) — nạn nhân h3
vọt lên 18,4 Mbps ở tick 46 và vào `affected`; đánh giá lại mỗi tick sẽ bóp nhầm
nạn nhân.

Hợp đồng giữa hai phần là `desired_bw(cstate, params)` — viết sẵn từ 8.2, giờ mới
có vòng gọi.

## 2. Lũy đẳng chưa đủ: phải **không tác dụng phụ khi lặp**

| Tính chất | `h_set_bandwidth` trước 8.4 |
|---|---|
| **Idempotent** (kết quả cuối sau n lần = sau 1 lần) | ✅ `dt4n_bw` luôn bằng giá trị yêu cầu |
| **Không tác dụng phụ khi lặp** | ❌ `intf.config()` dựng lại qdisc mỗi lần → bộ đếm về 0 → 1 tick `unknown(missing_data)` (F8-6, đã đo ở 8.3) |

Hợp đồng C (8.3) chỉ đòi cái thứ nhất; vòng reconcile (8.4) đòi **cả hai**. Gửi
lại mỗi 5 s mà không vá = **một tick mù mỗi 5 giây**, chồng lên 97% đã có.

Bản vá ở `bridge/command_agent.py`: no-op khi `dt4n_bw` đã bằng giá trị yêu cầu
(vẫn gia hạn lease). Khoá bằng test đếm số lần gọi `intf.config`:
`test_lap_lai_khong_dung_lai_qdisc` và hồi quy `test_doi_gia_tri_van_ap_dung`.

## 3. Nguyên tắc ba trạng thái và trễ quan sát

```
have = observed.get(link)
if have is None:            -> CHƯA BIẾT ≠ SAI, không hành động
if now - last_send < 2.0 s  -> TRỄ QUAN SÁT ≠ TRÔI GIÁ TRỊ, không hành động
if |have - want| > 0.01     -> trôi thật, gửi lại
```

`CONFIRM_GRACE_S = 2.0` không phải số tròn: nó lớn hơn p95 của trễ xác nhận đủ
đường đo ở §6 (1,003 s) cộng một tick. **Phát hiện từ lần chạy live đầu tiên:**
không có cửa sổ ân hạn này, mỗi lần can thiệp sinh thêm **1 lệnh thừa** vì twin
còn báo giá trị cũ trong ~1 tick (lần chạy đó: `drift_fixes = 4` cho 4 lần inject).

## 4. Bulkhead: controller **không** chạy trong callback của collector

`DetectorRunner.on_tick` có lời hứa: *"bounded local work only, never network
I/O"* (`detector_runner.py:186`). Gửi lệnh p95 **984 ms** trong callback đó sẽ
làm tick sau trễ → `tick_overruns` → chuỗi thời gian méo → **detector đã đóng
băng cho kết quả khác lúc train**. Controller sẽ phá chính cảm biến nó phụ thuộc —
vòng phản hồi dương ở tầng **tài nguyên**, khó thấy hơn tầng logic.

Kiến trúc bốn luồng:

```
collector ──mailbox──> detector-writer ──PATCH──> Ditto
                                                    │ SSE
                                               twin-sse
                                                    │ cache
                                                 CONTROL (~1 Hz, độc lập)
```

Điểm giao **duy nhất** giữa khoang collector và khoang control là
`intervention_log`: control **ghi** (write-ahead), collector **đọc**
(`fsm.step → log.active()`). `InMemoryInterventionLog` không có khoá → từ 8.4 là
**data race**. Không sửa nó (nằm trong đường chạy đã đo ở 6R/7) mà **bọc**:
`controller/locked_log.py`, trả **bản sao** để bên đọc không cầm tham chiếu sống.
Stress test 2 luồng × 2000 vòng: 0 lỗi.

**Hai đồng hồ, hai mục đích, không được lẫn:** `Intervention.t_start` dùng
`time.time()` (wall clock) vì FSM so nó với `t_source` của snapshot (M8);
`deadline_mono` dùng `time.monotonic()` vì NTP có thể nhảy lùi. Có test.

## 5. Trạng thái vô chủ, dead-man switch, tắt êm

**Revert-first (crash recovery).** Controller restart: `cstate` mặc định IDLE,
`intervention_log` rỗng, nhưng `bw` thật **có thể vẫn là 7.0** → không ai gỡ.
Khởi động: chờ SSE ≤ 10 s → liệt kê link **mình sở hữu** → write-ahead revert →
mới vào IDLE. Ba quyết định:

- **Chỉ link `<client>-s1`** (prereg 8.1). `link-s2-s3` có bw lạ **không phải việc
  của controller** — điều hoà tài nguyên không thuộc về mình là cách hai
  controller bắt đầu đánh nhau.
- **Revert orphan cũng write-ahead**, vì đổi bw cũng là nhiễu loạn (reset qdisc).
- **Không có dữ liệu twin → HOLD, không phải IDLE.** `IDLE` nghĩa là "tôi đã kiểm
  tra và không có gì đang mở"; nói thế khi chưa kiểm được là nói dối. Cùng logic
  với `initial_controlloop_body` (8.3).

**Dead-man switch phải nằm bên kia ranh giới hỏng.** Watchdog trong tiến trình
controller chết cùng controller. Lease nằm ở `command_agent`:
`setBandwidth {"bw": 7.0, "leaseS": 15.0}` → không ai gia hạn trong 15 s thì agent
tự trả về giá trị **trước lease đầu tiên**.

> Bẫy nguy hiểm nhất: ghi đè `restore_bw` mỗi lần gia hạn → watchdog "phục hồi"
> về đúng 7.0 → **dead-man switch vô hiệu mà không báo lỗi nào**. Chụp giá trị
> **lần đầu**; có test `test_restore_bw_chup_lan_dau_khong_bi_ghi_de`.

Gia hạn dùng cid **tất định theo chu kỳ** (`<open_id>#r<k>`) để không bị dedup
chặn (dedup trả kết quả cũ và **không chạm Mininet** → lease không được gia hạn).

**Tắt êm**: `SIGTERM` → gỡ can thiệp đang mở → công bố `HOLD/shutting_down` →
thoát, có timeout 5 s và `try/except` (gỡ thất bại không được làm `systemctl stop`
treo). Không dùng dead-man switch làm đường thoát bình thường.

**Crash loop**: 5 lỗi/60 s → gỡ, `HOLD/crash_loop`, ngừng quyết định, **giữ
heartbeat** — chết im lặng khác hẳn "còn sống và đang từ chối hoạt động".

## 6. Bảng timeout nhiều tầng (và test quan hệ thứ tự)

| Timeout | Giá trị | Ở đâu | Phải nhỏ hơn |
|---|---|---|---|
| control tick | 1 s | `runner.py` | chu kỳ gia hạn |
| ân hạn xác nhận | 2 s | `runner.py` | — (≥ p95 xác nhận 1,003 s + 1 tick) |
| gia hạn lease | 5 s | `runner.py` | `LEASE_TTL_S / 3` |
| `LEASE_TTL_S` | 15 s | `command_agent` | `T₀` |
| `T₀` | 15 s | `PolicyParams` | `T_max` |
| `W` | 14 s | `PolicyParams` | — |
| `T_max` | 110 s | `PolicyParams` | `MAX_OPEN_S − 5` |
| `MAX_OPEN_S` | 120 s | `intervention_log` | — |

`test_thu_tu_timeout_nhat_quan` kiểm **quan hệ**, không kiểm từng giá trị: lỗi
timeout phổ biến nhất không phải "sai giá trị" mà là "hai timeout không nhất quán
với nhau".

**Mâu thuẫn đã khai (không giấu):** nếu controller **treo** ngay sau khi inject,
tc được phục hồi sau ≈ 15 + 1 + 0,98 ≈ **17 s**, nhưng `InterventionLog` vẫn còn
inject chưa đóng nên detector **vẫn ức chế tới 120 s** → cửa sổ mù thừa ≤ **103 s**.
Chấp nhận vì trạng thái **vật lý** đã an toàn (mạng hết bị bóp sau 17 s) và nó tự
khỏi khi controller sống lại (revert-first đóng lease). Phải **đo** ở 8.7 (C9-b),
không chỉ khai.

## 7. Trễ xác nhận đủ đường — trả nợ 8.3

`results/report/phase8_confirm_latency.json`, n = 25, **pha ngẫu nhiên**, 0 timeout,
twin: 3107 event, 0 dropped, 0 reconnect.

| | p50 | p95 | max |
|---|---|---|---|
| `inject` (quyết định → `observed_bw()` thấy 7,0) | **667,3 ms** | **1003,0 ms** | 1097,5 ms |
| `revert` (→ thấy 20,0) | 993,7 ms | 1034,8 ms | 1041,7 ms |

Đây là **đủ đường**: quyết định → lệnh → `tc` → tick collector kế tiếp → PATCH →
SSE → cache của controller. Khác hẳn 0,03–0,11 s đo ở 8.3 (chỉ tới lúc `tc` đổi,
đọc thẳng trong tiến trình Mininet).

**Dự đoán của tôi trước khi đo là ~1,2 s p50 / ~2,0 s p95 — đo thật nhanh hơn.**
Nguyên nhân: thành phần "chờ tick collector" nhỏ hơn giả định (collector lấy mẫu
rồi PATCH ngay trong tick đó), và trễ lệnh trong lần chạy này thấp hơn receipt
Phase 7 (đo dưới hồ sơ tải khác). Phân bố `revert` chụm quanh ~1 tick, đúng với
việc thành phần chờ tick chi phối.

Ngân sách C3:

```
phát hiện (phys_obs p95 1,433 + n_act 2 tick)   ≈ 3,4 s
chu kỳ quyết định của controller                ≤ 1,0 s
xác nhận đủ đường (p95)                          ≈ 1,0 s
─────────────────────────────────────────────────────
                                                 ≈ 5,4 s  <  10 s  ✅ biên 46%
```

## 8. Chạy thật: vòng kín đầu-cuối

`scripts/run_phase8_loop.py --duration 300 --flood --flood-at 30 --flood-stop 240`

Diễn biến quan sát được (in ra từng 10 s):

```
t=30  flood ON
t≈35  detector act        -> controller MITIGATING, bw = 7.0
t≈50  hết hạn giữ (T₀=15) -> revert, PROBING, bw = 20.0
t=60  act lại trong W     -> MITIGATING, backoff k=1 (giữ 30 s)
...   k=2 (60 s), k=3 (110 s)
t=240 flood OFF           -> probe sạch -> IDLE
```

`logs/controller_audit.jsonl`: 44 dòng, **chuỗi hash hợp lệ**, gồm 4 `inject`,
4 `revert`, 36 `reassert` (toàn bộ là `lease_renew`; `drift_fixes = 0` sau khi có
cửa sổ ân hạn §3 — lần chạy trước khi vá là 48 dòng với 4 `drift`). Chuỗi backoff đọc thẳng từ audit:

```
ctl-<boot>-e1-k0:inject  act_localized
ctl-<boot>-e1-k0:revert  hold_expired
ctl-<boot>-e1-k1:inject  probe_failed_backoff
ctl-<boot>-e1-k1:revert  hold_expired
ctl-<boot>-e1-k2:inject  probe_failed_backoff   (giữ 60 s)
ctl-<boot>-e1-k3:inject  probe_failed_backoff   (giữ 110 s)
```

Đúng lịch 15 → 30 → 60 → 110 mà `phase8_sim_predictions.json` đã niêm phong ở 8.2.

## 9. Lỗi thật tìm được khi chạy live (không phải lỗi giả định)

**(a) SSE một mình không bao giờ mang `attributes.role`.** Lần chạy vòng kín đầu
tiên: 291 tick, **0 lệnh**, dù detector báo `act` và `affected` có `host-h1`.
Nguyên nhân: Ditto SSE chỉ gửi **trường thay đổi**; `attributes.role` của host
**không bao giờ đổi** nên **không bao giờ** xuất hiện trong stream → `roles()` trả
toàn `None` → `localize()` thấy 0 ứng viên client → im lặng.

Sửa: `TwinReader.prime()` — **GET một lần toàn bộ Things rồi mới nghe stream**, và
prime lại sau mỗi lần reconnect. Đây là mẫu chuẩn *snapshot-then-stream* của mọi
consumer stream. Có test `test_sse_mot_minh_khong_bao_gio_co_role`.

> Đây là một chế độ hỏng **im lặng hoàn toàn**: không exception, không log ERROR,
> mọi chỉ số đều đẹp (twin 4306 event, 0 dropped), controller vẫn tick đều 291 lần.
> Chỉ có một dấu hiệu: nó **không bao giờ làm gì**. Nếu không chạy live, ba lesson
> nữa cũng không phát hiện được.

**(b) Trễ quan sát bị hiểu nhầm thành trôi giá trị** — xem §3.

**(c) `LockedInterventionLog` có `__len__` nên log rỗng là *falsy*.** Một dòng
`log_store or default` trong test đã âm thầm thay log thật bằng log mặc định. Sửa
bằng `is None`. Bài học: lớp nào định nghĩa `__len__` thì **không bao giờ** dùng
`or` để chọn mặc định.

## 10. Receipt

| File | Nội dung |
|---|---|
| `controller/runner.py` | vòng chính: edge + level + revert-first + tắt êm + crash loop |
| `controller/locked_log.py` | bọc khoá cho điểm giao hai luồng |
| `bridge/command_agent.py` | no-op khi lặp + lease + watchdog (dead-man switch) |
| `scripts/run_phase8_loop.py` | khởi động 4 luồng, có `--debug-every` |
| `scripts/measure_phase8_confirm.py` | đo trễ xác nhận đủ đường |
| `results/report/phase8_confirm_latency.json` | n=25, p50 667 ms / p95 1003 ms |
| `results/report/phase8_loop_run.json` | thống kê một lượt vòng kín 300 s |
| `logs/controller_audit.jsonl` | 48 dòng, chuỗi hash hợp lệ |
| `test/test_phase8_runner.py` (21) · `test_command_agent_noop.py` (8) · `test_phase8_twin_reader.py` (17) | kiểm bằng máy |
