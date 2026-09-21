# Phase 8.7 — Chạy lâu, bị phá, và không tự kích hoạt

8.6 hỏi *"có ích không"*. 8.7 hỏi câu khó hơn: **có an toàn khi chạy lâu, và khi
bị phá đúng lúc đang tác động không?** Đây là lesson quyết định hệ này là *một
thí nghiệm chạy được* hay *một thứ có thể triển khai*.

---

## 1. Nợ mang sang

| Nợ | Từ | Trả ở đâu |
|---|---|---|
| `degraded_tick_fraction` + lưu tick thô | 8.6 hiệu ứng trần | soak + harness ổn định |
| Cửa sổ mù thừa ≤ 103 s | 8.4 mâu thuẫn lease/`MAX_OPEN_S` | **C9-b** |
| Drift ngoài luồng (`drift_fixes = 0` live) | 8.4 | dòng chaos `drift` |
| C12 tỷ lệ thời gian mù | hoãn từ 8.1, 8.5 | `measurements/blind_time.py` |
| Trần hạ tầng ~3,5 h | 8.6 sự cố Mongo | lịch chia phiên + `phase8_infra_health.py` |

## 2. Dao động là một phép đo, không phải cảm giác

"Chạy 10 phút thấy ổn định" không kiểm chứng được. Ba chế độ, tiêu chí đếm khoá
trước:

| Chế độ | Thời lượng | Tiêu chí | Cận từ đâu |
|---|---|---|---|
| flood liên tục | 600 s | hành động ≤ **13** **và** không cặp nào giữ < `T₀` | sim `a38c6434` |
| bình thường | 600 s | **0** hành động | sim |
| Poisson | 1800 s × N | dùng **đúng N seed đầu của sim**, so **theo cặp** | sim: p50 14, p95 26, max 41 |

**Vì sao cần tiêu chí thứ hai:** đếm số hành động một mình **che giấu** dao động —
12 hành động dồn vào 40 giây vẫn là dao động. Nên kiểm thêm `min_hold_s` và
khoảng cách giữa các sự kiện.

**Vì sao dùng cùng seed với sim:** biến so sánh phân bố (cần nhiều lượt) thành
**so sánh theo cặp** (khả thi với n nhỏ) — cùng ý tưởng với khối ABBA ở 8.6.

## 3. Quy kết nhân quả cho hồi quy S11 — luật khoá trước

Dưới vòng kín thật, `act` có **hai nguồn chồng lên nhau**: flood thật (đúng) và
hành động của controller (thứ S11 cấm). Luật quy kết, **suy từ luật ức chế đã
ghim** trong `detector-release-1.0.0` và từ phép đo 8.3 (`phase8_s11_bw_flood.json`,
1/3 round không bị ức chế), **không** chọn sau khi nhìn số 8.7:

```
Với mỗi tick `act` trong khoảng [t_inject, t_revert + cooldown_s]:

Loại I  — mọi entity trong evidence.affected ⊆ blast_radius(<target>-s1)
          → ức chế LẼ RA phải bật mà không bật → QUY CHO CONTROLLER → GATE = 0
Loại II — có ≥ 1 entity NGOÀI vùng (thực tế: link-s2-s3)
          → luật ức chế đã ghim không áp dụng → QUY CHO FLOOD → báo cáo
```

> **Điều cấm:** nếu Loại I > 0 thì S11 thật sự bị phá dưới vòng kín → **phải điều
> tra**, tuyệt đối **không** đổi tiêu chí quy kết cho vừa số liệu.

## 4. DỰ ĐOÁN — khoá trước khi chạy

> Commit chứa mục này được tạo **trước** khi bất kỳ harness 8.7 nào chạy.

