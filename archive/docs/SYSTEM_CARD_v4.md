# System card v4.1 — DT4N: detector + twin + **vòng điều khiển kín**

Thay `docs/phase-7/model-card-v3.md`. Bản v3 mô tả một hệ **chỉ quan sát**. Bản
v4 thêm thứ làm hệ này khác về bản chất: **một actuator**. Một hệ quan sát hỏng
thì mất dữ liệu; một hệ có actuator hỏng thì **để lại dấu vết vật lý trên mạng
mà không ai sở hữu**. Vì vậy mục quan trọng nhất của tài liệu này không phải
§2 (hiệu năng) mà **§4 (Giới hạn)** và **§5 (Không nên dùng cho)**.

- Nghiệm thu: `results/report/phase8_acceptance.json`
  (sinh bằng `python3 scripts/accept_phase8.py --strict`)
- Bằng chứng: mọi dòng trong §4 có **một số** và **một receipt**.
- Tài liệu đọc được: `docs/phase-8/08-acceptance.md`

---

## 0. Model card / system card là gì, và vì sao bản này dài ở chỗ giới hạn

**Model card** (Mitchell et al., 2019) là tài liệu ngắn đi kèm một mô hình, mô
tả: nó làm gì, được đánh giá thế nào, **hoạt động kém ở đâu**, và **không nên
dùng cho việc gì**. Triết lý: *một hệ không có tài liệu về giới hạn thì không
triển khai được một cách có trách nhiệm* — người dùng **sẽ** tìm ra giới hạn,
bằng cách bị hại.

**System card** mở rộng cho cả hệ thống, không chỉ mô hình. Với Phase 8 điều
này là bắt buộc, vì thứ có thể gây hại không phải mô hình mà là **actuator** và
**vòng kín**.

Mục "Giới hạn" là mục có giá trị **nghiên cứu** cao nhất, vì ba lý do độc lập:

1. **Hội đồng sẽ tìm ra giới hạn dù có viết hay không.** Viết trước ⇒ tác giả
   là người hiểu hệ. Để họ tìm ra ⇒ tác giả là người không biết.
2. **Giới hạn có số đo là bằng chứng đã đo.** *"Cửa sổ mù thừa 105,01 s"* chứng
   minh C9-b đã chạy. *"Có thể có giới hạn"* không chứng minh gì cả.
3. **Đóng góp nghiên cứu nằm ở đó.** *"Ức chế toàn-hoặc-không có hai chế độ và
   ta chưa biết cái gì chuyển giữa chúng"* là một phát hiện thiết kế. Nó chỉ
   tồn tại vì đã đo và đã khai.

---

## 1. Dùng để làm gì

Phát hiện bất thường mạng ở mức tick 1 giây trên bản sao số, **và giới hạn tốc
độ tại nguồn** của client bị chỉ mặt, tự động, có thể đảo ngược.

- Actuator **duy nhất**: `setBandwidth` trên link truy nhập `<client>-s1`,
  giới hạn 7,0 Mbps (trần tải hợp lệ cao nhất từng quan sát trên 8 run TRAIN =
  6,181986 Mbps, làm tròn lên).
- Circuit breaker 4 trạng thái `IDLE → MITIGATING → PROBING → IDLE`, backoff
  mũ `T_k = min(15 · 2^k, 110) s`, gỡ **theo lịch** chứ không theo "trông có
  vẻ khoẻ".
- Vùng vận hành hợp lệ (kế thừa Phase 7): min txRate client ≤ **4,3126 Mbps**.
  Ngoài vùng: detector tự khai không có thẩm quyền, controller **không hành
  động** (N16).

**Đây không phải failover.** Xem §6.

---

## 2. Hiệu năng đã nghiệm thu

