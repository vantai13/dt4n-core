# Phase 8.2 — Thiết kế luật thời gian: vì sao vòng dao động và cách chặn

Nhánh `phase/8-closed-loop`. Không đụng Mininet ở lesson này: mọi con số dưới
đây sinh ra từ receipt Phase 7 + mô phỏng sự kiện rời rạc, và **niêm phong
trước** mọi phép đo live (`results/report/phase8_sim_predictions.json`).

---

## 1. Trễ chết (dead time) của vòng — đo, không đoán

| Chặng | Receipt | p50 | p95 |
|---|---|---|---|
| lệnh → `tc` hiệu lực → snapshot thấy (`phys_obs`) | `phase7_e2e_latency.json` | 1158.6 ms | **1432.6 ms** |
| detector chấm điểm (`detect`) | nt | 1.41 ms | 1.68 ms |
| PATCH Ditto (`write_2xx`) | nt | 8.57 ms | 11.17 ms |
| Ditto → consumer (`fanout_sse`) | nt | 8.46 ms | 11.03 ms |
| lệnh vòng kín đầu–cuối | `latency_command_randomized.json` | 674.7 ms | **984.2 ms** |
| `n_act` = 2 tick, `release_m` = 3 tick, `cooldown_s` = 8.0 s | `detector-release-1.0.0.json` → `fsm_params` | | |
| lease `MAX_OPEN_S` | `ml/intervention_log.py:9` | 120.0 s | |

**Trễ chết của nhánh "phát hiện lại" sau khi gỡ giới hạn:**

```
cooldown_s                 8.000 s   (ức chế còn hiệu lực sau revert,
                                      ml/intervention_log.py:80)
+ phys_obs p95             1.433 s
+ n_act × tick             2.000 s
────────────────────────────────────
= 11.433 s   = controller.policy.DEAD_TIME_S
```

Mọi hằng số thời gian của Lesson 8.2 đều phải tôn trọng con số này. Một
controller quyết định nhanh hơn 11.4 s là đang **đoán**, không phải **đo**.

8 giây trong đó là **do chính controller tự gây ra**: `InterventionLog.active()`
giữ khoảng can thiệp sống thêm `cooldown_s` **sau** revert
(`ml/intervention_log.py:80`, `end = closed_at + cooldown_s`).

## 2. Bang-bang + trễ chết ⇒ limit cycle (đo bằng chính mô hình này)

Đối chứng `controller/sim.py::run_bangbang` hiện thực đúng luật của master plan
("bật khi `act`, tắt khi detector báo khỏe"), flood liên tục 600 s:

| | Bang-bang | Circuit breaker (8.2) |
|---|---|---|
| số hành động / 10 phút | **92** | **13** |
| số lần giảm thiểu | 46 | 7 |
| chu kỳ dao động | **13.0 s** | — (không có chu kỳ cố định) |
| thời gian gây hại (flood lọt) | **69.3%** | **9.7%** |
| thời gian mù | 84.3% | 97.3% |
| khoảng giữ dài nhất | 4.0 s | 110.0 s |

Bang-bang làm việc **gấp 7 lần** để bảo vệ được **1/7 thời gian**.

**Gốc rễ, một câu:** quyết định "gỡ" dựa trên sự khỏe mạnh **do chính controller
tạo ra**. Sensor không phân biệt được hai trạng thái hoàn toàn khác nhau:

| Trạng thái thật | Detector thấy |
|---|---|
| flood đã ngừng, mạng khỏe thật | `normal` |
| flood vẫn chạy, đang bị chặn | `normal` |

Không trường nào trong `org.dt4n:detector` phân biệt được. Đây là **giới hạn khả
quan sát**, không phải lỗi code.

## 3. Vì sao hysteresis + cooldown **chưa đủ**

Bạn **đã có** hysteresis từ Phase 6: `ml/fsm.py` ép `release_m (3) > n_act (2)`,
và `raise ValueError("release_m phai > n_act de chong dao dong X->Y->X")`. Bạn
cũng đã có cooldown 8 s. Vòng vẫn dao động, vì **hysteresis chữa sai bệnh**:

| | Hysteresis chữa được | Bệnh của vòng này |
|---|---|---|
| nguyên nhân | nhiễu **đo** quanh ngưỡng | tác động làm **đổi phép đo** |
| nhiễu kéo dài? | không (transient) | có (flood 10 phút) |
| hiệu quả | cắt hẳn chattering | **chỉ kéo dài chu kỳ** |

Đo bằng mô hình (bang-bang, flood liên tục 600 s):

| `release_m` | hành động | chu kỳ | gây hại |
|---|---|---|---|
| 3 (giá trị thật) | 92 | 13.0 s | 69.3% |
| 5 | 80 | 15.0 s | 60.0% |
| 10 | 60 | 20.0 s | 45.0% |
| 20 | 40 | 30.0 s | 30.0% |

Tăng `release_m` gần 7 lần vẫn còn **40 hành động / 10 phút và 30% gây hại**.
Và bạn **không được** sửa `release_m`: nó nằm trong `detector-release-1.0.0` đã
đóng băng — sửa là phá các hàng S của Phase 7.

> Câu hỏi hội đồng sẽ hỏi: *"Chu kỳ dao động của em bây giờ là bao nhiêu giây?"*
> Nếu chỉ trả lời "em đã thêm hysteresis" thì chưa chữa gì cả.

## 4. Cách chữa: circuit breaker + exponential backoff

Vì sensor **không thể** phân biệt "flood hết" với "flood đang bị chặn", thì
**đừng hỏi sensor câu đó nữa**: gỡ **theo lịch**, và coi mỗi lần gỡ là một **thí
nghiệm** (probe).

| Nygard, *Release It!* | Ở đây | Ý nghĩa |
|---|---|---|
| closed | `IDLE` | bình thường, không can thiệp |
| open | `MITIGATING` | đang giới hạn, **không hỏi sensor về việc gỡ** |
| half-open | `PROBING` | đã gỡ, đang quan sát thử trong cửa sổ W |

Ba nguyên tắc:
1. **Không bao giờ gỡ vì "trông có vẻ khỏe".** Sự khỏe mạnh quan sát trong lúc
   can thiệp là bằng chứng vô giá trị.
2. **Mỗi lần gỡ là một probe** — trong cửa sổ W không có can thiệp mở nên sensor
   lại đáng tin.
3. Cái đọc được trong `MITIGATING` chỉ xác nhận **lệnh đã có hiệu lực**, không
   phải "mạng đã khỏe".

Backoff: `T_k = min(T₀ · 2^k, T_max)` → **15 → 30 → 60 → 110 → 110 …**

## 5. Ba hằng số, mỗi cái truy về một phép đo

| Hằng số | Giá trị | Suy ra từ |
|---|---|---|
| `T₀` | 15 s | > trễ chết 11.433 s, cộng biên ~3 s; đủ dài để một probe có nghĩa |
| `T_max` | **110 s** | `MAX_OPEN_S = 120` − biên 5 s (lệnh p95 0.984 s + ghi log). Test `test_tmax_nho_hon_lease` đọc thẳng `ml.intervention_log.MAX_OPEN_S` |
| `W` | **14 s** | ≥ `DEAD_TIME_S` 11.433 s + biên; `PolicyParams.__post_init__` **từ chối** W < 11.433 |

Vượt lease 120 s → `stale_intervention` từ chính can thiệp của mình → theo **N15**
controller phải gỡ, và nếu code sai thì tự tạo vòng phản hồi dương chu kỳ 120 s.
Phase 7 đã đo cơ chế lease này.

### Đường cong đánh đổi (flood liên tục 600 s)

| `T_max` | hành động | gây hại | mù |
|---|---|---|---|
| 30 s | 31 | 23.2% | 94.3% |
| 60 s | 19 | 14.2% | 96.3% |
| **110 s** | **13** | **9.7%** | **97.3%** |