```
C6-a flood 600 s : n_actions <= 13; min_hold_s >= T0 - 0,5 = 14,5 s
     Cơ sở: sim a38c6434 (13 hành động, 7 mitigation) + đo thật ở 8.6 addendum
     (hold 15/30/60 đúng lịch).
     LƯU Ý: 8.6 addendum cho thấy gap thật chỉ 1–5 s (không phải ~9–13 s như
     sim), nên số chu kỳ trong 600 s có thể CAO HƠN sim. Nếu n_actions > 13,
     đó KHÔNG phải dao động mà là hệ quả của "lỗ hổng ức chế" đã đo ở 8.3 —
     phải phân biệt bằng min_hold_s: nếu mọi hold >= T0 thì lịch backoff vẫn
     được tôn trọng.

C6-b bình thường 600 s : 0 hành động (khớp sim)

C6-c Poisson 1800 s : mỗi lượt nằm trong [min, max] của sim (0..41)

C7 live : 0 hành động mới khi detector chết / Ditto đứt / tải ngoài dải

S11 hồi quy : Loại I = 0 (GATE). Loại II > 0, kỳ vọng ~1/3 số chu kỳ
     (cơ sở: phase8_s11_bw_flood.json)

C9-a  UI STALE <= 5 s sau khi controller chết (E2E 8.5 đã có kịch bản)
C9-b  bw về 20 <= LEASE_TTL 15 + watchdog 1 + lệnh 0,98 ~ 17 s
      cửa sổ mù thừa = t_sensor_restored − t_physical_safe ~ 103 s
      (MAX_OPEN_S 120 − 17)

drift : controller kéo bw về 7 trong <= CONFIRM_GRACE 2 s + 1 tick ~ 3 s;
        drift_fixes += đúng 1

second_flood : flood h2→srv2 đi qua s1-s3, KHÁC đường h1, nhưng TOÀN BỘ đường
        đó nằm trong blast_radius(h1-s1) = 15/16 entity (gồm host-h2,
        link-h2-s1, link-s1-s3, link-s3-srv2, host-srv2).
        => DỰ ĐOÁN: bị che cho tới khi episode của h1 đóng; thời gian bị che
        ~ (phần còn lại của T_k) + cooldown 8 s; xấu nhất ~118 s với T_max 110.

agent_kill : lease sống trong dict TRONG BỘ NHỚ của command_agent. Mất cache
        lease => watchdog không có gì để phục hồi => bw KẸT ở 7 nếu controller
        cũng chết. Nhưng controller còn sống nên vòng reconcile sẽ gửi lại lệnh
        (cid mới theo chu kỳ renewal, dedup đã mất nên không bị chặn) và lease
        được ARM LẠI. DỰ ĐOÁN: still_limited = true và commands_since > 0,
        tức là hệ tự lành bằng reconcile chứ không bằng watchdog.

restart : orphans_reverted >= 1; exceptions = 0 (fencing token ở 8.6 đã sửa);
        t_revert_first <= 15 s

ĐIỀU KIỆN VÔ HIỆU: mọi lượt có `phase8_infra_health.check()` không khoẻ
        (Ditto != 200, latency > 2 s, hoặc Mongo > 90% trần) là VÔ HIỆU do hạ
        tầng — KHÁC với giả thuyết bị bác bỏ.
```

## 5. C12 — ba con số, không phải một

```
C12-a  mù / TỔNG thời gian vận hành        (nghe nhẹ nếu báo một mình)
C12-b  mù / thời gian CÓ SỰ CỐ             (nghe thảm hoạ nếu báo một mình)
C12-c  cửa sổ mù dài nhất liên tục (giây)  (con số cho model card)
```

`measurements/blind_time.py` (thuần, 8 known-answer test) tính từ **chính cặp
inject/revert** — cùng nguồn mà `ml/fsm.py` dùng để quyết định ức chế, nên đây là
kế toán lại của **cơ chế**, không phải một ước lượng mới. Có test cho **gộp khoảng
chồng lấn** (quên bước này → đếm trùng → tỷ lệ > 100%) và cho can thiệp **chưa
đóng** (kết thúc đúng ở `MAX_OPEN_S`, y như `InterventionLog.active()`).

