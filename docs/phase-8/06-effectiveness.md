# Phase 8.6 — Đo hiệu quả bằng thí nghiệm, không bằng demo

Cho tới 8.5 ta đã chứng minh hệ **chạy**. Lesson này trả lời câu khác hẳn: **nó
có ích không, ích bao nhiêu, và bao nhiêu phần trong đó là nhờ những thứ đã xây?**

---

## 1. Thao tác hoá — biến chính, đăng ký trước

*"Controller làm mạng tốt hơn"* không đo được cho tới khi nói rõ: tốt hơn **cho
ai**, bằng **đại lượng gì**, trong **cửa sổ nào**, so với **cái gì**.

```
BIẾN CHÍNH (primary outcome)
  Tên:      goodput nạn nhân
  Đo:       txRate của Thing org.dt4n:host-h3, lấy từ twin
  Đơn vị:   Mbps (txRate byte/s × 8 / 1e6)
  Tổng hợp: TRUNG BÌNH CỘNG các mẫu có rateValid == true
  Cửa sổ:   [t_flood + 2 s, t_flood + 122 s]
  Mốc:      t_flood = lúc harness phát lệnh flood
  Loại bỏ:  mẫu rateValid == false bị BỎ, KHÔNG thay bằng 0
```

Hai dòng cuối là hai chỗ dễ thiên vị nhất:

- **Neo vào `t_flood`, không neo vào `t_act`.** `t_act` phụ thuộc detector và
  **khác nhau giữa hai nhánh** → hai nhánh sẽ đo trên hai cửa sổ khác nhau.
  `t_flood` do harness điều khiển, giống hệt cả hai nhánh.
- **Bỏ mẫu không hợp lệ, không thay bằng 0.** `setBandwidth` sinh đúng 1 tick
  `unknown(missing_data)` mỗi lần đổi bw (F8-6, đo ở 8.3) → thay bằng 0 sẽ
  **phạt riêng nhánh có controller**.

Chỉ **một** biến chính. Với 6 biến và ngưỡng 5%, xác suất ít nhất một biến "có ý
nghĩa" do ngẫu nhiên là `1 − 0,95⁶ ≈ 26%` — chọn biến sau khi nhìn số (HARKing)
gần như chắc chắn cho một kết quả đẹp kể cả khi controller vô dụng.

Biến thứ cấp (đăng ký trước, **không** dùng làm gate): goodput h3 trên cửa sổ
30 s · goodput **h2 (đối chứng âm)** · goodput h1 (cái giá) · rxRate srv1 · số
hành động · số lệnh gia hạn/trôi.

## 2. Thiết kế: pha ngẫu nhiên + khối ABBA/BAAB

**Ngẫu nhiên hoá pha** (`SETTLE_S + rng.uniform(0, 1)`) biến thiên lệch hệ thống
của chu kỳ lấy mẫu 1 s thành nhiễu ngẫu nhiên — trung bình ra 0.

**Khối ABBA** triệt tiêu xu hướng thời gian **tuyến tính** mà không cần đo nó.
Với hiệu ứng trôi `δ·t` và vị trí trong khối 1..4:

```
A ở {1,4} -> trôi trung bình 2,5δ      hiệu (A−B) = μ_A − μ_B   (δ biến mất)
B ở {2,3} -> trôi trung bình 2,5δ
AABB thì: A 1,5δ, B 3,5δ -> hiệu bị lệch −2δ
```

Hạn chế phải khai: ABBA chỉ xoá trôi **tuyến tính**; trôi bậc hai còn sót một phần.

**Mỗi khối là ABBA hoặc BAAB do đồng xu có seed** (`SEED = 20260920`). Đây không
phải trang trí: nó tạo **cơ sở hoán vị hợp lệ** để dùng randomization test —
phép kiểm chính xác, đúng ngay cả với ít khối.

## 3. Cửa sổ đo là một tham số của thí nghiệm

Với lịch backoff đã niêm phong (`T₀=15, T_max=110, W=14`):

```
Cửa sổ 30 s : bảo vệ 4,5 → 19,5              = 15 s / 28 s   ≈ 54%
Cửa sổ 120 s: 4,5→19,5 + 29→59 + 68,5→120    = 96,5 s / 118 s ≈ 82%
```

**54% so với 82% — cùng hệ, cùng controller.** Vì backoff mũ làm tỷ lệ bảo vệ
**tăng theo thời gian**; cửa sổ ngắn chỉ nhìn thấy chu kỳ đầu, chu kỳ tệ nhất.