Không có lựa chọn tốt hơn về mọi mặt: **T lớn → ít dao động, ít gây hại, mù lâu
hơn; T nhỏ → nhìn thấy nhiều hơn, gây hại và dao động nhiều hơn.** Chọn 110 s vì
C12 là `gate: false` (báo cáo) còn C5/C6 là gate.

**Hai phát hiện của mô phỏng mà bản thiết kế chưa lường:**

1. **Dưới flood liên tục, `W` không ảnh hưởng gì** tới số hành động (13 với mọi
   W ∈ {12,14,20,30}), vì `act` quay lại sau ~9 s — **trước** khi hết cửa sổ.
   `W` chỉ lộ tác dụng khi flood **đã tắt thật**: nó chính là độ trễ gỡ giới hạn
   sau khi sự cố kết thúc (flood tắt ở t=130 → về IDLE ở t=148/150/156/166 ứng
   với W=12/14/20/30). Vậy **W là tham số của C4 (thời gian hồi phục), không
   phải của C6.**
2. **`T₀` 15 s và 30 s cho kết quả y hệt** dưới flood liên tục: lịch bị `T_max`
   chi phối sau 3 lần backoff. `T₀` chỉ quan trọng với các sự cố ngắn.

## 6. Tách thang thời gian (cascade control)

```
VÒNG TRONG — Ryu: port up/down → next_hop_table(excluded_edges)   ~10 ms
VÒNG NGOÀI — twin: detector act → setBandwidth                    ≥ 15 s
tỷ lệ ≈ 1500× → an toàn (kinh nghiệm: vòng ngoài chậm hơn ≥ 5–10×)
```

Hệ quả **bắt buộc**: controller Phase 8 **không bao giờ** phát `disableLink` /
`enableLink` / `disableSwitch` / `enableSwitch` / `disableHost`. Đây là **kiểm
tra tĩnh**, không phải lời hứa: `test_policy_khong_cham_actuator_topology`.

## 7. FSM controller — bảng chuyển đầy đủ

`k` = số probe thất bại liên tiếp. `T_k = min(T₀·2^k, T_max)`.

### 7.1 Phân loại đầu vào (`classify`, thứ tự có ý nghĩa)

| Nhãn | Điều kiện | Điều cấm |
|---|---|---|
| `STALE` | `not fresh` (MonotonicFreshness) | **N12**, R3 |
| `STALE_INTERVENTION` | `cause == "stale_intervention"` | **N15** |
| `OUT_OF_RANGE` | `cause == "out_of_operating_range"` | **N16** |
| `WARMING` | `state == "warming_up"` | S9 |
| `SUPPRESSED` | `unknown` + `suppressed_intervention` | — |
| `UNKNOWN` | `unknown` + cause khác | — |
| `ACT` | `state == "act"` và không rơi vào nhãn trên | R1 |
| `QUIET` | `normal` **và** `suspect` | **N10** |

Freshness kiểm **trước** state: một bản tin `act` đã hết TTL vẫn là bản tin chết.
`suspect` **không có nhãn riêng** → không có đường nào trong bảng dẫn từ `suspect`
tới hành động → N10 không thể quên. (8.1 đã cho bằng chứng số: `C-vary-s2002-r1`
có 4 tick luật gap sẽ bắn nhưng **0** tick `act`; và guard N16 nuốt 232 tick act
thô của `RN-load8M/10M`.)

### 7.2 Bảng chuyển