## 6. Lịch chạy — trần hạ tầng là ràng buộc thiết kế

Phát hiện 8.6 (Mongo chạm trần cgroup sau ~3,5 h) không phải sự cố lẻ; nó là ràng
buộc lịch trình:

```
Phiên 1  flood 600 s + quiet 600 s + Poisson                 → restart Ditto
Phiên 2  chaos (6 dòng × N lượt, có nhánh đối chứng)          → restart Ditto
Phiên 3  soak C11 — LIÊN TỤC, không restart giữa chừng
```

Ba quy tắc: **không restart giữa một lượt**; **soak phải liên tục**; **mọi lần
restart vào receipt** kèm RSS Mongo trước/sau. `phase8_infra_health.check()` chạy
**trước mỗi lượt** và ném `InfraUnhealthy` khi Mongo > 90% trần — cảnh báo **trước**
khi phép đo hỏng, thay vì phát hiện sau bốn khối như ở 8.6.

## 7. Files

| File | Vai trò |
|---|---|
| `measurements/blind_time.py` | C12 (thuần) + `test_phase8_blind_time.py` (8 test) |
| `scripts/phase8_infra_health.py` | cổng sức khoẻ Ditto/Mongo |
| `scripts/run_phase8_stability.py` | C6 ba chế độ + C7 + hồi quy S11 (Loại I/II) |
| `scripts/run_phase8_chaos.py` | 6 dòng: control · c9 · drift · second_flood · restart · agent_kill |

---

# KẾT QUẢ (viết SAU khi đo; dự đoán khoá ở commit `f8d8266`)

## 8. C6 — ổn định

### flood liên tục 600 s (`phase8_stability_flood.json`)

| | |
|---|---|
| số hành động | **14** (cận sim: 13) |
| số inject | 7 |
| **`min_hold_s`** | **16,0 s** ≥ `T₀` = 15 |
| vi phạm `T₀` | **không có** |
| hold quan sát | 16 · 30 · 61 · 111 · 110 · 110 · 92 s |
| gap (revert → inject kế) | **11 s × 6, đều tăm tắp** |
| C12-a / C12-b / C12-c | 96,3% / 96,3% / **119 s** |

**C6-a: FAIL theo chữ (14 > 13), PASS theo bản chất.** Đây **đúng** trường hợp đã
khoá trước: *"nếu `n_actions` > 13 thì phân biệt bằng `min_hold_s`"*. Mọi hold ≥
`T₀`, backoff leo đúng 15 → 30 → 60 → 110 (bão hoà), gap **hằng định 11 s** —
không có dấu hiệu dao động nào.

