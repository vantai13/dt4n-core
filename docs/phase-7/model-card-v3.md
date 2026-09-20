# Model card v3 — DT4N detector + twin (system card)

Bản v3 mở rộng model card thành **system card**: không chỉ mô hình, mà cả hệ thống đang chạy.
Mọi con số dưới đây lấy từ receipt nghiệm thu sinh trên commit đóng băng `9917e07`
(tag `phase-7-frozen`), trừ nơi ghi rõ nguồn khác.

- Phán quyết: `results/report/phase7_verdicts.json`
- Bằng chứng: `results/report/phase7_acceptance/`
- Phát hành: `released = G1 ∧ G2 ∧ G3 ∧ G4 = true`, `fails_declared = ["S1"]`

## 1. Dùng để làm gì

Phát hiện bất thường mạng ở mức tick 1 giây trên bản sao số (digital twin), và **chỉ** phát
tín hiệu. Nó không hành động. Quyết định hành động thuộc về Phase 8, theo hợp đồng ở
`08-phase8-handoff.md`.

Vùng vận hành hợp lệ: min txRate của client ≤ **4.3126 Mbps** (lấy từ max trên tick judgeable
của 8 run TRAIN Phase 5, `phase7_prereg.json`). Ngoài vùng này detector **tự khai không có
thẩm quyền** thay vì đoán.

## 2. Hiệu năng đã nghiệm thu

| Thuộc tính | Số đo | Ngưỡng |
|---|---|---|
| Trễ phát hiện p95 (từ lệnh inject) | 1836.5 ms | ≤ 3000 ms |
| Trễ e2e p95 (sự cố → khung hình) | 1535.1 ms | < 5000 ms |
| Twin → UI p95 | 43.09 ms | ~1000 ms |
| Latency detector p95 dưới tranh chấp | 1.6165 ms | ≤ 50 ms |
| RSS tăng sau 30 phút (giao thức v2) | 0.5273 MiB | ≤ 1.0 MiB |
| Detector chết → twin STALE (max) | 3014 ms | ≤ 5000 ms |
| Tự kích hoạt do can thiệp controller | 0 lần vào `act` | == 0 |

**Giới hạn lớn nhất, đã khai:** S1 — tỷ lệ phát hiện theo sự cố của envelope-only là **0.30**
so với mục tiêu 0.875. Đây là kết quả 6R trên tập R-D **mở một lần**, và nó **không** được đo
lại. Hệ thống phát hiện tốt các sự cố tạo bất thường ở mức link, và bỏ sót các sự cố mà TCP
hấp thụ thành một mức thông lượng thấp hơn nằm trong biên đã hiệu chỉnh.

## 3. Failure mode — hệ nói gì khi CHÍNH NÓ hỏng

Cột "người vận hành thấy gì" là cột quan trọng nhất: một hệ thống giám sát hỏng mà im lặng
thì nguy hiểm hơn một hệ thống hỏng mà kêu.

| FM | Hỏng cái gì | Người vận hành thấy gì | Số đo |
|---|---|---|---|
| **FM8** | Ditto nghẽn (pause 5 s) | **STALE** — nhãn tím, "nhịp tim mới cuối cùng X s trước". **Không** phải trạng thái cũ giả vờ còn tươi. Heartbeat đi **qua** Ditto, nên Ditto nghẽn thì twin không nhận được nhịp và UI phải STALE. Đường đo của detector **không** bị ảnh hưởng | 7.3: 60/60 tick, `dt_max` 1.000 s, 0 gap > 1.5 s, `failed` 2, `overwritten` 1, 0 exception, 59 tick `normal` |
| **FM9** | Detector chết (crash hoặc treo luồng ghi) | STALE, và **không bao giờ** hiện "All systems normal". Mở trang lúc detector đã chết cũng thấy STALE ngay | S12: 20/20 trial, max 3014 ms, p95 2925 ms; `all_clear_while_stale` = 0; `first_load_dead_detector.always_stale` = true |
| **FM10** | Tải ngoài vùng hiệu chỉnh | `unknown(out_of_operating_range)`, **không bao giờ** `suspect`. Detector tự khai không có thẩm quyền ở tải này | 7.1 KN1: R-N 8M/10M guard bật 100% tick; 0 tick che lỗi trên 22 run lỗi |
| **FM11** | Controller quên ghi `revert` | Sau **120 s** lease, cause đổi thành `stale_intervention`, ức chế dừng, báo động **quay lại** | 7.6: `stale` xuất hiện 0.29 s sau khi hết hạn; nghiệm thu: `lease_pass` = true |
| **FM12** | Collector chết | Heartbeat dừng → STALE. Supervisor tạo incarnation mới → `warming_up` với `bootId` mới | test `run_forever_survives_collector_crash` |
| **FM13** | Topology lạ | Fail-closed: không heartbeat → STALE vĩnh viễn, log ERROR | test `unknown_topology_fails_closed` |
| **FM14** | Bug tất định (crash-loop) | Dừng sau 6 exception trong 60 s, log ERROR, **không** reset vô hạn | test `deterministic_bug_becomes_crash_loop` |

