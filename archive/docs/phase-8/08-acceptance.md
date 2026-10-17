# Phase 8.8 — Nghiệm thu, system card, bàn giao

Niêm phong: `results/report/phase8_acceptance.json`
Chạy lại bằng **một lệnh**, từ một clone sạch, không cần tác giả giải thích gì:

```bash
python3 scripts/accept_phase8.py --strict      # → mã thoát 0 hoặc 1
```

---

## 0. Ba việc bắt buộc trước 8.8 — kết quả

| # | Việc | Kết quả |
|---|---|---|
| 1 | Phát biểu lại cận C6-a bằng nguyên nhân *shutdown revert* | ✅ cận = 13 + 1 = **14**; sim đã vá; known-answer test ra **đúng 14** |
| 2 | Thống nhất định nghĩa `gap` | ✅ một hàm; **giả thuyết "lệch định nghĩa" bị BÁC BỎ** — chênh lệch là **vật lý** |
| 3 | Quy kết S11 bằng vị từ `t_source` | ✅ vị từ không hằng số đã cài; run 8.7 **không quy kết lại được** (không lưu `t_source`) → đo lại ở 8.8 |

### 0.1 Cận C6-a — đính chính mô hình, không nới tiêu chí

Từ receipt `phase8_stability_flood.json` (không suy diễn):

```
holds_s = [16.0, 30.0, 61.0, 111.0, 110.0, 110.0, 92.4]
gaps_s  = [11.0] × 6        duration_s = 600.4
```

Cộng dồn thời điểm bắt đầu mỗi hold:

```
hold 1: 0     → 16.0     gap → 27.0
hold 2: 27.0  → 57.0     gap → 68.0
hold 3: 68.0  → 129.0    gap → 140.0
hold 4: 140.0 → 251.0    gap → 262.0
hold 5: 262.0 → 372.0    gap → 383.0
hold 6: 383.0 → 493.0    gap → 504.0
hold 7: 504.0 → 596.4    ← lịch là 504 + 110 = 614, NGOÀI chân trời 600
```

Hold thứ 7 **không kết thúc theo lịch** — nó kết thúc vì run hết giờ và
`ControlRunner.shutdown()` gỡ can thiệp đang mở. **Hành động thứ 14 là revert
của tắt êm.**

Sim 8.2 (`a38c6434`) cắt ngang can thiệp đang mở lúc hết chân trời mà **không
gỡ**, nên nó đếm 13. Một hệ thật **bắt buộc** phải gỡ: nếu không, mạng kẹt ở
7 Mbps với một bản ghi can thiệp không ai sở hữu — đúng lỗi #2 của chaos 8.7.
**Cái sai là sim, không phải hệ.**

Bản vá: `controller/sim.py::run` phát một revert khi `open_since is not None`
lúc hết chân trời, đếm riêng vào `n_shutdown_reverts`.

```
$ python3 -c "from controller.sim import run, always, SimParams; \
>   print(run(always,600.0).n_actions, \
>         run(always,600.0,sim_params=SimParams(graceful_shutdown_revert=False)).n_actions)"
14 13
```

Hai nhánh, hai khoá: bản vá **tiên đoán** 14 (không phải "≥ 13"), và tắt cờ đi
thì **tái lập đúng** con số 13 đã niêm phong ở 8.2 — nên bản vá không đụng chạm
vào bất cứ cơ chế nào khác. `test/test_phase8_acceptance_fixes.py` và
`test/test_phase8_sim.py` khoá cả hai phía.

`min_hold_s = 16,0 ≥ T₀ = 15`, `violates_t0 = []`. Hai tiêu chí, hai mục đích:
đếm hành động chống *hành động thừa*, `min_hold_s` chống *dao động*.

### 0.2 `gap`: 2,31 s và 11,0 s — định nghĩa GIỐNG nhau, khác biệt là VẬT LÝ

Receipt: `results/report/phase8_gap_reconciliation.json`

Một hàm duy nhất, `measurements/blind_time.pairs` + `.gaps`
(`gap_k = t_inject[k+1] − t_revert[k]`, ghép theo `pair_key`), áp lên audit đã
niêm phong của **cả hai** chiến dịch:

| | tính lại | receipt đã niêm phong | khớp |
|---|---|---|---|
| 8.6 A/B nhánh A (n = 48) | mean 2,31 · min 1,00 · max 5,00 | mean 2,31 · min 1,0 · max 5,0 | ✅ |
| 8.7 stability flood | [11,0] × 6 | [11,0] × 6 | ✅ |

**Giả thuyết "hai harness định nghĩa `gap` khác nhau" bị bác bỏ.** Cả hai đã đi
qua đúng một hàm.

Cơ chế thật đọc thẳng từ **cùng những file audit đó**:

| | 8.6 A/B nhánh A | 8.7 stability flood |
|---|---|---|
| tick báo động chứa `link-s2-s3` (entity **duy nhất** ngoài vùng 15/16) | **1846/1846 = 100,0%** | **2/23 = 8,7%** |
| tick `unknown/suppressed_intervention` | **0** | **554** |
| ⇒ `local ⊆ zone` | không bao giờ thoả | thoả gần như luôn |
| ⇒ ức chế | **không bao giờ** áp dụng | áp dụng |
| ⇒ gap | 1 tick (1–5 s) | 11,0 s |

11,0 s khớp **trễ chết** của sim 8.2 (`dead_time_s` = 8,0 cooldown + 1,433
`d_obs` p95 + 2 tick `n_act` = **11,433 s**) trong **0,43 s**. Khi ức chế bật,
mô hình đúng; khi nó tắt, vòng kín tái bảo vệ nhanh hơn mô hình.

#### Phải rút lại

1. `phase8_ab_addendum::why_gaps_are_short` phát biểu **quá rộng**: *"dưới flood
   47 Mbps tập entity vi phạm CÓ CHỨA `link-s2-s3`"*. Đúng cho chiến dịch 8.6
   (100,0%), **sai** cho chiến dịch 8.7 (8,7%). Phải giới hạn phát biểu vào
   điều kiện đã đo.
2. `06-effectiveness.md` §15.3: phần bù do recovery burst là **≈ 0,15 Mbps**,
   không phải ≈ 0,5 Mbps (xem §0.4 dưới).

#### Ẩn số được KHAI, không được lấp

Điều kiện phân biệt hai chế độ ức chế — **0/1846** tick ở 8.6 so với **554/577**
ở 8.7, dưới cùng một kích thích danh nghĩa — **chưa xác định được** từ các hiện
vật hiện có. Đây là một ẩn số được khai, không phải một kết luận.

> Hệ quả cho system card: **không được phát biểu tỷ lệ mù C12 như một hằng số
> của hệ.** Nó phụ thuộc một biến chưa biết. Xem giới hạn **C4** ở system card.

### 0.3 S11: từ "trừ trễ" sang một vị từ kiểm chứng được

Cách xử lý ở 8.7 (*"trừ trễ hiển thị 1,5–2,0 s → Loại I = 0"*) đúng về bản
chất nhưng **trông** giống nới định nghĩa. Thay bằng đúng vị từ mà FSM dùng,
`ml/intervention_log.py::Intervention.active_at`, **không có hằng số nào**:

```python
def in_intervention_window(t_source, t_start, t_revert, cooldown_s=8.0):
    end = (t_revert + cooldown_s) if t_revert is not None else t_start + 120.0
    return t_start <= t_source < end
```

Cuộc đua thật không phải *log vs lệnh* (M5 đã xử lý) mà là *log vs snapshot đã
đang bay*: collector lấy mẫu tại `t_source`, FSM chấm nó vài trăm ms sau. Một
tick có `t_source < t_start` là **nhân quả đi trước** — nó không thể do can
thiệp gây ra, nên nó không phải bằng chứng cho "ức chế lẽ ra phải bật mà không
bật". Hệ **không sai**: `InterventionLog.active()` đã so với `t_source` rồi.
Sai là **quy tắc quy kết** đếm tick theo đồng hồ tường.

Cài ở `measurements/attribution.py`, ba rổ: `type_i` (GATE), `type_ii`
(entity ngoài vùng — lỗ hổng thiết kế, không phải lỗi), `unattributed`
(`t_source` ngoài mọi cửa sổ; mỗi mục ghi `t_source − t_start` để người đọc tự
kiểm).