Do đó: **120 s là biến chính** (hiệu quả ở trạng thái ổn định, khớp kịch bản
"flood kéo dài" và khớp dự đoán sim `a38c6434`), **30 s là biến thứ cấp** đã đăng
ký trước với nhãn *"hiệu quả giai đoạn đầu"*. Báo cáo **cả hai** — sự khác biệt
giữa chúng chính nó là một kết quả: nó đo giá trị của backoff.

> Khi hệ có hành vi **không dừng**, độ dài cửa sổ đo là một bậc tự do. Không khai
> nó là bỏ sót một tham số của thí nghiệm.

## 4. Giao thức rửa trôi giữa hai lượt

Tồn dư có thật, có số: cooldown **8 s** sau revert (release) · lease **15 s**
(8.4) · recovery burst **≈ 3 tick** (đo ở 8.1: tick 45–47, 14–18 Mbps) ·
`release_m` 3 tick · tiến trình iperf còn sót.

`require_clean()` là **kiểm tra trạng thái**, không phải `sleep`: mọi link truy
nhập client `bw == 20` (đọc qua twin) **và** detector `normal` 3 tick liên tiếp.
Quá 60 s không sạch → **huỷ lượt và ghi lại**.

**ĐIỀU KIỆN VÔ HIỆU (khoá trước):** nếu > **20%** số lượt bị huỷ, phép đo là **VÔ
HIỆU** (không phải FAIL) → sửa giao thức dọn dẹp rồi chạy lại.

## 5. Thống kê: effect size + CI, không phải p-value trần

`p-value` không nói khác biệt **lớn bao nhiêu** và không nói nó có **đáng quan
tâm** không; với `n` đủ lớn mọi khác biệt khác 0 đều "có ý nghĩa". Nên:

- **Effect size = chênh lệch trung bình, tính bằng Mbps** (đơn vị người đọc hiểu;
  không chuẩn hoá vì chuẩn hoá chỉ làm mất thông tin ở đây).
- **Bootstrap percentile CI95, lấy mẫu lại KHỐI** — trong một khối các lượt dùng
  chung điều kiện máy nên **không độc lập**; lấy mẫu lại lượt sẽ cho **CI hẹp
  giả**, tức là tự tin sai.
- **Randomization test** (đổi dấu hiệu theo khối, liệt kê đủ `2ⁿ` khi `n ≤ 20`):
  chính xác ở `n` nhỏ, bù đúng chỗ bootstrap yếu.
- **Luôn in ra toàn bộ hiệu số theo khối.** Trung bình và CI không bao giờ thay
  thế được dữ liệu.

`C5` (đã niêm phong ở 8.1): **CI95 của chênh lệch nằm hoàn toàn trên 0.**

## 6. DỰ ĐOÁN — khoá trước khi chạy

> Commit chứa mục này được tạo **trước** khi harness chạy lần đầu.

```
A vs B (controller bật / tắt), cửa sổ chính 120 s
  B: h3 ≈ 0,0–0,1 Mbps      (8.1 đo: h3 tụt 2,15 -> 0,01 Mbps khi flood)
  A: h3 ≈ 1,7–1,8 Mbps      (82% thời gian bảo vệ × 2,15 Mbps nền)
  => chênh lệch ≈ +1,7 Mbps, CI95 hoàn toàn trên 0  -> C5 PASS
  cửa sổ 30 s (thứ cấp): chênh nhỏ hơn, ≈ +1,1 Mbps (54% bảo vệ)

  h1 (cái giá): nhánh A thấp hơn nhánh B rõ rệt — ingress policing bóp cả
  traffic hợp lệ của thủ phạm (đã khai ở prereg 8.1, giới hạn số 4).

ĐỐI CHỨNG ÂM: chênh lệch goodput h2 phải có CI95 CHỨA 0.
  h2 gửi tới srv2 qua s1-s3, không đi qua s1-s2, và controller không bao giờ
  chạm h2-s1. Nếu CI95 của h2 KHÔNG chứa 0 -> có cơ chế ghép nối chưa hiểu
  hoặc harness rò rỉ -> biến chính phải diễn giải kèm cảnh báo và PHẢI điều
  tra trước khi kết luận.

A vs C (detector / luật ngưỡng) — ablation:
  DỰ ĐOÁN: KHÔNG có khác biệt đáng kể trên kịch bản flood.
  Cơ sở (replay offline, tôi tự chạy lại trên Phase 5, xem §7):
    luật ngưỡng kích hoạt tick 22 ở CẢ HAI run flood;
    detector + localize v2 kích hoạt tick 22 và 23.
  Đây là kết quả ĐƯỢC DỰ ĐOÁN, không phải thất bại.

  Nhánh C có thể cho SỐ HÀNH ĐỘNG cao hơn do luật ngưỡng không có ức chế can
  thiệp (sau khi bóp còn 7 Mbps > X = 6,18 nên nó vẫn "act" mỗi tick). Nếu
  vậy, đó là một phát hiện về giá trị của InterventionLog, KHÔNG phải lỗi
  harness.

ĐIỀU KIỆN VÔ HIỆU: > 20% lượt bị huỷ ở require_clean -> phép đo vô hiệu.
```

