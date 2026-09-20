# Phase 7.7 — Đóng băng, nghiệm thu và phán quyết

## 0. Dự đoán cho chiến dịch nghiệm thu (khóa TRƯỚC khi chạy)

Mục này được commit trước commit đóng băng, nên thứ tự "dự đoán → đóng băng → đo" được
git chứng minh. Code runtime chỉ đổi rất ít so với các lần đo trước, nên dự đoán bám sát
giá trị cũ.

| SLO | Giá trị trước (receipt, commit) | Dự đoán nghiệm thu |
|---|---|---|
| S12 `kill_to_stale.max_ms` | 3093 ms (`9bd5890`, 7.4) | 2.9–3.4 s, PASS (≤ 5000 ms) |
| S4 `s4_like_from_cmd.p95_ms` | 1770.8 ms (`3b666d5`, 7.5) | 1.6–1.9 s, PASS (≤ 3000 ms) |
| S5 block ON xấu nhất (p95) | 1.64 ms (`b30fee8`, 7.6) | 1.4–2.2 ms, PASS (≤ 50 ms) |
| S6_v2 `delta_mib` | 0.5625 MiB (`5be681f`, 7.7p1) | 0.3–0.8 MiB, PASS (≤ 1.0 MiB) |
| S11 `log_first` act | 0/4 (`b30fee8`) | 0/4, PASS; `log_late` 1 alarm / 0 act mỗi lần; `no_log` 4/4 act |
| e2e p95 / twin → UI p95 | 1469 / 44 ms (`3b666d5`) | 1.3–1.6 s / 30–60 ms |

Dự đoán cho quy tắc phát hành (amendment 3): `released = G1 ∧ G2 ∧ G3 ∧ G4 = true`, và
`fails_declared = ["S1"]`. S1 là giới hạn của 6R (envelope-only 0.30 < 0.875), không phải
một gate.

Nếu có dòng FAIL: ghi FAIL, truy tầng bằng bảng phân rã 7.5, sửa logic, tạo đóng băng mới
(`phase-7-frozen-2`) rồi đo lại. Toàn bộ lịch sử được giữ trong `history`. Không chỉnh
`ttlTicks` hay bất kỳ ngưỡng nào.

## 1. Quy trình

1. Commit code nghiệm thu và mục 0 → `build_phase7_freeze.py` → commit → tag `phase-7-frozen`.
2. `run_phase7_acceptance.py` chạy lại 5 phép đo live trên commit đóng băng. Trước mỗi bước:
   kiểm HEAD == tag, worktree sạch, SHA từng file == `phase7_freeze.json`; bảo đảm Ryu lắng
   nghe ở 6653 (mỗi harness kết thúc bằng `mn -c`, lệnh này kill cả `ryu-manager`).
3. `build_phase7_verdicts.py` suy bảng 14 dòng và gate bằng code (`measurements/phase7_verdicts.py`).
4. `build_phase7_manifest.py` niêm phong thứ tự đăng ký (lấy từ git) → tag `phase-7-complete`.

## 2. Chiến dịch nghiệm thu đã chạy

Toàn bộ năm phép đo sinh từ **cùng một commit đóng băng** `9917e07d` (tag `phase-7-frozen`),
khác với các receipt 7.4–7.7p1 vốn đến từ năm commit khác nhau. Đó là lý do phải chạy lại:
receipt cũ mô tả một hệ thống khác với hệ sẽ phát hành.

| Bước | Lệnh | Thời gian | Receipt |
|---|---|---|---|
| `s12` | measure_phase7_s12_live.py --trials 20 | 3.5 phút | `phase7_s12_live.json` |
| `e2e` | measure_phase7_e2e.py --trials 25 | 6.2 phút | `phase7_e2e_latency.json`, `phase7_e2e_latency.png` |
| `s11` | run_phase7_s11_live.py --reps 4 --lease | 11.4 phút | `phase7_s11_live.json`, `phase7_residual_intervention.json` |
| `contention` | run_phase7_contention.py --block 300 | 20.4 phút | `phase7_contention.json` |
| `soak` | soak_phase7_live_v2.py | 45.5 phút | `phase7_soak_live_v2.json` |