**Run 8.7 không lưu `t_source` nên KHÔNG quy kết lại được.** Không trừ hằng số
để nó biến mất; đo lại. `scripts/run_phase8_stability.py` nay dump
`DetectorRunner.timeline` và join theo `(bootId, seq)`. Verdict C8-r ở 8.8.

### 0.4 Con số phải sửa trong `06-effectiveness.md`

8,19 s không được bảo vệ trên cửa sổ 120 s, h1 ở 20 Mbps trong khoảng đó thay
vì 7 Mbps. Trung bình "thật" của h3 ≈ **2,00 Mbps**; đo được **2,146**. Phần bù
do recovery burst ≈ **0,15 Mbps**, **không phải ≈ 0,5**.

---

## 1. Nghiệm thu: một script, chạy từ số 0

### 1.1 Vì sao phải là MỘT script

Nghiệm thu phải chạy được bởi **người không phải tác giả**, trên **máy không
phải máy tác giả**, **không cần tác giả giải thích gì**. Nếu nó là "mở docs,
đọc 12 mục, đối chiếu 9 file receipt bằng mắt" thì nó không phải nghiệm thu —
nó là một buổi thuyết trình. Và nó **không bắt được hồi quy**: ba tháng sau ai
đó sửa `policy.py`, không ai biết C6 đã hỏng.

### 1.2 Nghiệm thu ĐỌC receipt, không CHẠY LẠI thí nghiệm

`accept_phase8.py` **không** chạy lại A/B 90 phút hay soak 30 phút. Nó:

1. đọc từng receipt đã niêm phong
2. kiểm **SHA nội dung** của mỗi receipt khớp với nội dung (chưa bị sửa)
3. kiểm **chuỗi phụ thuộc** `prereg → sim → contract → phép đo`
4. kiểm **mã nguồn bị ghim** còn đúng SHA, hoặc trôi **có lý do đã khai**
5. áp tiêu chí **C1–C12 đã niêm phong** lên số trong receipt
6. in bảng verdict, trả 0/1

Hai lý do **khác nhau về bản chất**:

- **receipt là HIỆN VẬT, thí nghiệm là SỰ KIỆN.** Sự kiện không lặp lại được
  (máy khác, tải khác, giờ khác); hiện vật kiểm được mãi mãi.
- **một nghiệm thu chạy 3 giờ thì không ai chạy nó.** Một cổng không ai chạy
  không phải là một cổng.

### 1.3 Kiểm chuỗi phụ thuộc

Một receipt đo bằng một hợp đồng **khác** với hợp đồng được niêm phong là một
receipt **đo sai hệ**. Kiểm bằng máy, không bằng mắt:

```
phase8_prereg (cd7d168c)
   └─ phase8_sim_predictions (a38c6434)  → upstream_sha256[phase8_prereg.json]
        └─ phase8_contract (47464487)    → pinned_sha256[cả hai]
             ├─ phase8_s11_*             → contract_sha256
             └─ phase8_ab_addendum       → source_sha256 = ab_c5.content_sha256
```

**8/8 khớp.**

**Đã khai thẳng — thiếu sót của kỷ luật:** năm receipt phép đo
(`ab_c5`, `c3`, `stability_flood`, `stability_quiet`, `chaos`) **không khai
tham chiếu nào** tới prereg/contract. Chúng được chạy trên cây làm việc đúng,
nhưng điều đó **không kiểm được từ hiện vật**. Script liệt kê chúng ở
`dependency_chain_not_declared` thay vì im lặng cho qua. Việc phải làm ở Phase
9: mọi harness ghi `prereg_sha256` + `contract_sha256` vào receipt của nó.

### 1.4 Mã nguồn bị ghim: trôi phải có lý do

`phase8_contract.pinned_sha256` ghim 18 file. Bốn file đã trôi, cả bốn **có lý
do đã khai** trong `accept_phase8.py::DECLARED_DRIFT`:

| File | Lý do |
|---|---|
| `controller/policy.py` | 8.4/8.6: thêm `incarnation` (hai lần chạy controller trên cùng detector sinh trùng `intervention_id`) |
| `controller/twin_reader.py` | 8.4: R3 kiểm freshness TRƯỚC khi gộp delta |
| `bridge/command_agent.py` | 8.6 fencing token; 8.7 sửa đường lease khi agent chết |
| `controller/sim.py` | **8.8 đính chính mô hình** (§0.1), có known-answer test |

Trôi **không khai** ⇒ nghiệm thu FAIL. Đó là điểm khác nhau giữa một bảng đóng
băng có tác dụng và một bảng đóng băng để trang trí.

---

## 2. C10 — dựng lại bit-exact

### 2.1 Vì sao đây là cổng khó nhất

```
đọc dòng audit  →  gọi lại decide()  →  kết quả PHẢI TRÙNG TỪNG BIT
```

Nó đòi **tính tất định** qua thời gian, qua tiến trình, qua phiên bản.

### 2.2 Bảy nguồn phi tất định, và lesson nào bịt cái nào

| Nguồn | Bịt ở đâu |
|---|---|
| Đồng hồ | `now_mono` truyền vào; `decide()` không gọi `time.monotonic()` — **8.2** |
| Ngẫu nhiên | không `random` trong policy; test tĩnh — **8.2** |
| Id ngẫu nhiên | `_iid` tất định thay `uuid4()` — **8.3**; fencing token — **8.6** |
| Thứ tự dict | `roles` là tuple đã sắp; `canonical()` `sort_keys=True` — **8.3** |
| Tham số ngầm | `PolicyParams` truyền vào + `params_sha256` trong audit — **8.2/8.4** |
| Thiếu đầu vào | `roles` ghi khi `changed` **hoặc** `state == "act"` — **review 8.6** |
| Trạng thái ẩn | `ControllerState` frozen, ghi cả `cstate_before`/`cstate_after` — **8.2** |

Bảy quyết định trải bảy lesson, mỗi cái lúc đó trông như chi tiết nhỏ. **C10 là
chỗ tất cả cùng trả công**, và nó **không vá được ở phút chót**.

### 2.3 Ba cái bẫy, cả ba được chặn tường minh

`scripts/replay_phase8_decisions.py`:

1. **Kiểm chuỗi hash TRƯỚC khi dựng lại.** Chuỗi gãy ⇒ audit không đáng tin ⇒
   dựng lại nó vô nghĩa. Thứ tự này quan trọng.
2. **`n_decisions > 0`.** Không có dòng `decision` nào thì `khớp == tổng == 0`
   và `0 == 0` là `True` → **PASS giả**. Có thêm `--min-decisions` (mặc định
   1000): C10 trên 5 tick là bằng chứng rỗng.
3. **Đọc theo thứ tự xoay vòng** (`audit.jsonl.1 → .2 → … → audit.jsonl`) và
   kiểm chuỗi **liền qua các file** — `verify_chain` kiểm cả `prev_sha256` lẫn
   tính liên tục của `seq`.

### 2.4 Kết quả C10 và C11 trên cùng soak production

Receipt `phase8_soak_production_v2.json` dùng đúng giao thức S6 v2 đã đăng ký:
production (`timeline_samples=0`, không sampler), bỏ **300 s warmup**, rồi chấm
cửa sổ **1800 s**. Kết quả C11: **968 KiB = 0,9453125 MiB** (ngưỡng ≤ 1 MiB),
0 ERROR, thread +0, 0 exception; audit xoay 4 lần và chuỗi hash liền qua cả 5
file. Toàn run kể cả transient tăng 1,8125 MiB được giữ riêng để không che
warmup. Verdict: **C11 PASS**, sát ngưỡng 56 KiB.

`phase8_c10_v2.json` dựng lại chính audit này: **2101/2101** quyết định khớp
bit-exact, `n_decisions >= 1800`, hash chain hợp lệ. Verdict: **C10 PASS**.

---

## 3. Xử lý verdict trung thực: bốn loại, không phải hai