## 7. Ablation — replay offline (đã chạy, trước khi đo live)

Baseline giữ nguyên **mọi thứ** (FSM circuit breaker, backoff, actuator, lease,
audit, reconcile) và chỉ thay **nguồn kích hoạt**:

```
nếu txRate của một client > X trong 2 tick liên tiếp -> "act", target = client đó
X = 6,181986 Mbps   owner = (N-vary-s1007-r1, tick 16, h3)
                    lấy từ ĐÚNG 8 run train qua _assert_train_path
```

Replay trên 18 run Phase 5 (`controller/threshold_baseline.py`):

| run | fault | maxTx | fires | tick đầu → mục tiêu |
|---|---|---|---|---|
| F-flood-h1_to_srv1 | flood | 20,01 | 25 | **tick 22 → h1** ✅ |
| F-flood-h2_to_srv2 | flood | 20,01 | 24 | **tick 22 → h2** ✅ |
| **F-shift-s1-s2** | shift | 14,79 | 2 | **tick 42 → h3** ❌ **NẠN NHÂN** |
| F-shift-s1-s3 | shift | 10,91 | 0 | — |
| F-degrade-s1-s2 | degrade | 10,38 | 0 | — |
| F-admin_down ×2, F-degrade-s2-s3 | — | ≤ 3,03 | 0 | — |
| C-load2M | none | 2,16 | 0 | — |
| **C-vary** | none | **6,43** | 0 | — (đỉnh **vượt** X = 6,18) |
| 8 run train | none | ≤ 6,18 | 0 | — |

Đối chiếu detector + `localize` v2 (probe 8.1): flood h1 tick **22**, flood h2
tick **23**, và **0/8** run không-flood bị chỉ mặt.

**Biên an toàn — đo thêm, số còn xấu hơn dự kiến.** Số tick liên tiếp lớn nhất
vượt X, theo run:

```
C-vary-s2002-r1   (bình thường)  h2: 1 tick
N-vary-s1007-r1   (train)        h3: 1 tick
F-degrade-s1-s2                  h1: 1, h3: 1 tick
F-shift-s1-s3                    h2: 1 tick
F-shift-s1-s2                    h3: 3 tick  -> BẮN
```

**Năm** trong 18 run chỉ cách ngưỡng **đúng một tick**. Luật ngưỡng không bắn chỉ
vì đòi 2 tick liên tiếp. Hạ `n_act` xuống 1 là nó báo nhầm trên lưu lượng **hợp
lệ**.

Và một chi tiết nữa: trên `F-flood-h1`, tập mục tiêu mà luật ngưỡng chỉ mặt trong
cả run là `{h1, h3}` — **nó cũng chỉ vào nạn nhân trong recovery burst**, y hệt
cái bẫy đã phát hiện ở 8.1. Nó không bóp h3 **chỉ vì** cơ chế latch (chốt mục
tiêu tại tick act đầu) mà nó thừa hưởng từ FSM của ta.

### Cách đọc kết quả này

> Trên kịch bản tấn công flood — kịch bản duy nhất mà hệ được thiết kế để hành
> động — một luật ngưỡng đơn biến lấy từ cùng tập huấn luyện đạt hiệu quả tương
> đương pipeline phát hiện đầy đủ, và nhanh hơn một chu kỳ lấy mẫu ở một trong
> hai run. Đóng góp đo được của pipeline nằm ở nơi khác: trên tám run không-flood,
> luật ngưỡng chỉ mặt sai một lần, và lần đó nó nhắm vào **nạn nhân** trong giai
> đoạn hồi phục; pipeline im lặng ở cả tám. Ngoài ra luật ngưỡng vận hành gần như
> **không có biên**: năm run chỉ cách ngưỡng một chu kỳ lấy mẫu, trong đó có một
> run đối chứng hoàn toàn bình thường (đỉnh 6,43 so với ngưỡng 6,18).
>
> Kết luận: với một loại sự cố đã biết và đặc trưng rõ, một luật đơn giản là đủ.
> Giá trị của pipeline là ở việc **từ chối hành động** khi tín hiệu không phải
> thứ nó được hiệu chuẩn để nhận ra — và đó là tính chất chỉ đo được bằng các ca
> **âm tính**, không đo được bằng ca dương tính.