| Tiêu chí | Đo được | Ngưỡng | Verdict |
|---|---|---|---|
| **C1** hành động đúng nguồn | E1: **12/20 sai mục tiêu**; h2→srv2 đúng 5/5, ba kịch bản còn lại mỗi kịch bản sai 4/5 | 100% | **FAIL** |
| **C2** không hành động với admin_down/shift/degrade | 0 lần (0/20 run offline; 0 hành động / 600 s quiet live) | 0 | PASS |
| **C3** `act` → giới hạn **có hiệu lực** (p95) | **2032 ms** (n = 9, p50 1027 ms) | ≤ 10 000 ms | PASS |
| **C4** nạn nhân hồi phục ≥ 80% nền (p95) | — | ≤ 15 s | **INVALID** (§4 E1) |
| **C5** A/B goodput nạn nhân | **+1,893 Mbps**, CI95 [1,854; 1,931], p = 0,0078 (8/8 khối cùng chiều) | CI95 > 0 | PASS |
| **C6-a** số hành động / flood 600 s | **14** = 13 (chính sách) + 1 (revert của tắt êm); `min_hold` 16,0 s ≥ T₀ | ≤ cận sim | **PASS-with-model-correction** |
| **C6-b** số hành động / 600 s bình thường | **0** | 0 | PASS |
| **C6-c** Poisson 1800 s × 3 seed | live = **[12, 18, 0]**, sim cùng seed = **[12, 18, 0]**, Δ = **[0, 0, 0]** | trong dải sim | PASS |
| **C7** hành động trên trigger bị cấm | 0 | 0 | PASS |
| **C8** S11: controller không tự kích hoạt detector | 0 (nhánh `quiet_udp`, phép đo có hiệu lực) | 0 | PASS |
| **C8-r** hồi quy S11 dưới vòng kín (vị từ `t_source`) | **0 Loại I**; 7 tick không quy kết vì `t_source` ngoài mọi cửa sổ | 0 | PASS |
| **C9-a** controller chết → UI STALE | max **3178 ms** (n = 5); detector vẫn fresh | ≤ 5 s | PASS |
| **C9-b** controller chết → vật lý an toàn | **10,73 s** và **12,33 s** (n = 2) | ≤ TTL + biên | PASS |
| **C10** dựng lại bit-exact từ audit | v2: **2101/2101**; A2/v3: **1803/1803** quyết định | 100% | PASS |
| **C11** soak 30 phút: ΔRSS, ERROR | **0,9453 MiB** (968 KiB); 0 ERROR; thread +0; 0 exception | ≤ 1 MiB; 0 | PASS |
| **C12** tỷ lệ thời gian mù | §4 C2–C3 | báo cáo, không đặt ngưỡng | PASS |

Bốn loại verdict và bốn rào của loại thứ tư: `08-acceptance.md §3`.

---

## 3. Chế độ hỏng — hệ nói gì khi CHÍNH NÓ hỏng

Kế thừa FM8–FM13 của v3. Bốn chế độ **mới** do actuator sinh ra, cả bốn tìm
được bằng **fault injection ở 8.7**, không phải bằng suy luận:

| FM | Hỏng cái gì | Người vận hành thấy gì | Số đo |
|---|---|---|---|
| **FM14** | Controller chết giữa lúc đang giảm thiểu | `controlloop` STALE; **lease 15 s tự gỡ** giới hạn ⇒ mạng an toàn. Nhưng sổ can thiệp vẫn "mở" tới `MAX_OPEN_S` = 120 s ⇒ **cảm biến vẫn mù thêm ~105 s** sau khi vật lý đã an toàn | 10,73 / 12,33 s vật lý; 115,74 / 117,34 s cảm biến; **mù thừa 105,01 s** (`phase8_chaos_v6.json`) |
| **FM15** | `command_agent` chết | Lease chết **theo agent** (dict trong bộ nhớ). Tự lành bằng vòng **reconcile**, KHÔNG bằng watchdog: cache dedup mất theo agent nên lệnh gửi lại được thực thi lại — và **vô hại đúng vì lệnh tuyệt đối** (`{"bw": 7.0}`, không bao giờ tương đối). Chuỗi 8.3 → 8.4 → 8.7 khép kín | `phase8_chaos_v6.json::agent_kill` |
| **FM16** | Trạng thái vật lý trôi ngoài luồng (ai đó `tc` bằng tay) | Vòng reconcile kéo về trong **1,28–1,89 s**, `drift_fixes += 1`; sau 3 lần trôi liên tiếp thì **giãn chu kỳ gửi lại** (một vòng sửa lỗi lặp mà lỗi không mất là một **nguồn tải**, không còn là sửa lỗi) | `phase8_chaos_v6.json::drift` |
| **FM17** ⚠️ | **Bản ghi can thiệp vô chủ** (controller chết sau khi ghi `inject`, controller mới chỉ sửa `bw` mà không đóng sổ) | **KHÔNG CÓ GÌ** trong bản 8.7: không exception, không ERROR, tick đều, UI xanh — và controller **không bao giờ hành động nữa** trong khi mạng đang bị flood thật. `stale_open()` luôn trả bản ghi đó ⇒ theo N15 mọi controller sau đó **từ chối hành động**. Im lặng, vĩnh viễn, **do chính một cơ chế an toàn gây ra** | chaos 8.7 lỗi #2 |