| Trạng thái | Nhãn | Điều kiện | Hành động | Kế tiếp |
|---|---|---|---|---|
| IDLE | `ACT` | `localize()` → target | **inject** `setBandwidth(target-s1, 7)` | MITIGATING(k=0, deadline=now+T₀) |
| IDLE | `ACT` | `localize()` → None | — (ghi audit lý do) | IDLE |
| IDLE | mọi nhãn khác trừ `STALE` | | — | IDLE |
| IDLE | `STALE` | | — | HOLD |
| MITIGATING | bất kỳ | `now < deadline` | — (reconcile ở 8.4) | MITIGATING |
| MITIGATING | bất kỳ | `now ≥ deadline` | **revert** `setBandwidth(…, 20)` | PROBING(window=now+W) |
| MITIGATING | `STALE_INTERVENTION` | | **revert ngay** (N15) | PROBING |
| MITIGATING | `STALE` | | — | HOLD (giữ can thiệp) |
| PROBING | bất kỳ | `now ≥ window_end` | — | IDLE, k=0 |
| PROBING | `ACT` | target giống | **inject** lại | MITIGATING(k+1, deadline=now+T_{k+1}) |
| PROBING | `ACT` | target khác | — (fail-closed) | IDLE, k=0 |
| PROBING | `ACT` | ≥2 ứng viên | — | PROBING |
| PROBING | khác | trong W | — | PROBING |
| HOLD | `STALE` | có can thiệp mở và `now ≥ deadline` | **revert** (lịch thắng) | PROBING |
| HOLD | `STALE` | còn lại | — | HOLD |
| HOLD | freshness trở lại | có can thiệp mở | — | MITIGATING (deadline giữ nguyên) |
| HOLD | freshness trở lại | không có can thiệp | — | IDLE |

### 7.3 Ba dòng dễ làm sai

- **HOLD + quá hạn → vẫn revert.** N12 cấm **hành động mới**; gỡ can thiệp của
  chính mình là **fail-safe**. Không gỡ → lease 120 s hết → `stale_intervention`.
- **PROBING + target khác → IDLE, reset k.** `k` là bộ nhớ về **một** thủ phạm;
  thủ phạm đổi thì bộ nhớ cũ vô nghĩa. Đây là **lựa chọn**, không phải chân lý —
  khai ra để người sau biết có thể đổi.
- **MITIGATING + chưa hết hạn → reconcile.** Mầm của 8.4: mỗi nhịp so `desired_bw()`
  với `link.capacity.bwMbps` đọc từ twin, lệch thì gửi lại **lệnh tuyệt đối**
  (level-triggered reconciliation ⇒ gửi hai lần phải an toàn).

## 8. Hợp đồng của `decide()` — hàm thuần

```python
decide(view: DetectorView, cstate: ControllerState,
       now_mono: float, params: PolicyParams)
    -> tuple[tuple[Action, ...], ControllerState]
```

| Ràng buộc | Phục vụ |
|---|---|
| `now_mono` truyền vào (monotonic, không `time.time()` vì NTP có thể nhảy lùi) | C10, C11 |
| `params` truyền vào, không phải hằng module | sim quét được tham số |
| `ControllerState` **frozen**, trả bản mới | audit ghi được `before`/`after` |
| `intervention_id` **tất định** `ctl-<bootId>-e<episode>-k<attempt>:<kind>` | **C10** |
| không `time`/`random`/`requests`/`open(`/id ngẫu nhiên | test tĩnh |

Kết quả: **C7 được chứng minh ở tầng logic bằng 320 tổ hợp liệt kê**
(`5 state × 8 cause × 2 fresh × 4 mode`) chạy trong mili-giây, trước khi tốn một
phút Mininet nào.

## 9. Ẩn số chưa đóng (khai rõ, không đoán)

**Trong lúc `MITIGATING`, detector công bố gì?**

| Khả năng | Cơ chế | Công bố |
|---|---|---|
| **A** | UDP 47 Mbps đập vào shaper 7 Mbps → `qdiscDropDelta` tăng → alarming, nhưng entity ∈ blast radius → nhánh `suppressed_intervention` | `unknown(suppressed_intervention)` |
| **B** | giới hạn đưa mọi thứ về trong biên → không alarming | `normal` sau 3 tick |

