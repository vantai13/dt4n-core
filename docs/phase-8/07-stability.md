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