**FM17 là chế độ hỏng nguy hiểm nhất của cả Phase 8**, vì cả ba đặc điểm cùng
lúc: im lặng, vĩnh viễn (khởi động lại không cứu nếu log được bền hoá), và do
chính cơ chế fail-safe N15 gây ra. Mẫu này có tên trong kỹ thuật an toàn: **một
cơ chế fail-safe cần một đường thoát.** Không có đường thoát, "an toàn" thành
"vô dụng vĩnh viễn" — và trong một hệ điều khiển, vô dụng vĩnh viễn **cũng là
một chế độ hỏng**.

Ba lớp phòng thủ đã cài (8.7 + 8.8):

1. `ControlRunner._close_orphan_interventions()` — ghi `revert` đóng sổ cho mọi
   `inject` chưa đóng **của các lần chạy trước** (không đụng vào bản ghi của
   chính mình: đường thoát không được biến thành cái gây ra đúng vấn đề nó
   chữa). Test hồi quy:
   `test_phase8_acceptance_fixes.py::test_revert_first_phai_dong_ca_so_sach`.
2. **Cảnh báo vận hành** — `stale_intervention` liên tục ≥ 30 tick ⇒
   `log.error("… controller đang bị TẮT VĨNH VIỄN (N15)")`. Im lặng là đặc
   điểm tệ nhất của lỗi này, nên tối thiểu phải có tiếng.
3. **UI** — `mode = IDLE` + `reason = idle_stale_intervention` nay hiện
   **"KHÔNG THỂ HÀNH ĐỘNG"** (severity `warning`), **không** phải "RẢNH"; và
   `allClear()` trả `false`. Hai trạng thái đòi hỏi hai hành vi khác nhau từ
   người vận hành thì không được chia chung một nhãn.
   (`dashboard/src/lib/controlView.js`, 6 test mới.)

---

## 4. GIỚI HẠN — mục dài nhất, và đó là đúng

Mỗi dòng: **một số** và **một receipt**. Đừng rút gọn mục này cho "gọn".

### A. Phạm vi và khả năng điều khiển

| | Giới hạn | Receipt |
|---|---|---|
| **A1** | Actuator **duy nhất**: `setBandwidth` trên link truy nhập client. Hệ **KHÔNG** làm failover đường đi (Ryu đã làm ở tầng dữ liệu, mili-giây) | `phase8_prereg.json::controllability_table` |
| **A2** | Chỉ hành động khi thủ phạm là **MỘT** client trong `evidence.affected`. ≥ 2 ứng viên ⇒ **fail-closed, im lặng** | `controller/localize.py` (luật v2) |
| **A3** | Giới hạn ở link truy nhập cũng **bóp traffic HỢP LỆ của thủ phạm**: h1 **−11,97 Mbps** (CI95 [−12,15; −11,81]) trong A/B | `phase8_ab_c5.json::secondary.h1` |
| **A4** | Giới hạn là **7,0 Mbps cố định**, không thích nghi. Nó đến từ trần tải hợp lệ trên **8 run train** (6,181986 Mbps). Tải hợp lệ vượt con số đó sẽ bị bóp oan | `phase8_prereg.json::actuator.limit_derivation` |
| **A5** | Sau khi mục tiêu đổi trong PROBING, controller cách ly **14 s**. Recovery burst không bị re-latch ngay, nhưng một thủ phạm thật xuất hiện trong khoảng đó có thể bị trễ tối đa 14 s | amendment A2, `test_phase8_quarantine.py` |
| **A6** | Nếu detector còn `act` sau khi sự cố gốc hết, controller có thể giới hạn một host có bất thường dưới ngưỡng kéo dài. E1 đo được **12/20** trial nhắm sai theo đường này | `phase8_closure_diagnostics.json::D1,D3` |