Bằng chứng gián tiếp nghiêng về **A** (`phase7_s11_live.json`: `suppressed_ticks
= 84` trên n=4 can thiệp), **nhưng** actuator ở thí nghiệm đó là `inject` trên
link `s1-s2` (kiểu admin-down), **không phải** `setBandwidth` → **không phải bằng
chứng**.

**Cách xử lý:** thiết kế gỡ **theo lịch** nên không đọc `normal` cũng không đọc
`suppressed` để quyết định. Sim chạy **cả hai** kịch bản và
`test_ket_qua_khong_doi_theo_an_so_93` chứng minh số hành động **giống hệt**.
Lesson 8.3 (đo lại S11 cho `setBandwidth`) sẽ đóng ẩn số này.

> 🚨 **Cấm:** dùng `suppressed_intervention` làm tín hiệu "flood vẫn còn". Nó
> không nằm trong hợp đồng R1–R4, phụ thuộc nội tại `blast_radius.py`, và là tín
> hiệu **do chính hành động của mình tạo ra** — đúng cái bẫy mà lesson này tồn
> tại để tránh.

## 10. Dự đoán niêm phong

`results/report/phase8_sim_predictions.json` (immutable, script từ chối ghi đè).
Sinh **trước** mọi phép đo live của 8.6/8.7.

| Dự đoán | Giá trị |
|---|---|
| C6 — hành động / 600 s, flood liên tục | **13** |
| C6 — hành động / 600 s, mạng bình thường | **0** |
| C6 — hành động / 1800 s, Poisson (10 000 seed) | p50 **14**, p95 **26**, max 41 |
| C12 — tỷ lệ mù, flood liên tục | **97.3%** |
| C12 — tỷ lệ mù, Poisson trên tổng thời gian | p50 **17.7%**, p95 44.5% |
| C12 — tỷ lệ mù, mạng bình thường | **0%** |
| gây hại: circuit breaker vs bang-bang | **9.7%** vs **69.3%** |
| `max_open_s` phải luôn < 120 s | 110.0 s (max trên 10 000 seed: 110.0) |

`content_sha256 = a38c6434f8d333c3eb0ec7cd2e6abe49342d7d02c21cb7cfa4687f1528504c88`

Đuôi phân phối phải khai: `harm_fraction` có `max = 1.0`. Đó là **2 trên 475**
seed có flood, và cả hai có span dài nhất **0.7 s** — ngắn hơn một tick, nên
`n_act = 2 tick` không thể bắt được. Không phải lỗi controller: đó là giới hạn
độ phân giải của sensor, đã biết từ Phase 6.

**Khai báo thêm (khác biệt receipt):** `latency_command_randomized.json` đo trên
collector `qdisc_v2`, còn release đóng băng đòi `v3-qdisc-ratevalid`. Độ trễ lệnh
là đường truyền (Ditto → agent → `tc`) nên không phụ thuộc phiên bản feature,
nhưng đây là khác biệt phải ghi, không giấu.

**C12 phải báo cáo có điều kiện, hai con số:** tỷ lệ mù *trong các khoảng có can
thiệp* (≈97%) và *trên tổng thời gian vận hành* (Poisson p50 ≈ 18%, và **0%** khi
mạng bình thường). Rủi ro cụ thể: một flood thứ hai độc lập từ h2 trong khoảng
đang giảm thiểu h1 **bị che hoàn toàn** — Lesson 8.7 có thí nghiệm riêng cho nó.

## 11. Receipt của lesson này

| File | Nội dung |
|---|---|
| `controller/policy.py` | FSM thuần + bảng chuyển |
| `controller/sim.py` | mô phỏng sự kiện rời rạc + đối chứng bang-bang |
| `scripts/run_phase8_sim.py` | sinh dự đoán, từ chối ghi đè |
| `results/report/phase8_sim_predictions.json` | **bản niêm phong** |
| `test/test_phase8_policy.py` | 738 test (320 tổ hợp C7 + liệt kê classify + vòng đời) |
| `test/test_phase8_sim.py` | 10 known-answer test |