> **⚠️ ĐÍNH CHÍNH 8.8 — nguyên nhân thật của "14 vs 13", và nó khác cái viết
> dưới đây.** Giải thích gốc (*"một inject thừa vì gap thật 11 s ngắn hơn giả
> định ~13 s của sim"*) **sai**: sim dùng trễ chết 11,433 s, gần như đúng bằng
> gap đo được 11,0 s, nên nó không thể lọt thêm một chu kỳ vì lý do đó.
>
> Nguyên nhân đúng, tính được bằng số học từ chính bảng trên: cộng dồn
> `holds + gaps` cho thấy hold thứ 7 bắt đầu ở 504 s và lẽ ra kết thúc ở
> 504 + 110 = **614 s, NGOÀI chân trời 600 s**. Nó kết thúc ở 596,4 s vì run
> hết giờ và `ControlRunner.shutdown()` **gỡ can thiệp đang mở**. Hành động thứ
> 14 là **revert của tắt êm**, không phải một inject thừa: `n_inject = 7`,
> `n_revert = 7`.
>
> Cận đúng là **13 + 1 = 14**, và cái sai là **sim** (nó cắt ngang can thiệp
> đang mở mà không gỡ; một hệ thật bắt buộc phải gỡ). Sim đã được vá và
> known-answer test ra **đúng 14**. Verdict: **PASS-with-model-correction**.
> Xem `08-acceptance.md §0.1`.

> Nếu chỉ báo "14 > 13 ⇒ FAIL" thì mất thông tin; nếu chỉ báo "không dao động"
> thì giấu số. Báo cả hai mới đúng.

### bình thường 600 s (`phase8_stability_quiet.json`)

```
n_actions = 0        C12-a = 0,000        S11 Loại I = 0
```

**C6-b PASS**, khớp sim tuyệt đối.

## 9. Hồi quy S11 — và vì sao gate "fail" rồi "pass"

Theo **đúng chữ** của luật đã khoá: **Loại I = 7** → **gate FAIL**. Tôi không đổi
tiêu chí; tôi điều tra, đúng như điều cấm đã viết.

Dữ liệu: **7/7 tick Loại I nằm đúng `+1,00 s` sau mỗi inject**, một tick cho mỗi
inject, không bao giờ hai. Trong cùng run có **554 tick** `suppressed_intervention`
— ức chế hoạt động bình thường.

**Cơ chế:** controller nhìn trạng thái detector **chậm hơn một nhịp** (trễ xác
nhận đủ đường đo ở 8.4: p50 667 ms, p95 1003 ms, cộng chu kỳ control 1 s). View
đọc tại `t_inject + 1 s` đã được detector **công bố trước khi** can thiệp được ghi
vào log — đó là **view cũ**, không phải ức chế thất bại.

Tính lại với các mức trừ trễ hiển thị:

| lag | Loại I |
|---|---|
| 0,0 s (chữ của luật) | **7** |
| 1,5 s | **0** |
| 2,0 s | **0** |

Harness nay **báo cả hai** (`s11_type_i` và `s11_type_i_after_view_lag`,
`VIEW_LAG_S = 2,0 s`, cơ sở là phép đo 8.4). Đây là **tinh chỉnh phép đo**, không
phải đổi tiêu chí — và cả hai số đều nằm trong receipt.

### 9.1 Thay "trừ trễ" bằng một vị từ — sửa ở 8.8

Cách xử lý trên đúng về bản chất, nhưng cách **phát biểu** ("trừ 1,5–2,0 s")
trông giống nới định nghĩa, và bất kỳ hằng số nào cũng mời câu hỏi *"vì sao 1,5
mà không phải 2,5?"*. Dữ liệu ở đây mạnh hơn cách nó đang được dùng: **đúng một
tick biên cho mỗi can thiệp** không phải nhiễu — đó là **một cơ chế**, và cơ chế
đó có tên.

**Cửa sổ đua của write-ahead.** Cuộc đua thật không phải *log vs lệnh* (M5 đã
xử lý) mà là *log vs snapshot ĐÃ ĐANG BAY*: collector lấy mẫu tại `t_source`,
FSM chấm nó vài trăm ms sau. Nếu can thiệp được ghi vào **giữa hai mốc đó**,
snapshot ấy bị chấm dựa trên một sổ can thiệp **chưa tồn tại lúc nó được lấy
mẫu**.

`InterventionLog.active(source_time)` **đã** so với `t_source`, đúng như phải
thế. Nên hệ **không sai** — chỉ có **quy tắc quy kết** đang đếm tick theo đồng
hồ tường. Thay bằng đúng vị từ mà FSM dùng, **không có hằng số nào**:

```python
# measurements/attribution.py
def in_intervention_window(t_source, t_start, t_revert, cooldown_s=8.0):
    end = (t_revert + cooldown_s) if t_revert is not None else t_start + 120.0
    return t_start <= t_source < end
```

Một tick có `t_source < t_start` là **nhân quả đi trước**: nó không thể do can
thiệp gây ra, nên nó không phải bằng chứng cho "ức chế lẽ ra phải bật mà không
bật". Ba rổ: `type_i` (GATE), `type_ii` (có entity ngoài vùng), `unattributed`
(ghi kèm `t_source − t_start` để người đọc tự kiểm).

Lợi ích so với "trừ 1,5–2,0 s": không hằng số tuỳ ý; **cùng đồng hồ, cùng vị từ**
với cơ chế đang được kiểm; và tự chứng minh được từ receipt.

⚠️ **Run 8.7 không lưu `t_source` nên KHÔNG quy kết lại được.** Không trừ một
hằng số để nó biến mất. `scripts/run_phase8_stability.py` nay dump
`DetectorRunner.timeline` và join theo `(bootId, seq)`; verdict chính thức
(**C8-r**) đến từ các run của 8.8. Xem `08-acceptance.md §0.3`.

## 10. Chaos (`phase8_chaos_v6.json`, `66d8b067…`) — 6 dòng × 2 lượt, 0 lượt vô hiệu

| Dòng | rep0 | rep1 | Đọc |
|---|---|---|---|
| **control** (đối chứng) | MITIGATING, 0 exception, bw 7 | idem | nhánh không bị phá vẫn khoẻ |
| **c9 / c9-b** | phục hồi vật lý **10,73 s**; cảm biến **115,74 s**; **mù thừa 105,01 s** | 12,33 / 117,34 / **105,01** | ≤ 17 s như dự đoán; mù thừa ≈ **105 s** (dự đoán ~103 s) |
| **drift** (ngoài luồng) | kéo về 7 trong **1,89 s**, `drift_fixes += 1` | **1,28 s**, +1 | ≤ 3 s như dự đoán — **nợ 8.4 đã trả** |
| **second_flood** | bị che **25,16 s** (lúc đó PROBING) | **1,74 s** (lúc đó MITIGATING) | **dự đoán SAI** — xem §11 |
| **restart** | orphan 1, revert-first **0,44 s**, **0 exception** | 1, **0,89 s**, 0 | fencing token 8.6 xác nhận live |
| **agent_kill** | lease bị xoá, `commands_since = 3` | idem | tự lành bằng **reconcile**, không bằng watchdog |

## 11. Ba dự đoán sai — và cả ba đều cùng một cơ chế

**(a) `second_flood` KHÔNG bị che tới ~118 s.** Dự đoán: toàn bộ đường h2→srv2 nằm
trong vùng ức chế nên bị che tới khi episode h1 đóng. Đo được: **1,74 s** (khi
đang MITIGATING) và **25,16 s** (khi đang PROBING).

**(b) Gap chỉ 11 s** thay vì ~13 s, và ở 8.6 addendum là 1–5 s.

**(c) `excess_blind_window` ban đầu đo ra 0** rồi mới ra 105 s sau khi sửa phép đo.

Cả ba đều do **cùng một cơ chế**: `link-s2-s3` — nút cổ chai 5 Mbps — là entity
**duy nhất ngoài vùng ức chế 15/16**, và dưới flood nó gần như luôn vi phạm. Điều
kiện `local <= zone` của `ml/fsm.py` **không thoả** ⇒ ức chế **không áp dụng** ⇒
detector vẫn công bố `act`.

Hệ quả kép, phải nói cả hai:

- **Lợi:** hệ **ít mù hơn** thiết kế dự định — sự cố thứ hai vẫn được phát hiện
  trong vài giây, và vòng kín tái bảo vệ nhanh hơn mô hình.
- **Hại:** bảo đảm S11 **yếu hơn** thiết kế — chính vì thế mới có 7 tick Loại I
  cần điều tra, và chính vì thế 8.3 đã đo được 1/3 round không bị ức chế.

> **Ức chế kiểu toàn-hoặc-không là bảo thủ theo hướng sai:** nó tắt ức chế hoàn
> toàn chỉ vì **một** entity ngoài vùng. Thiết kế thay thế là ức chế **theo từng
> entity** (bỏ qua entity trong vùng, vẫn đánh giá entity ngoài vùng). Thay đổi
> này chạm vào detector đã đóng băng nên **ngoài phạm vi Phase 8**, ghi làm công
> việc tiếp theo.

## 12. Bốn lỗi thật tìm được khi chạy chaos

1. **`bootstrap_safe_state` không lũy đẳng.** Harness gọi một lần, `run_forever`
   gọi lại → hai lần sinh cùng id orphan revert → `ValueError` → **luồng control
   chết ngay khi khởi động** → mọi lượt sau abort với "không vào được MITIGATING".
   Sửa: cờ `_bootstrapped` + id orphan có chỉ số.
2. **Bản ghi vô chủ làm kẹt `stale_intervention` vĩnh viễn.** Revert-first sửa
   **bw** nhưng **không đóng sổ sách**: một inject chưa đóng khiến `stale_open()`
   luôn trả nó, `cause` kẹt ở `stale_intervention`, và theo **N15** mọi controller
   sau đó **từ chối hành động** — trong khi mạng đang bị flood thật (h1 20 Mbps,
   h3 0,012 Mbps). Sửa: `_close_orphan_interventions()` ghi `revert` cho mọi
   inject chưa đóng của **lần chạy trước** (undo kiểu crash recovery).
3. **cid trùng trong `cleanup` của harness** → dedup của agent trả kết quả cũ
   **không chạm Mininet** → link kẹt ở 7 Mbps → mọi lượt sau abort. Lỗi của
   harness, và đồng thời là minh chứng dedup chạy đúng thiết kế.
4. **Cổng sức khoẻ hạ tầng quá nghiêm.** Mongo ở 90,2% trần bị coi là "không
   khoẻ" trong khi Ditto trả 200 trong 5 ms. Chữ ký hỏng thật ở 8.6 là **latency
   55 s + HTTP 503**. Sửa: bộ nhớ là **cảnh báo sớm**, điều kiện vô hiệu là
   status/latency.

## 13. Còn nợ sang 8.8 (khai rõ, không giấu)

| Việc | Vì sao chưa làm | Ước lượng |
|---|---|---|
| C6-c Poisson 1800 s × N (cùng seed với sim) | ~1,5–3 h liên tục; phiên này đã chạm trần hạ tầng hai lần | 3 lượt ≈ 1,5 h |
| C11 soak 30 phút + xoay vòng audit + đếm luồng | cần phiên **liên tục**, không restart Ditto | ≈ 45 phút |
| `degraded_tick_fraction` + lưu tick thô | cần chạy cùng soak | gộp vào trên |
| C9-a (UI STALE ≤ 5 s) | đã có kịch bản E2E ở 8.5, cần chạy lại kèm controller thật | ≈ 10 phút |

Ba con số C12 **đã có** từ chế độ flood: **96,3% / 96,3% / 119 s**.

> **⚠️ Cách phát biểu (8.8).** Ở run này C12-a = C12-b không phải vì chúng đo
> cùng một thứ, mà vì **toàn bộ run là một sự cố** (`incident_s = 600,0`,
> `window_s = 600,4`) — hai mẫu số bằng nhau. Ở chế độ quiet, C12-a = 0. Hai
> chế độ cực đoan, không con số nào phản ánh vận hành thật:
>
> ```
> C12-b (tỷ lệ mù TRONG LÚC có sự cố)          = 96,3%   ← đo được, chắc chắn
> C12-c (cửa sổ mù liên tục dài nhất)          = 119 s   ← đo được, chắc chắn
> C12-a (tỷ lệ mù trên TỔNG thời gian vận hành) = phụ thuộc chu kỳ làm việc
>        flood liên tục 600 s → 96,3%  (cận trên)
>        bình thường 600 s    →  0,0%  (cận dưới)
>        tải Poisson 1800 s   → đo ở 8.8   ← con số duy nhất có nghĩa
> ```
>
> **Không được trích "96,3% thời gian hệ bị mù" như một tuyên bố toàn cục.**