| Verdict | Nghĩa | Ví dụ trong Phase 8 |
|---|---|---|
| **PASS** | thoả đúng như khoá trước | C1, C2, C3, C5, C7, C8 |
| **FAIL** | không thoả, hệ có vấn đề thật | — |
| **INVALID** | phép đo không sinh tín hiệu đo được | **C4** (biến kết cục bão hoà); S11 quiet TCP lượt 1 (đối chứng dương 0 act); ablation khối 4+ (Ditto 503) |
| **PASS-with-model-correction** | thoả sau khi **sửa cận**, nguyên nhân xác định và kiểm chứng được | **C6-a**: 14 = 13 + shutdown revert |

Loại thứ tư dễ bị lạm dụng, nên có **bốn rào**, và `accept_phase8.py` kiểm
chúng **bằng máy** (`CORRECTION_GATES`); thiếu một rào thì verdict **tự động
hạ xuống FAIL**:

```
1. cause_identified      nguyên nhân giải thích được bằng SỐ HỌC từ chính receipt
                         (hold cuối 92,4 s < lịch T_max 110 s ⇒ bị cắt ngang;
                          n_inject == n_revert ⇒ hành động 14 là revert tắt êm)
2. model_not_data        sửa vì SIM thiếu một cơ chế, KHÔNG vì đo được 14
3. known_answer_test     sim vá xong phải ra ĐÚNG 14, không phải "≥ 13"
4. declared_…            sai lệch + lý do vào receipt VÀ system card
```

Rào #2 là rào quan trọng nhất. *"Sửa cận vì đo được 14"* là gian lận. *"Sửa cận
vì sim không mô hình hoá tắt êm, và một hệ thật bắt buộc phải gỡ khi tắt"* là
khoa học. Khác nhau ở chỗ bản sửa **tiên đoán** được con số, chứ không **theo
sau** nó — và ở đây nó tiên đoán được: `run(always, 600.0).n_actions == 14`
chạy được mà không cần nhìn dữ liệu live.

---

## 4. Đổi tên: Failover → Closed-loop Mitigation

```
CŨ : "Failover: phát hiện → traffic chuyển hướng < 10 s"
MỚI: "Closed-loop Mitigation: phát hiện (act) → nguồn gây nghẽn bị giới hạn
      CÓ HIỆU LỰC < 10 s"      [C3, đo được p95 = 2032 ms, n = 9]
```

**Ba chứng cứ vật lý, ba file khác nhau** (bắt buộc ghi — đổi tên im lặng là
nới định nghĩa):

1. `ditto/topology_spec.json` — `srv1` chỉ có một cạnh `["srv1","s2"]`; không
   có LB/DNS/NAT nào đổi đích 10.0.0.4 → 10.0.0.5. `disableLink s2-srv1` = **cô
   lập dịch vụ**, không phải failover.
2. `mininet/topology.py:72` — `s2-s3` = **5 Mbps**; đường vòng là nút cổ chai.
   Dưới tải, "failover" làm mạng **tệ hơn**.
3. `mininet/controller_static.py:359-365` + `:222` — Ryu **đã** cập nhật
   `down_edges` rồi gọi `next_hop_table(excluded_edges=…)` trong **mili-giây**
   khi port down. Twin làm lại việc đó là **giẫm chân vòng trong** (cascade
   control).

⇒ Đóng góp của vòng ngoài là **CHÍNH SÁCH** (ai được bao nhiêu băng thông),
không phải **ĐƯỜNG ĐI**. Chỉ số được đổi tên cho khớp với thứ **thật sự được
đo**.

**Ghi chú về nơi lưu:** `MASTER_PLAN_V2.md` **không có trong repo này** (đã
kiểm: không file nào khớp `MASTER_PLAN*`). Bản đính chính có thẩm quyền nằm ở
ba nơi trong repo: `results/report/phase8_prereg.json::problem_renaming` (đã
niêm phong từ 8.1), `docs/phase-8/01-control-prereg.md §1`, và mục này. Khi
master plan được đưa vào repo, chép nguyên ba chứng cứ trên.

---

## 5. Bàn giao

### 5.1 Ai đọc gì

