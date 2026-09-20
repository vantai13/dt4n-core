# Phase 8.1 — Preregistration: chọn đúng bài toán điều khiển

Niêm phong: `results/report/phase8_prereg.json`
`content_sha256 = cd7d168c168f7afbe0a7e2fbab28fdb10b163acdfbfb3b2565c47802e22f70c4`
Nhánh: `phase/8-closed-loop`, nền: `2c4711a` (tag `phase-7-complete`).
Detector: `detector-release-1.0.0`, đóng băng, không train lại gì ở Lesson 8.1.

Tài liệu này là bản đọc được của prereg. Khi hai bản lệch nhau, **file JSON đã
niêm phong là bản đúng**.

---

## 1. Bài toán được đổi tên

| | Plan cũ | Thực tế đã kiểm chứng |
|---|---|---|
| Tên | Closed-loop **failover** | Closed-loop **mitigation** |
| Cơ chế | chuyển đường bằng `disableLink` | **rate limiting** bằng `setBandwidth` |
| Ai làm failover? | twin | **Ryu**, ở tầng dữ liệu, đã có sẵn |

Bằng chứng vòng trong đã tự failover: `mininet/controller_static.py:359-365`
thêm cạnh vào `down_edges` rồi `mininet/controller_static.py:222` gọi
`next_hop_table(spec, excluded_edges=self.down_edges)` và cài lại flow. Đó là
**cascade control**: vòng trong (Ryu, mili-giây) xử lý *sự kiện hạ tầng*, vòng
ngoài (twin, giây) xử lý *chính sách*.

Hệ quả bắt buộc cho PART V của master plan: chỉ số
`"phát hiện → traffic chuyển hướng < 10 s"` đổi thành
`"phát hiện → giảm thiểu có hiệu lực < 10 s"` (= C3), **kèm lý do trên**. Đổi
tên mà không ghi lý do là nới định nghĩa.

## 2. Khả điều khiển — vì sao là `setBandwidth`

| Actuator | Tác động vật lý | Cải thiện nạn nhân? | Bằng chứng |
|---|---|---|---|
| `disableLink s1-s2` | Ryu reroute qua `s1-s3-s2` | ❌ tệ hơn | đường vòng xuyên bottleneck 5 Mbps — `mininet/topology.py:72` |
| `disableLink s2-srv1` | cô lập srv1 | ❌ giết dịch vụ | `ditto/topology_spec.json`: srv1 chỉ có cạnh `["srv1","s2"]`; không có LB/DNS/NAT đổi đích 10.0.0.4 → 10.0.0.5 |
| `disableSwitch s1` | tắt switch gốc | ❌ cả 3 client chết | h1,h2,h3 đều treo vào s1 |
| `disableHost h1` | tắt hẳn thủ phạm | ✅ nhưng phá huỷ | h1 còn traffic hợp lệ; không đảo ngược êm |
| `enableLink`/`enableSwitch`/`enableHost` | khôi phục | — | chỉ là đường lui |
| **`setBandwidth h1-s1 bw=L`** | **policing ở cổng vào** | ✅ **và đảo ngược được** | `bridge/command_agent.py:317` trong whitelist; ghi `dt4n_bw` ở `:258`, twin đọc lại ở `bridge/collector.py:403` |

**L = 7 Mbps.** Owner: `N-vary-s1007-r1`, tick 16, host `h3`, 6.181986 Mbps —
trần tải hợp lệ cao nhất trên **đủ 8 run train**, làm tròn lên. Nghĩa là mức
giới hạn không bao giờ cắt vào một mức tải mà hệ đã từng coi là bình thường.

Tác dụng phụ **phải khai**: flood là UDP (`rl/scenarios.py::TrafficFlood`,
`iperf -u`), không lùi bước; bóp `h1-s1` xuống 7 Mbps làm hàng đợi ở đó đầy,
`lossPct`/`qdiscDropDelta` của `link-h1-s1` tăng, và traffic hợp lệ 2 Mbps của
chính h1 cũng bị chèn. Đây là ngữ nghĩa chuẩn của ingress policing; S11 phải đo
lại cho actuator mới ở Lesson 8.3 (C8).

## 3. Luật định vị v2 — không tham số tự do

`controller/localize.py` (`sha256 = 9dba6b29ee25…`), hàm thuần, không I/O.

```
candidates = { host ∈ evidence.affected | attributes.role == "client" }
|candidates| == 0  -> NO_ACTION(no_client_candidate)
|candidates| == 1  -> TARGET = candidate đó
|candidates| >= 2  -> NO_ACTION(ambiguous_multiple_clients)   # fail-closed
LATCH: chốt TARGET tại tick act đầu tiên, không đánh giá lại tới hết episode.
```

Điều kiện tiên quyết (do FSM controller bảo đảm): `decision.state == "act"`
(R1, N10) · freshness còn hạn (R3, N12) · `cause ∉ {stale_intervention,
out_of_operating_range}` (N15, N16) · controller đang IDLE.

