# Phase 7.5 — Ngân sách độ trễ end-to-end

## 1. Tám mốc thời gian

Phép đo dùng tám mốc thay vì năm mốc ban đầu để tách chi phí inject, lần quan
sát vật lý đầu tiên, nhánh ghi Ditto và thời điểm trình duyệt thực sự vẽ:

`tA (inject bắt đầu) → tB (flood chạy) → t_obs (bằng chứng thô) → t1 (công bố alarm) → t2 (mailbox) → {t3 (HTTP 2xx), t4 (SSE)} → tDom (Vue flush) → t5 (đã vẽ)`.

`t3` và `t4` là hai nhánh song song sau persist. Vì vậy `write_2xx=t3-t2`
được báo riêng, còn đường găng UI dùng `fanout_sse=t4-t2`; không lấy `t4-t3`.

## 2. Con số S4 2007 ms của Phase 6R

S4 2007 ms chỉ có ba mẫu phát hiện được, là giá trị lớn nhất theo nearest-rank
p95, chỉ thuộc lỗi degrade s2-s3. Nó đo từ lúc bắt đầu lệnh inject tới snapshot
báo động, không đo từ snapshot có bằng chứng. Các run đều mất một tick do thay
đổi `tc` làm rate không hợp lệ và đều inject ngay sau snapshot (pha gần 0), tức
đo trúng pha xấu nhất. Đại lượng Phase 7.5 so được với nó là
`s4_like_from_cmd=t1-tA`, không phải `detect=t1-t_obs`.

## 3. Phương pháp

Mọi mốc Python dùng `time.monotonic()` trong cùng process. Mốc
`performance.now()` của Chromium được đổi sang đồng hồ Python bằng Cristian
min-RTT với 31 mẫu; RTT/2 là cận sai số. Mỗi trial chờ `3 + U(0,1)` giây với
seed 7005 để phân bố pha inject, và trial đầu là warmup bị loại nhưng vẫn lưu.

Headline là `e2e_from_event=t5-tB`, vì ngân sách 5000 ms phải bao gồm tầng quan
sát vật lý. Verdict được tính trên tổng từng trial; p95 của tổng không được thay
bằng tổng p95 từng tầng.

## 4. Kiểm chứng thước đo

- Clock bridge được kiểm tra trong 20 thế giới giả có độ trễ bất đối xứng; sai
  số thật phải nằm trong cận RTT/2 đã báo.
- Phân rã có known-answer test, test conflation/censoring, bỏ mốc trước sự kiện,
  và chạy cả aggregate/plot trên dữ liệu tổng hợp.
- Timeline runner kiểm tra `t_in ≤ t1 ≤ t2`, join `(bootId, seq)` và `t3 ≥ t2`.
- Chromium thật với Ditto giả kiểm tra nhân quả `server push ≤ t4 ≤ tDom ≤ t5`
  trong cận clock bridge.

## 5. Dự đoán khóa trước phép đo live

| Chỉ số | Dự đoán trước live | Căn cứ |
|---|---:|---|
| `inject_cmd` | khoảng 340 ms, ổn định | sleep 300 ms và hai shell command |
| `phys_obs` p50 / p95 | khoảng 0.6 s / 1.2 s | pha snapshot; đôi lúc cần thêm tick |
| `detect` | khoảng 2–3 ms | suspect debounce bằng 1 |
| `s4_like_from_cmd` p95 | 1.5–1.6 s, dưới 2007 ms | không reset `tc`, pha ngẫu nhiên |
| `write_2xx` p95 | khoảng 20 ms | số đo Phase 7.3 |
| `fanout_sse` p95 | 10–50 ms | Ditto, SSE và proxy |
| `paint` | 16–33 ms | double requestAnimationFrame |
| `twin_ui` p95 | dưới 100 ms, đạt 1000 ms | đường găng sau detector |
| `e2e_from_event` p95 | 1.3–1.4 s, đạt 5000 ms | quan sát vật lý chi phối |
| `tick_dt_across_inject` max | khoảng 1.34 s, dưới 1.5 s | inject giữ `net_lock` khoảng 340 ms |
| Pha theo bốn quý | khoảng 6 trial/quý | n=25 và randomized settle |

## 6. Kết quả live

Campaign chạy 25 trial hợp lệ và một warmup bị loại. Cả 25/25 trial đều được
phát hiện và hiển thị; không có write conflation.