`index.json` ghim `frozen_commit`, mã thoát và SHA từng receipt; `build_phase7_verdicts.py`
từ chối nếu bất kỳ con số nào trong đó lệch.

### Hai lần trượt trước khi chạy được

Cả hai đều là **lỗi dụng cụ**, xảy ra trước khi bất kỳ harness nào chạy, nên không để lại
dấu vết nào trong `index.json`:

1. `ryu-manager` nằm trong môi trường conda `sdn_net`, không có trong `PATH`, và
   `run_phase7_acceptance.py` tìm nó qua `shutil.which` hoặc `DT4N_RYU_MANAGER`.
2. `ryu-manager` chạy bằng Python 3.9 của conda và nạp app `mininet.controller_static` —
   package **trong repo này**, trùng tên với thư viện Mininet. `sys.path[0]` là thư mục
   `bin/` của conda nên `ModuleNotFoundError: No module named 'mininet'`.

Cách chạy đúng: `sudo -E env PYTHONPATH=$PWD .venv/bin/python scripts/run_phase7_acceptance.py
--ryu-manager <conda>/bin/ryu-manager`. **Không sửa orchestrator**, vì nó nằm trong nhóm
`harness` của tập đóng băng; đổi một byte là `check_frozen()` từ chối và bốn receipt đã đo
mất giá trị so sánh.

## 3. Bảng SLO — 14 dòng, suy bằng code

Bảng này **copy từ `phase7_verdicts.json`**, không gõ tay. `measurements/phase7_verdicts.py`
là hàm thuần: thiếu dữ liệu trả `NO_DATA` (không bao giờ `PASS`), logic 6R trôi trả `INVALID`.