Ánh xạ hợp đồng Phase 7 → thiết kế (bản đầy đủ trong `prohibitions` của prereg):
R1/N10 = cổng `act` trên state **đã công bố**; R2 = dùng `evidence.affected` của
chính tick đó (không phải `decision.affected`, vốn có quán tính hysteresis);
R3/N12 = freshness; R4 = ghi `releaseVersion`/`releaseSha256` vào audit; N13 =
không tính lại gì của detector (luật v2 chỉ đọc `attributes.role`); N15/N16 =
hai `cause` chặn hành động. **N11** có bằng chứng số: trên
`F-flood-h1_to_srv1-s3005-r1`, **8/28** tick act có `evidence.actRule = false`
(`RC-flood-h1`: 7/26) — `actRule` không có quán tính nên không được dùng làm
trigger.

**Vì sao LATCH là bắt buộc** — recovery burst, đo trên
`F-flood-h1_to_srv1-s3005-r1` (`results/report/phase8_localization_probe.json`):

| tick | state | h1 | h2 | h3 (Mbps) | client trong `affected` | mục tiêu nếu đánh giá **mỗi tick** |
|---|---|---|---|---|---|---|
| 22 | act | 20.00 | 2.15 | 2.15 | h1 | h1 ✅ |
| 29 | act | 19.99 | 2.16 | 0.02 | h1 | h1 ✅ |
| 40 | act | 20.00 | 2.17 | 0.00 | h1 | h1 ✅ (flood tắt tại đây) |
| 45 | act | 2.14 | 2.16 | **14.39** | h3 | **h3 ❌ (nạn nhân!)** |
| 46 | act | 2.15 | 2.17 | **18.43** | h3 | **h3 ❌** |
| 48 | act | 2.14 | 2.15 | 2.16 | — | — |

Tại **mọi** tick, `affected` chứa h1 **hoặc** h3, **không bao giờ cả hai** —
khác với mô tả của F8-5 trong `PHASE_8.md`, vốn là **hợp của cả episode**. Hai
run bị ảnh hưởng nếu bỏ latch: `F-flood-h1_to_srv1-s3005-r1` và
`RC-flood-h1_to_srv1-s4201-r1`.

## 4. Δ-gap: phần mở rộng **chưa kích hoạt**

```
Δ = 5.36595616 Mbps
owner = { run_id: "N-vary-s1008-r2", tick: 26, host: "h2",
          top: 5.366516, second: 0.000560 }
quyết định: GIỮ đủ 8 run train, KHÔNG loại s1008
lý do   : loại s1008 -> Δ = 3.245677 -> luật gap bắn nhầm ở C-vary-s2002-r1
          (run hoàn toàn bình thường)
```

Và ngay cả với Δ đủ 8 run, luật gap **một mình** vẫn chỉ mặt sai ở 8 run không
flood: `F-shift-s1-s2`, `F-shift-s1-s3`, `RC-shift-s1-s2`,
`RD-degrade-s1-s2-rho{125,150,200}`, `RN-load10M-s4015/s4016`. Đó là lý do luật
v2 không dùng Δ. Δ được ghi lại ở đây để không ai tính lại nó sau khi đã nhìn
test; nếu `|candidates| >= 2` xảy ra thật trong live thì phải **đo lại** trước
khi bật nhánh này.

## 5. Kết quả probe offline — KN1

43 run được phát lại qua đúng đường runtime Phase 7
(`scorer.observe → fsm.step → OperatingRangeGuard.update → build_document`),
gồm 18 run Phase 5 và 25 run Phase 6R (dữ liệu có sẵn trên đĩa, không phải LFS
pointer).

| | |
|---|---|
| flood → đúng thủ phạm | **4/4** (`F-flood-h1`, `F-flood-h2`, `RC-flood-h1`, `RC-flood-h2`) |
| không-flood → không hành động | **39/39** |
| chỉ mặt sai | 0 |
| bỏ sót | 0 |

→ **KN1** trên dữ liệu đã mở. *Caveat:* offline, in-sample, n_flood = 4. C1 thật
đến từ A/B live ở 8.6 (n ≥ 10).

**Hai lớp phòng thủ đã được đo, không phải hứa:**

1. **N16 / guard vùng vận hành.** Bốn run tải cao `RN-load8M-*`, `RN-load10M-*`
   có **232 tick act ở FSM thô**, nhưng guard (T = 4.312610 Mbps, prereg Phase 7)
   bật 59/59 tick nên state công bố **không có tick act nào**. Nếu không có
   guard, `affected` ở đó chứa **cả ba client**.
2. **Fail-closed của luật v2.** Kể cả khi guard không bật, ba ứng viên →
   `ambiguous_multiple_clients` → không hành động.

`shift` và `admin_down` vào `act` nhưng `affected` **không chứa client nào** →
C2 được thoả mãn bằng dữ liệu (0/39), không phải bằng lời hứa.