### B. Khả năng phát hiện (kế thừa Phase 6/7, vẫn còn nguyên)

| | Giới hạn | Receipt |
|---|---|---|
| **B1** | `degrade` trên s1-s2 **KHÔNG BAO GIỜ** vào `act` ⇒ controller **không bao giờ** phản ứng với loại sự cố này. 12/12 run degrade: 0 latch | `phase8_actionability.json::latched_by_fault.degrade` |
| **B2** | **Nạn nhân bị bỏ đói KHÔNG được phát hiện** (h3 2,15 → 0,01 Mbps mà không vào `affected`). Hệ thấy **thủ phạm**, không thấy **hậu quả** | probe 8.1 |
| **B3** | Sự kiện ngắn hơn `n_act × tick` (**2 s**) không thể bắt — giới hạn Nyquist của cảm biến | `phase8_sim_predictions.json::sim_params.n_act` |
| **B4** | `admin_down` (4 run) và `shift` (4 run): 0 latch — đúng thiết kế, nhưng nghĩa là **hệ mù với chúng về mặt hành động** | `phase8_actionability.json` |
| **B5** | Kế thừa **S1 = 0,30**: tỷ lệ phát hiện theo sự cố của envelope-only, so với mục tiêu 0,875. Sự cố mà TCP hấp thụ thành mức thông lượng thấp hơn trong biên đã hiệu chuẩn thì bị bỏ sót | Phase 6R, `model-card-v3.md` |

### C. Khả năng quan sát TRONG LÚC can thiệp

| | Giới hạn | Receipt |
|---|---|---|
| **C1** | Vùng ức chế **15/16** thực thể của mô hình | `phase8_prereg.json::suppression_zone` |
| **C2** | Tỷ lệ mù phải báo **theo chế độ**. Campaign cũ: 96,3% trong sự cố, cửa sổ dài nhất 119 s. E3 mới: **3/3 run** vào SUPPRESSION với 552–561 tick suppressed/600 s | `phase8_stability_flood.json`, `phase8_suppression_modes.json` |
| **C3** | Trên tổng thời gian: 0,0% ở quiet; Poisson trung bình 12,86%; flood suppression gần toàn cửa sổ. Không số đơn nào là “tỷ lệ mù của hệ” | `phase8_poisson.json`, `phase8_suppression_modes.json` |
| **C4** ⚠️ | Mode phần lớn do baseline `link-s2-s3` của **từng phiên** quyết định: A/B và E1 có s2-s3 trong **100%** tick normal và 0 suppressed; bốn stability-flood chỉ **0–10%**, với 552–561 suppressed tick. H-DURATION là tương quan hậu kiểm, chưa phải quan hệ nhân quả | `phase8_closure_diagnostics.json::D2_s2s3_baseline` |
| | *Đề xuất (ngoài phạm vi):* ức chế theo **TỪNG thực thể** thay vì toàn-hoặc-không | `08-acceptance.md §5.3` |

### D. Chế độ hỏng và hồi phục

| | Giới hạn | Receipt |
|---|---|---|
| **D1** | Controller chết: vật lý an toàn sau **10,73–12,33 s**; nhưng **cửa sổ mù THỪA ≈ 105,01 s** vì `LEASE_TTL_S` (15 s) ≠ `MAX_OPEN_S` (120 s). Hai lease, hai đồng hồ, không ai đồng bộ chúng | `phase8_chaos_v6.json::c9` |
| **D2** | `command_agent` chết: lease chết theo (dict trong bộ nhớ). Tự lành bằng **reconcile**, KHÔNG bằng watchdog | `phase8_chaos_v6.json::agent_kill` |
| **D3** | Bản ghi can thiệp **vô chủ**, nếu không được đóng, làm N15 **TẮT VĨNH VIỄN** mọi controller sau đó — im lặng. Đã vá + test hồi quy + cảnh báo + UI (§3 FM17) | chaos 8.7 lỗi #2 |
| **D4** | `InterventionLog` hiện **in-memory**. Revert-first **không** sống sót qua crash toàn tiến trình; nó chỉ sống sót qua crash của controller | `ml/intervention_log.py` |