| SLO | SLI | Mục tiêu | 6R | Live | Phán quyết |
|---|---|---|---|---|---|
| S1 | per_incident_detection_rate (tang suspect) | >= 0.875 | FAIL | — | **FAIL** |
| S2 | su kien bao dong sai moi gio, nen tinh | <= 3.0 | PASS | — | **PASS** |
| S3 | MTBFA, nen tinh | >= 20.0 | PASS | — | **PASS** |
| S4 | time_to_detect p95 (snapshot dau co dau ve | <= 3000 | PASS | 1836.51 | **PASS** |
| S4b | tran debounce N (rang buoc suy ra tu S4) | <= 2 | PASS | — | **PASS** |
| S5 | latency p95 observe()+step(), gom flatten  | <= 50 | PASS | 1.6165 | **PASS** |
| S6 | tang RSS sau 30 phut | <= 1.0 | PASS | 0.5273 | **PASS** |
| S7 | khong dao dong | == 0 | PASS | — | **PASS** |
| S8 | hanh vi khi thieu du lieu | == 1.0 | PASS | — | **PASS** |
| S9 | trang thai sau restart | == 1.0 | PASS | — | **PASS** |
| S10 | hanh vi o tai ngoai vung hieu chinh | báo, không đặt mục tiêu | REPORT_ONLY | — | **REPORT_ONLY** |
| S11 | chong tu-kich-hoat | == 0 | PASS | 0 | **PASS** |
| S12 | staleness khi detector chet | <= 5000 | DEFERRED | 3014 | **PASS** |
| S13 | truy vet mo hinh | == 1.0 | PASS | — | **PASS** |

Các dòng **mang sang từ 6R** (S1, S2, S3, S4b, S7, S8, S9, S13) chỉ hợp lệ vì hai điều kiện
cùng đúng: `ml/*.py` và `models/*` **trùng bit** với `phase6r_manifest` (`pins_6r_ok = True`,
kiểm ở cả ba nơi: file thật, manifest 6R, `phase7_freeze.json`), và dữ liệu **không thể đo
lại hợp lệ** (tập R-D mở một lần; S4b là suy diễn thuần).

## 4. Gate phát hành

```
G1 = true
G2 = true
G3 = true
G4 = true
released = G1 ∧ G2 ∧ G3 ∧ G4 = true
fails_declared = ["S1"]
```

Quy tắc này là **amendment 3 của 6R**, không phải "mọi SLO PASS". Hai thứ khác nhau: bảng SLO
**mô tả** hệ thống và được phép chứa FAIL trung thực; gate **quyết định** có bàn giao cho
Phase 8 hay không.

**Vì sao S1 FAIL mà vẫn phát hành.** S1 (tỷ lệ phát hiện theo sự cố, envelope-only 0.30 so với
ngưỡng 0.875) là **giới hạn đã khai** của 6R, không phải một gate. Nó được đo trên tập R-D
vốn chỉ được mở **một lần**; đo lại chính là tái sử dụng tập test. Nếu áp quy tắc "mọi SLO
PASS" thì Phase 7 không bao giờ phát hành được, trừ khi có người đo lại S1 — và đó đúng là
hành vi mà toàn bộ kỷ luật này tồn tại để ngăn.

**G4 đóng được ở đây.** Amendment 4 của 6R hoãn S12 sang Phase 7 vì nó là thuộc tính tích hợp
detector–Ditto–TTL, không tồn tại trong harness 6R. Lần này S12 được đo live: 20/20 trial đạt,
`max_ms` = 3014.0 ms so với ngưỡng 5000 ms. Verdict dùng `max`, **không** dùng p95 — cam kết
"detector chết thì twin phải STALE trong 5 giây" chỉ cần trượt một lần là đã vi phạm. Nếu có
trial nào lỗi (`ok != trials`), giá trị bị đặt `None` và dòng thành `NO_DATA`.

## 5. Dự đoán so với thực đo

| SLO | Dự đoán (khóa trước) | Thực đo | |
|---|---|---|---|
| S12 `max_ms` | 2.9–3.4 s | **3014.0 ms** | ✅ trong khoảng |
| S4 `s4_like_from_cmd.p95` | 1.6–1.9 s | **1836.5 ms** | ✅ |
| S5 block ON xấu nhất | 1.4–2.2 ms | **1.6165 ms** | ✅ |
| S6_v2 `delta_mib` | 0.3–0.8 MiB | **0.52734375 MiB** | ✅ |
| S11 `log_first` act | 0/4 | **0/4**, 84 tick bị ức chế | ✅ |
| e2e p95 / twin → UI p95 | 1.3–1.6 s / 30–60 ms | **1535.1 ms / 43.09 ms** | ✅ |
| `released` / `fails_declared` | `true` / `["S1"]` | **`true` / `["S1"]`** | ✅ |

Bảy trên bảy dự đoán đúng. Điều này **không** chứng minh hệ thống tốt; nó chứng minh hệ thống
**ổn định và dự đoán được** giữa các lần đóng băng, và rằng không ai điều chỉnh gì sau khi
nhìn thấy số.

## 6. Lịch sử: mọi FAIL và mọi lần chạy lại được giữ

Trường `history` trong `phase7_verdicts.json` giữ:

- **S6**: 7.6 FAIL (2.77 MiB/30 phút) do bộ đệm nghiên cứu `timeline` chạy mặc định trong
  production (tracemalloc: `bridge/detector_runner.py` +1725 KiB). Sửa **logic** —
  `DetectorRunner(timeline_samples=0)` mặc định — **không** đổi tham số SLO. Giao thức v2
  được đăng ký trước khi đo lại (`phase7_s6_v2_prereg.json`), và giao thức v1 trên **cùng
  chuỗi** vẫn được báo: 1.48828125 MiB. Hai con số, không chọn con số đẹp.
- **S11**: 7.6 có lệch 2 tick ở nhánh `log_late` do off-by-one của harness; chạy bổ sung
  `phase7_s11_live_offbyone_fix.json`.
- **S12**: 6R `DEFERRED` theo amendment 4, đo live lần đầu ở Phase 7.

## 7. Ngân sách MASTER_PLAN

| Ngân sách | Mục tiêu | Thực đo (p95) | |
|---|---|---|---|
| e2e: sự cố → khung hình vẽ xong | < 5 s | **1535.1 ms** | ✅ |
| twin → UI | ~1 s | **43.09 ms** | ✅ |

n = 25, pha inject ngẫu nhiên, sự kiện `flood h1->srv1 47M`, cầu đồng hồ Cristian sai số ≤ 0.33 ms. Đây là
**kênh nhanh** (envelope). Kênh chậm (conservation) mất khoảng 11 s và **vượt** 5 s — giới hạn
đã khai của kênh đó, xem `08-phase8-handoff.md` điều cấm N11.