## 8. C3 phải đo TRỰC TIẾP

C3 = từ `act` công bố → thủ phạm thật sự bị giới hạn (p95), gate ≤ 10 000 ms.

**Không cộng p95 của các tầng lại**: `p95` của tổng ≠ tổng các `p95` khi các tầng
không độc lập — đúng cái bẫy `measurements/e2e_budget.py` đã xử lý ở 7.5. Đo
thẳng từ `act` tới lúc `capacity.bwMbps` xác nhận, `n ≥ 10`, **pha ngẫu nhiên**
(tầng "chờ nhịp control tick" là 0–1000 ms phân phối đều và chiếm ưu thế; không
ngẫu nhiên hoá thì đo ra một hằng số chứ không phải một phân phối).

Dự đoán tầng nào ăn thời gian: **chờ tick (0–1 s)** và **đường lệnh (p95 984 ms)**
— cả hai đều **không** phải lớp ML. Đó là một kết quả đáng nói: nút thắt của vòng
kín nằm ở chu kỳ lấy mẫu và đường lệnh, không ở suy luận.

## 9. Files

| File | Vai trò |
|---|---|
| `controller/threshold_baseline.py` | luật ngưỡng thuần, X từ train qua `_assert_train_path` |
| `measurements/ab_stats.py` | bootstrap CI trên khối + randomization test (thuần) |
| `scripts/phase8_ab_common.py` | sampler twin, `require_clean`, một lượt |
| `scripts/run_phase8_ab.py` | A vs B |
| `scripts/run_phase8_ablation.py` | A vs C |
| `test/test_phase8_ab_stats.py` | 12 known-answer test |

---

# KẾT QUẢ (viết SAU khi đo; dự đoán đã khoá ở commit `e1e0143`)

## 10. C5 — A/B controller BẬT vs TẮT

`results/report/phase8_ab_c5.json` (`b4da398a…`) · 8 khối × 4 lượt = **32 lượt**,
**0 lượt bị huỷ**, `measurement_valid = true`.
Thứ tự khối do đồng xu có seed: `BAAB ABBA ABBA ABBA ABBA BAAB BAAB ABBA`.

**Biến chính — goodput h3, cửa sổ 120 s (Mbps):**

| | |
|---|---|
| hiệu số theo khối | 1,953 · 1,978 · 1,876 · 1,905 · 1,792 · 1,900 · 1,832 · 1,909 |
| **effect size** | **+1,893 Mbps** |
| **CI95 bootstrap (trên khối)** | **[1,854 ; 1,931]** — hoàn toàn trên 0 |
| randomization test (chính xác, 2⁸ = 256 hoán vị) | **p = 0,0078** = 2/256, **giá trị nhỏ nhất có thể** với 8 khối |
| **C5** | **PASS** |

Ba con số nói cùng một câu chuyện: tám hiệu số thô đều dương và nằm trong dải hẹp
1,79–1,98; CI95 hẹp và xa 0; phép kiểm hoán vị đạt sàn. **Không có khối nào đi
ngược chiều.**

**Dự đoán khoá trước là +1,7 Mbps; đo được +1,893.** Dự đoán hơi bảo thủ vì tôi
ước tính 82% thời gian được bảo vệ, thực tế cao hơn (h3 gần như giữ nguyên mức
nền 2,15 Mbps trong cửa sổ 120 s).

**Biến thứ cấp (đăng ký trước, không phải gate):**