### E. Giới hạn của PHÉP ĐO (khác với giới hạn của hệ)

| | Giới hạn | Receipt |
|---|---|---|
| **E1** | Biến kết cục chính (trung bình txRate nạn nhân) **BÃO HOÀ** ở tốc độ chào TCP: **không phân biệt được 93% bảo vệ với 100%**. CV nhánh A = **0,0466%**; trung bình nhánh A (2,1462) ≈ h2 chưa bị động tới (2,1352). Phần bù do recovery burst chỉ ≈ **0,15 Mbps** | `phase8_ab_addendum.json` |
| **E2** | Ablation là **NULL TẠI TRẦN**, không phải bằng chứng tương đương: cả hai nhánh chạm cùng một trần nên phép so sánh **không có khả năng phân biệt**. Bằng chứng phân biệt thật nằm ở **ca âm tính offline**: luật ngưỡng chỉ mặt sai ở **8/43 run** (shift, degrade, load10M) và **nhắm vào nạn nhân**; pipeline 0 lần | `phase8_ablation_rerun.json`, `phase8_localization_probe.json::gap_rule_wrong_target_runs` |
| **E3** | Chiến dịch đo liên tục > **~3,5 h** chạm trần bộ nhớ Ditto/Mongo (**252,4/256 MiB**, truy vấn **55 s**, HTTP 503). Cổng hạ tầng phải cảnh báo theo **triệu chứng** (latency + mã lỗi), không theo **tài nguyên**: 90% Mongo là bình thường (đo được 75,4% lúc khoẻ) | 8.6 + 8.7, `scripts/phase8_infra_health.py` |
| **E4** | `second_flood`: **5/5 phát hiện**, 0 censored; latency **[1,54; 1,74; 18,34; 21,95; 24,15] s**, median 18,34 s. Cụm chậm có 80–103 mẫu suppressed, cụm nhanh 1–2; n=5 chỉ hỗ trợ kết luận định tính | `phase8_chaos_second_flood.json` |
| **E5** | Sửa một phần từ 8.9: receipt mới E1/E3/E4 khai SHA prereg/contract/policy. Năm receipt cũ vẫn không khai tham chiếu và không được hồi tố | `phase8_acceptance.json::dependency_chain_not_declared` |
| **E6** | Harness E1 chấp nhận phiên “bẩn” vì `require_clean` chỉ kiểm `state == normal`, không kiểm client ngoài cuộc trong `affected`. **Normal không đồng nghĩa sạch**; 12 phiên bẩn trùng 1-1 với 12 wrong-target | `phase8_closure_diagnostics.json::D1_contamination` |

### F. Phạm vi thực nghiệm

| | Giới hạn |
|---|---|
| **F1** | **Một** topology (3 client, 2 server, 3 switch), **một** loại flood (UDP 47 Mbps h1→srv1), **một** tải nền (TCP 2 Mbps/client). **Không có bằng chứng về tổng quát hoá.** |
| **F2** | Dữ liệu dùng để thiết kế luật định vị **đã mở** từ Phase 6R/7 ⇒ kết quả offline ở 8.1 là **in-sample**; `n_flood = 4`. |
| **F3** | Mininet, **không phải phần cứng thật**. Không có mất gói vật lý, không có jitter đường truyền thật, không có nhiều tenant. |
| **F4** | Thủ phạm luôn là **một** client. Kịch bản **hai nguồn gây nghẽn đồng thời chưa bao giờ được chạy**. |
| **F5** | Sim 8.2 mù cấu trúc với lỗi re-latch: detector mô phỏng không sinh ứng viên là nạn nhân, nên 2.000 seed trùng nhau không kiểm được A2. |