## 4. Can thiệp của controller

Trong khoảng `[inject, revert + cooldown 8 s]`, mọi báo động mà **toàn bộ** entity vi phạm nằm
trong hành lang nhân quả (gồm cả đường detour) bị đổi thành `unknown(suppressed_intervention)`.

Nghiệm thu 7.7, ba nhánh, mỗi nhánh 4 lần can thiệp thật:

| Nhánh | `act` | `alarm` | Tick bị ức chế | Ý nghĩa |
|---|---|---|---|---|
| `log_first` (ghi log trước khi hành động) | **0** | 0 | 84 | Hành vi đúng |
| `log_late` (ghi log trễ) | 0 | 4 | 84 | Đối chứng đua: có báo động lọt |
| `no_log` (không ghi log) | **4** | 4 | 0 | Đối chứng âm: tự kích hoạt hoàn toàn |

`log_first` 0 act và `no_log` 4/4 act cùng lúc là điều làm kết quả này có nghĩa: nó cho thấy
ức chế **thật sự** là thứ ngăn vòng phản hồi, chứ không phải sự cố tình cờ không gây báo động.

**Giá phải trả, đã khai:** một sự cố thật, độc lập, xảy ra trên hành lang đó trong khoảng đó
**sẽ bị che**. Trên topology 3 switch nối tam giác, hành lang nhân quả của một `admin_down`
phủ **14/16 entity**, nên ức chế "đúng vùng" gần bằng ức chế toàn mạng. Khác biệt chỉ có ý
nghĩa khi topology lớn hơn; Phase 7+ nên đo `|zone| / |topology|` như một chỉ số vận hành.

Residual **không** bị ức chế bởi `InterventionLog` và chỉ có thể lên tới `suspect`:
0 tick residual-only trên cả 4 lần can thiệp `admin_down`. **Chưa đo** cho loại hành động khác.

## 5. Dưới tranh chấp tài nguyên

Thiết kế ABBA, block 300 s: `cycle_scan` p95 72.01 ms (ON) so với 72.14 ms (OFF), CPU trung
bình 3.51% (ON) so với 3.22% (OFF), 0 overrun và 0 gap > 1.5 s ở cả hai. Detector không bị
tải ngoài đẩy ra khỏi ngân sách.

## 6. Bộ nhớ: hai giao thức, hai con số

| Giao thức | Kết quả | Ghi chú |
|---|---|---|
| v2 (đã đăng ký, bỏ 300 s warmup) | **0.5273 MiB** / 30 phút | PASS (≤ 1.0) |
| v1 trên **cùng** chuỗi đo | 1.4883 MiB / 30 phút | FAIL nếu chấm theo v1 |

Cả hai đều được báo. Chênh lệch nằm ở 5 phút đầu: tiến trình tích hợp khởi tạo lười khoảng
1 MiB. Dốc nửa sau là 16.3 KiB/phút, gần phẳng — **không rò rỉ**. JS heap sau khi ép GC:
4.758 → 5.749 MiB rồi phẳng, **không rò rỉ JS**. RSS của trình duyệt tăng chậm là bộ nhớ đệm
của renderer, không phải ứng dụng.

Việc ép GC mỗi 5 phút qua CDP là một **probe effect** nhỏ làm con số đẹp hơn thực tế; khai ở đây.

## 7. Điều kiện triển khai

- RAM khoảng 3.7–4 GB, trong đó Ditto chiếm khoảng 2.6 GB.
- Controller và collector **phải chạy trên cùng một máy / cùng nguồn thời gian**: ức chế so
  `t_start` với `t_source` bằng **wall clock**.
- `InterventionLog` hiện chỉ tồn tại **trong một tiến trình**.
- Ryu chạy trong môi trường `sdn_net`; `ryu-manager` nạp `mininet.controller_static` từ repo
  nên cần repo root trong `PYTHONPATH`.

## 8. Chưa chứng minh được

- S1 (0.30) không được đo lại và sẽ không được đo lại trong khuôn khổ này.
- Residual dưới can thiệp mới chỉ đo với `admin_down`.
- Độ đặc hiệu của residual ở tải cao không được gác bởi cổng nào (xem `phase6r_acceptance_prereg`
  mục `declared_coverage_gap`).
- Mọi số ở đây đo trên một máy, một topology 3 switch, một hồ sơ tải.