| Người | Đọc |
|---|---|
| Người vận hành | `SYSTEM_CARD_v4.md` §Giới hạn + §Không nên dùng cho + `05-dashboard.md` |
| Người kế nhiệm code | tài liệu này + `scripts/accept_phase8.py` + §5.2 |
| Hội đồng | `SYSTEM_CARD_v4.md` + chương kết quả |
| Chính bạn, 6 tháng sau | `07-stability.md` §lỗi live + bảng timeout nhiều tầng |

### 5.2 Bảng đóng băng (freeze set)

**Sửa file nào thì phải chạy lại phép đo nào.** Đây là thứ cứu người kế nhiệm
khỏi việc sửa một dòng rồi phá cả bộ test mà không hiểu vì sao.

| File | Sửa thì phải chạy lại |
|---|---|
| `controller/policy.py` | sim 8.2, C6, C7, **C10** |
| `controller/localize.py` | probe 8.1, C1, C2 |
| `controller/runner.py` | C3, C6, C9, C11, **C10** |
| `controller/sim.py` | C6 (cận), known-answer test |
| `controller/audit.py` | **C10** (chuỗi hash + xoay vòng) |
| `models/detector-release-1.0.0.json` | **toàn bộ Phase 6R, 7, 8** |
| `ml/fsm.py`, `ml/blast_radius.py`, `ml/intervention_log.py` | C8, C12, S11 |
| `bridge/command_agent.py` (handler + lease) | C8, C9, chaos |
| `bridge/detector_contract.py` | Phase 7 + 8 (hợp đồng công bố) |
| `mininet/topology.py` | **tất cả** |
| `measurements/blind_time.py` | C12, và **cả hai** receipt gap (§0.2) |
| `measurements/attribution.py` | C8-r |

> `controller/runner.py` và `controller/audit.py` **không nằm** trong
> `phase8_contract.pinned_sha256`. Đó là một lỗ hổng của hợp đồng 8.3 — chúng
> là hai file mà C10 phụ thuộc trực tiếp nhất. Ghi vào đây; ghim chúng ở Phase 9.

### 5.3 Công việc tiếp theo — nêu cụ thể, có tên cơ chế

1. **Ức chế theo TỪNG thực thể** thay vì toàn-hoặc-không (giới hạn C4). Sửa
   `ml/fsm.py`; phải hiệu chuẩn lại và chạy lại toàn bộ S-rows Phase 7.
2. **Đồng bộ hai lease**: `LEASE_TTL_S` (15 s) và `MAX_OPEN_S` (120 s) để xoá
   cửa sổ mù thừa 105 s (giới hạn D1). Cần một kênh để agent đóng sổ can thiệp.
3. **Biến kết cục bền với hiện tượng đệm**: `degraded_tick_fraction`
   (`measurements/degraded.py`, đã cài ở 8.8) hoặc đo ở phía **NHẬN** thay vì
   phía **GỬI** (giới hạn E1).
4. **Bền hoá `InterventionLog`** (hiện in-memory) để revert-first sống sót qua
   crash toàn tiến trình — **kèm đường thoát** để không tái diễn D3.
5. **Tìm điều kiện phân biệt hai chế độ ức chế** (§0.2, ẩn số được khai). Đây
   là việc số 1 về mặt khoa học: một cơ chế an toàn có hai chế độ mà ta không
   biết cái gì chuyển giữa chúng.
6. **Mở rộng topology và loại tấn công** để kiểm tổng quát hoá (giới hạn F1).

---

## 6. Sai lệch giao thức — khai đủ

### 6.1 Chaos: 2 lượt/dòng thay vì ≥ 5 (từ 8.7)

```
đăng ký:     ≥ 5 lượt/dòng          thực hiện: 2 lượt/dòng (phase8_chaos_v6)
nguyên nhân: trần hạ tầng 3,5 h (Mongo 252,4/256 MiB, truy vấn 55 s, HTTP 503)
             + 4 lỗi thật phải sửa giữa chiến dịch
hệ quả:      dòng `second_flood` có phương sai lớn (1,74 vs 25,16 s, tỷ số 14×)
             -> KHÔNG được đưa vào system card như một ước lượng
các dòng khác (control, c9, drift, restart, agent_kill) NHẤT QUÁN giữa hai lượt
```

Phải phân biệt hai loại kết luận:

- **kết luận ĐỊNH TÍNH vững** — *lease có tự gỡ không?* **Có, 2/2.*
  *drift có được kéo về không?* **Có, 2/2.** *bản ghi vô chủ có được đóng
  không?* **Có, 2/2.**
- **ước lượng ĐỊNH LƯỢNG sơ bộ** — *bao lâu?* 10,73 và 12,33 s, **n = 2**.

Với `n = 2` và tỷ số 14×, `second_flood` được chạy lại ở 8.8 với **n = 5**.

### 6.2 Poisson: 3 seed thay vì "N"

`N` không được cố định ở 8.7; 8.8 chọn **3 seed** (0, 1, 2 — đúng ba seed đầu
mà sim dùng), so **theo cặp**: cùng seed ⇒ cùng lịch flood ⇒ so được từng lượt
chứ không chỉ so phân phối. Ràng buộc: 3 × 1800 s ≈ 90 phút, cộng soak và chaos
là ~2,5 h — dưới trần hạ tầng 3,5 h nhưng không nhiều.

### 6.3 Dashboard được build lại ở 8.8

`dashboard/dist` build lại sau khi sửa `controlView.js` (IDLE bị trói tay).
Đây là thay đổi của **lớp trình bày**; nó không đụng vào vòng điều khiển, và
C9-a được đo **trên bản build mới**.

### 6.4 `controller/sim.py` trôi khỏi SHA đã ghim

Cố ý, có lý do, có known-answer test — xem §0.1 và §1.4. Mọi trôi khác đều là
trôi từ 8.4–8.7 và đều đã khai.

### 6.5 Chiến dịch Poisson lượt 1 bị VÔ HIỆU do lỗi thao tác

Receipt: `results/report/phase8_poisson_invalidated.json`
Hiện vật giữ nguyên: `logs/phase8_stability/poisson_003315_INVALIDATED/`

```
đăng ký:     3 seed × 1800 s trong MỘT lần gọi harness
lượt 1:      bắt đầu 00:33:13Z
             seed 0 xong 01:03Z  (1856 dòng audit)  — HỢP LỆ
             seed 1 xong 01:33Z  (1901 dòng audit)  — HỢP LỆ
             seed 2 bắt đầu 01:33Z                  — VÔ HIỆU
nguyên nhân: một phiên làm việc khác chạy `sudo mn -c` lúc ~01:45:30Z để dọn
             một topology mà nó TƯỞNG là rác. Đó chính là topology mà chiến
             dịch đang dùng. `mn -c` cũng giết Ryu.
triệu chứng: collector ngừng sinh snapshot lúc 01:46:50Z, trong khi vòng
             controller VẪN tick và VẪN ghi audit → seed 2 chạy MÙ ~12 phút
             mà không có dấu hiệu nào trong chính run đó.
```

**Đây là phép đo vô hiệu do hạ tầng, không phải giả thuyết bị bác bỏ** — cùng
cách phân biệt đã áp dụng ở ablation 8.6 (Ditto 503) và amendment 8.3.

**Vì sao không ghép seed 0/1 của lượt 1 với một seed 2 chạy riêng:** ghép hai
lần gọi harness khác nhau làm chiến dịch mất tính đồng nhất mà **không ai kiểm
lại được** từ hiện vật — đúng thứ mà cả Lesson 8.8 tồn tại để chống. Chạy lại
**cả ba seed trong một lần gọi**. Lượt 1 **không được dùng để tính bất kỳ con
số nào**.

> 🧠 Bài học vận hành, đáng ghi vì nó suýt lọt: **seed 2 không tự biết nó đã
> hỏng.** Audit vẫn liền chuỗi, controller vẫn tick, không có ERROR nào. Chỉ
> có *sự vắng mặt* của snapshot collector mới tố cáo — và sự vắng mặt thì
> không có dòng log nào cả. Cùng chữ ký với lỗi live #1 ở 8.4 và với lỗi
> `stale_intervention` ở 8.7: **hỏng im lặng là chế độ hỏng mặc định của hệ
> này.** Một chiến dịch dài cần một *heartbeat của nguồn dữ liệu*, không chỉ
> heartbeat của controller.