---

## 5. KHÔNG nên dùng hệ này để

Với C1 FAIL ở 8.9, hệ chỉ phù hợp ở chế độ **đề xuất hành động để con người
duyệt**. Không bật actuator tự động ngoài đúng phạm vi đã chứng minh.

- **Phản ứng với suy giảm chất lượng (`degrade`)** — B1, B5.
- **Bảo vệ khi có ≥ 2 nguồn gây nghẽn đồng thời** — A2 (fail-closed im lặng) +
  F4 (chưa từng chạy).
- **Phát hiện sự cố THỨ HAI trong lúc đang giảm thiểu sự cố thứ nhất** —
  C1–C4. Đây là hệ quả trực tiếp của thiết kế ức chế, không phải một bug.
- **Thay thế failover đường đi** — A1, §6.
- **Bảo đảm chất lượng cho traffic hợp lệ của host bị chỉ mặt** — A3.
- **Phát hiện hậu quả lên nạn nhân** — B2. Hệ thấy thủ phạm, không thấy nạn nhân.
- **Bất kỳ môi trường nào khác topology/tải đã đo** — F1, F3.

---

## 6. Chỉ số được đổi tên: Failover → Closed-loop Mitigation

```
CŨ : "Failover: phát hiện → traffic chuyển hướng < 10 s"
MỚI: "Closed-loop Mitigation: phát hiện (act) → nguồn gây nghẽn bị giới hạn
      CÓ HIỆU LỰC < 10 s"          [C3: p95 = 2032 ms]
```

Ba chứng cứ vật lý, ba file khác nhau:

1. `ditto/topology_spec.json` — `srv1` chỉ có cạnh `["srv1","s2"]`; không có
   LB/DNS/NAT đổi đích ⇒ `disableLink s2-srv1` là **cô lập dịch vụ**.
2. `mininet/topology.py:72` — `s2-s3` = **5 Mbps**; đường vòng là nút cổ chai,
   dưới tải "failover" làm mạng **tệ hơn**.
3. `mininet/controller_static.py:359-365`, `:222` — Ryu **đã** tính lại đường
   trong **mili-giây** khi port down. Twin làm lại = **giẫm chân vòng trong**.

⇒ Đóng góp của vòng ngoài là **CHÍNH SÁCH**, không phải **ĐƯỜNG ĐI**.

> Đổi tên chỉ số mà **không** nêu lý do là **nới định nghĩa** (moving the
> goalposts) và là lỗi nghiên cứu nghiêm trọng. Đổi tên **kèm chứng cứ vật lý**
> là **đính chính**. Khác nhau ở đúng ba mục trên.

---

## 7. Điều kiện triển khai

1. Tải nằm **trong** vùng vận hành đã hiệu chuẩn (min txRate client ≤ 4,3126
   Mbps); ngoài vùng, controller **không hành động** và phải nói ra.
2. `InterventionLog` phải được **bền hoá** trước khi chạy thật (D4), **kèm
   đường thoát** cho bản ghi vô chủ (D3).
3. Hai lease (`LEASE_TTL_S` 15 s, `MAX_OPEN_S` 120 s) phải được đồng bộ, nếu
   không chấp nhận cửa sổ mù thừa ~105 s (D1).
4. Người vận hành phải đọc **§4** và **§5** trước khi bật vòng kín.
5. Không bật vòng kín tự động khi `scripts/accept_phase8.py --strict` còn trả
   khác 0. Với receipt 8.9 hiện tại, chỉ chạy proposal + human approval.

---

## 8. Chưa chứng minh được

- Tổng quát hoá sang topology/tải/loại tấn công khác (F1–F4).
- Hành vi khi có **hai** thủ phạm đồng thời.
- Biến quyết định chế độ ức chế (C4); E3 chỉ xác nhận SUPPRESSION ở 3/3 run.
- Rằng biến kết cục nào **không** bão hoà đo đúng hiệu quả bảo vệ. Ứng viên
  `degraded_tick_fraction` mới được đo lần đầu ở 8.8, chưa có đối chứng.