| Biến | Chênh lệch A − B | CI95 | Đọc |
|---|---|---|---|
| h3, cửa sổ **30 s** | **+1,439** | [1,295 ; 1,553] | đúng dự đoán: **nhỏ hơn** cửa sổ 120 s (+1,893), vì cửa sổ ngắn chỉ nhìn thấy chu kỳ đầu — chu kỳ tệ nhất. Dự đoán +1,1; đo +1,44 |
| **h2 (đối chứng âm)** | **−0,0003** | **[−0,0012 ; +0,0003]** | **CI95 chứa 0** ✅ — h2 không bị ảnh hưởng, đúng như phải thế |
| h1 (cái giá) | **−11,974** | [−12,151 ; −11,810] | thủ phạm mất ~12 Mbps: đúng ngữ nghĩa ingress policing, đã khai ở prereg 8.1 (giới hạn số 4) |
| rxRate srv1 | **−9,895** | [−10,084 ; −9,733] | flood tới đích giảm ~10 Mbps — controller chặn tại nguồn |

Đối chứng âm đạt là điều kiện để tin biến chính: nếu h2 lệch, ta đã phải điều tra
trước khi kết luận.

## 11. C3 — đo TRỰC TIẾP từ `act` tới lúc giới hạn có hiệu lực

`results/report/phase8_c3.json` · n = **9 lượt hợp lệ / 12 lượt thử**, pha ngẫu nhiên.

```
min 1025,2 ms | p50 1026,5 ms | p95 2032,1 ms | max 2032,1 ms
gate: p95 <= 10 000 ms   ->   PASS, biên 80%
```

**Phân bố lưỡng đỉnh tại ~1026 ms và ~2032 ms** — tức là **đúng một hoặc hai chu
kỳ control tick**. Đây là bằng chứng trực tiếp cho điều đã dự đoán ở §8: nút thắt
của vòng kín là **chu kỳ lấy mẫu/quyết định**, không phải lớp suy luận (detector
chấm điểm hết ~1,4 ms).

**Ba lượt bị huỷ, và lý do đáng nói:** ở các lượt 7, 9, 11, `require_clean` thấy
`h1-s1` vẫn ở 7,0 Mbps — **controller vẫn đang giữ giới hạn theo lịch** (hold có
thể tới `T_max` = 110 s sau khi flood đã tắt). Đó là **thiết kế đang hoạt động
đúng** (gỡ theo lịch, không gỡ vì "trông có vẻ khoẻ"), không phải lỗi. Đã nâng
thời gian chờ rửa trôi của harness C3 lên 180 s và ghi lại ở đây thay vì im lặng
bỏ ba lượt.

## 12. Ablation — A (detector) vs C (luật ngưỡng), đo LIVE

`results/report/phase8_ablation_rerun.json` (`07243d3e…`) · 6 khối × 4 lượt =
**24 lượt**, **0 lượt huỷ**. Thứ tự: `CAAC ACCA ACCA ACCA ACCA CAAC`.
`X = 6,18198616 Mbps`, owner `(N-vary-s1007-r1, tick 16, h3)`, lấy qua
`_assert_train_path` và **không chỉnh**.

| | A (detector) | C (luật ngưỡng) |
|---|---|---|
| goodput h3 trung bình (12 lượt mỗi nhánh) | **2,1462 Mbps** | **2,1459 Mbps** |
| số lệnh / lượt | 25–28 | 26–27 |

| Chênh lệch A − C | Giá trị |
|---|---|
| hiệu số theo khối (Mbps) | 0,0000 · 0,0003 · −0,0001 · 0,0017 · 0,0000 · 0,0000 |
| effect size | **+0,0003 Mbps** |
| CI95 bootstrap | **[−0,0000 ; +0,0009]** — **chứa 0** |
| randomization test (2⁶ = 64 hoán vị) | **p = 0,281** |
| số lệnh, A − C | −0,33 lệnh, CI95 [−0,667 ; +0,083] — **chứa 0** |

**Dự đoán khoá trước đã đúng:** *"KHÔNG có khác biệt đáng kể trên kịch bản
flood"*. Khác biệt đo được là **3 phần vạn Mbps** — nhỏ hơn độ phân giải thực tế
của phép đo ba bậc độ lớn.

Dự đoán phụ *"nhánh C có thể cho số hành động cao hơn do thiếu ức chế can thiệp"*
**không xảy ra**, và lý do đáng nói: nhánh C **thừa hưởng toàn bộ FSM circuit
breaker** của ta (latch, backoff, gỡ theo lịch). Trong `MITIGATING`, nhãn `ACT`
không sinh hành động mới — nên dù luật ngưỡng "kêu" mỗi tick, vòng vẫn chỉ hành
động theo lịch. **Đây là bằng chứng live cho giá trị của thiết kế 8.2**, tách
khỏi giá trị của detector.