| Tầng / tổng | p50 (ms) | p95 (ms) | max (ms) |
|---|---:|---:|---:|
| `phys_obs` | 1158.6 | 1432.6 | 1502.1 |
| `detect` | 1.4 | 1.7 | 1.7 |
| `mailbox` | 0.6 | 0.8 | 0.8 |
| `write_2xx` | 8.6 | 11.2 | 13.2 |
| `fanout_sse` | 8.5 | 11.0 | 13.2 |
| `vue_flush` | 3.6 | 4.7 | 4.9 |
| `paint` | 22.4 | 31.5 | 31.6 |
| `s4_like_from_cmd` | 1512.7 | **1770.8** | 1841.9 |
| `twin_ui` | 35.3 | **44.2** | 50.3 |
| `e2e_from_event` | 1196.6 | **1469.2** | 1534.6 |
| `e2e_from_cmd` | 1549.0 | 1805.8 | 1873.0 |
| `inject_cmd` | 338.4 | 402.6 | 406.5 |

Ba verdict p95 đều **PASS**: S4-like 1770.8 ≤ 3000 ms, twin/UI 44.2 ≤
1000 ms, và event-to-paint 1469.2 ≤ 5000 ms. Clock bridge có cận sai số
tốt nhất 0.322 ms và drift đầu-cuối 0.019 ms. Warmup `[0]` đã bị loại.

So với dự đoán: detect nhanh hơn (1.7 so với 2–3 ms), write nhanh hơn (11.2
so với khoảng 20 ms), fanout nằm trong 10–50 ms, paint khớp 16–33 ms và
twin/UI tốt hơn mức dưới 100 ms. S4-like và E2E chậm hơn dự đoán lần lượt
khoảng 171 ms và 69 ms ở mép trên dự đoán, chủ yếu vì `phys_obs` p95 1432.6
ms thay vì khoảng 1200 ms. `inject_cmd` có p50 đúng dự đoán 340 ms nhưng đuôi
p95 402.6 ms cho thấy nó không ổn định như dự đoán.

Hai dự đoán bị bác bỏ rõ ràng. `tick_dt_across_inject` có p95 2002.7 ms và
max 2003.6 ms, không phải 1.34 s; đầu dò inject có thể làm bỏ hẳn một nhịp
collector. Phân bố `inject_phase` đo được là `[4, 14, 7, 0]`, không gần sáu
mẫu mỗi quý. Randomized settle đã được áp dụng, nhưng metric pha chuẩn hóa bằng
khoảng giữa hai tick quan sát; khi khoảng đó dài 2 s do bỏ nhịp, giá trị bị nén
về nửa đầu. Vì vậy campaign chứng minh kết quả trên các pha đã lấy mẫu, nhưng
không chứng minh được độ phủ pha đồng đều như dự kiến. Đây là giới hạn cần giữ
nguyên, không sửa hậu nghiệm.

Artifact nguồn là `results/report/phase7_e2e_latency.json`; hình đường găng và
histogram là `results/report/phase7_e2e_latency.png`.

## 7. Vì sao ba con số khác nhau

| Phép đo | Đơn vị | Mốc gốc → mốc đích | Điều kiện |
|---|---|---|---|
| Delay Phase 6 | tick | nhãn dương đầu → alarm đầu | offline |
| TTD 6R = 2007 | ms | inject bắt đầu → snapshot alarm | n=3, degrade, pha 0, mất một tick |
| E2E Phase 7.5 | ms | flood chạy (`tB`) → frame vẽ (`t5`) | flood, pha ngẫu nhiên, n=25 |

Các đại lượng khác mốc gốc, mốc đích và điều kiện nên không được ép cho bằng
nhau. `s4_like_from_cmd` chỉ là cầu nối định nghĩa để so trực tiếp với 6R.

## 8. Giới hạn

- Phép đo live chỉ dùng một sự kiện flood h1→srv1 47 Mbps.
- Chromium headless thường vẽ ở 60 Hz; tab ẩn có thể tạm dừng rAF.
- Công cụ inject giữ `net_lock` khoảng 340 ms và có thể kéo dài tick bao quanh.
- Kênh conservation chậm không nằm trong campaign này. Phase 6R combined cho
  thấy khoảng 11 giây, vượt SLO 5 giây; đây là giới hạn của kênh phát hiện,
  không phải đường ống Ditto/SSE/UI.