## 6. Vùng mù (observability)

- **Vùng ức chế:** can thiệp lên `link-h1-s1` có blast radius **15/16 entity**
  của model; entity duy nhất còn nhìn thấy là `link-s2-s3`. Mỗi giây đang giảm
  thiểu là một giây detector gần như mù. Đây là C12 (REPORT_ONLY, đo ở 8.7).
- **Reset bộ đếm:** `h_set_bandwidth` gọi `ln.intf1.config(...)` và `ln.intf2.config(...)` (`bridge/command_agent.py:256-258`) → dựng lại
  qdisc → 1 tick `rateValid=false` → `unknown(missing_data)` **dự đoán được**.
- **Trễ trung bình hoá:** `rxRate`/`txRate` trung bình 1 giây → trễ ~1–2 s.

## 7. Bảng SLO C1–C12 (niêm phong)

| ID | Đo | Mục tiêu | Gate | Đo ở |
|---|---|---|---|---|
| C1 | hành động đúng nguồn | 100% (n ≥ 10 live) | ✅ | 8.6 |
| C2 | không hành động với admin_down/shift/degrade | 0 | ✅ | 8.1 offline + 8.7 |
| C3 | trễ act → thủ phạm bị giới hạn (p95) | ≤ 10 000 ms | ✅ | 8.6 |
| C4 | nạn nhân hồi phục ≥ 80% nền (p95) | ≤ 15 s | báo cáo | 8.6 |
| C5 | A/B goodput nạn nhân | CI95 > 0 | ✅ | 8.6 |
| C6 | số hành động / 10 phút | ≤ cận sim; 0 lúc bình thường | ✅ | 8.7 |
| C7 | hành động trên trigger bị cấm | 0 | ✅ | 8.2 + 8.7 |
| C8 | S11 cho `setBandwidth` | 0 | ✅ | 8.3 |
| C9 | controller chết → UI STALE / giới hạn tự gỡ | ≤ 5 s / ≤ TTL | ✅ | 8.7 |
| C10 | dựng lại bit-exact từ audit | 100% | ✅ | 8.8 |
| C11 | ổn định 30 phút | ≤ 1 MiB RSS; 0 ERROR | ✅ | 8.7 |
| C12 | tỷ lệ thời gian mù | báo cáo | REPORT_ONLY | 8.7 |

## 8. Giới hạn đã khai TRƯỚC

1. `degrade` trên `s1-s2` **không bao giờ** vào act: 0 tick trên
   `F-degrade-s1-s2-s3003-r1` và cả 5 run `RD-degrade-s1-s2-*`. Controller tuân
   thủ hợp đồng **sẽ không bao giờ** phản ứng với loại sự cố này. Đây là giới
   hạn S1 = 0.30 hiện ra ở tầng hành động, không phải lỗi controller. Khai trước
   để không ai "sửa" controller cho phản ứng với `suspect` (vi phạm N10).
2. Nạn nhân bị bỏ đói **không** được phát hiện: h3 tụt 2.15 → 0.00 Mbps mà không
   vào `affected`. Hệ thấy thủ phạm, không thấy hậu quả.
3. Vùng ức chế 15/16 entity mỗi khoảng giảm thiểu.
4. Rate limit ở link truy nhập cũng bóp traffic hợp lệ của chính thủ phạm (UDP).
5. n = 4 run flood trong dữ liệu đã mở. Mỏng.
6. Luật v2 im lặng khi có ≥ 2 ứng viên — chủ đích, nhưng là giới hạn.

## 9. Sai lệch quy trình (khai báo trung thực)

`protocol_deviation.occurred = true`: hai probe đã chạy **trước** khi seal file
này, và kết quả trên R-set Phase 6R đã được đọc trước khi ghi KN. Không thể
tuyên bố blind prereg. Bù lại: luật **không có tham số tự do nào** để chỉnh sau
khi nhìn số, và mọi con số lấy từ train đều đi qua tường lửa train-only
(`ml/operating_range.py::_assert_train_path`, từ chối đường dẫn ngoài
`data/phase5/raw` và từ chối nếu không đủ đúng 8 run train).

## 10. Receipt

| File | Nội dung |
|---|---|
| `results/report/phase8_actionability.json` | ma trận act theo loại lỗi, 43 run, latch vs per-tick |
| `results/report/phase8_localization_probe.json` | ma trận nhầm lẫn, Δ + L có owner, so sánh luật gap, vùng ức chế, bảng recovery burst |
| `results/report/phase8_prereg.json` | bản niêm phong (`cd7d168c…`), immutable |
| `test/test_phase8_localize.py` | 44 test: liệt kê 2⁵ tổ hợp + firewall "không I/O" + bất biến với receipt |

Quy tắc cứng: **không viết dòng nào trong `controller/runner.py`** cho tới khi
prereg này đã có SHA và đã push.