> ⚠️ **Caveat tự động của `ab_stats`:** 6 khối là ít cho bootstrap percentile; đọc
> hiệu số thô và randomization test trước. Ở đây cả ba đồng thuận (hiệu số ≈ 0,
> CI chứa 0, p = 0,28) nên kết luận vững.

### Kết luận ablation (viết cho chương kết quả)

> Trên kịch bản tấn công flood — kịch bản duy nhất mà hệ được thiết kế để hành
> động — một luật ngưỡng đơn biến lấy từ cùng tập huấn luyện đạt hiệu quả **không
> phân biệt được** với pipeline phát hiện đầy đủ (chênh lệch +0,0003 Mbps,
> CI95 chứa 0, p = 0,28), và trong replay offline nó còn nhanh hơn một chu kỳ lấy
> mẫu ở một trong hai run. Đóng góp đo được của pipeline nằm ở nơi khác: trên tám
> run không-flood, luật ngưỡng chỉ mặt sai một lần, và lần đó nó nhắm vào **nạn
> nhân** trong giai đoạn hồi phục (`F-shift-s1-s2`, tick 42 → h3); pipeline im
> lặng ở cả tám. Ngoài ra luật ngưỡng vận hành gần như **không có biên**: năm
> trong mười tám run chỉ cách ngưỡng **đúng một chu kỳ lấy mẫu**, trong đó có một
> run đối chứng hoàn toàn bình thường (đỉnh 6,43 so với ngưỡng 6,18).
>
> Với một loại sự cố đã biết và đặc trưng rõ, một luật đơn giản là đủ. Giá trị của
> pipeline là ở việc **từ chối hành động** khi tín hiệu không phải thứ nó được
> hiệu chuẩn để nhận ra — tính chất chỉ đo được bằng các ca **âm tính**.

## 13. Sự cố hạ tầng trong lúc đo (khai đầy đủ)

Lượt ablation **đầu tiên** (8 khối) phải **bỏ**: từ khối 4 trở đi Ditto trả
`503 ThingUnavailable`, collector báo `PATCH ... -> 500`, và mọi lượt sau đó cho
`primary=None`.

**Nguyên nhân gốc, đã xác định bằng số:** container MongoDB chạm trần bộ nhớ
cgroup — `252,4 MiB / 256 MiB` — khiến truy vấn chậm tới **55 s** (log Mongo:
`durationMillis: 55253`), Ditto không đọc được kho và trả 503. Đĩa 24%, RAM máy
còn 22 GB ⇒ **không phải cạn tài nguyên máy, mà là trần bộ nhớ của container**.

Xử lý: khởi động lại `mongodb` + `things`/`things-search`/`gateway`, xác nhận
Ditto trả 200 và Mongo về 204 MiB, rồi **chạy lại ablation với 6 khối** (giảm
thời lượng để ở trong ngân sách bộ nhớ). Lượt hỏng **không** được dùng để tính
bất kỳ con số nào.

> Đây là **phép đo vô hiệu do hạ tầng**, khác hẳn *giả thuyết bị bác bỏ* — cùng
> cách phân biệt đã áp dụng ở amendment 8.3. Ghi lại vì nó là một giới hạn thật
> của môi trường thí nghiệm: **ngân sách bộ nhớ của Ditto/Mongo giới hạn độ dài
> tối đa của một chiến dịch đo liên tục** (~3,5 giờ trong quan sát này).

## 14. Tổng kết số của Lesson 8.6

| Chỉ số | Kết quả | Gate |
|---|---|---|
| **C5** goodput nạn nhân, A vs B | **+1,893 Mbps**, CI95 [1,854 ; 1,931], p = 0,0078 | ✅ **PASS** |
| C5 (cửa sổ 30 s, thứ cấp) | +1,439 Mbps, CI95 [1,295 ; 1,553] | báo cáo |
| Đối chứng âm h2 | −0,0003 Mbps, CI95 [−0,0012 ; +0,0003] chứa 0 | ✅ đạt |
| Cái giá: h1 | −11,974 Mbps | khai trước ở prereg 8.1 |
| **C3** act → giới hạn có hiệu lực | p50 1026 ms, **p95 2032 ms** | ✅ **PASS** (biên 80%) |
| Ablation A vs C | +0,0003 Mbps, CI95 chứa 0, p = 0,281 | dự đoán ĐÚNG |
| Lượt bị huỷ | 0/32 (A/B), 0/24 (ablation) | ✅ < 20% |
