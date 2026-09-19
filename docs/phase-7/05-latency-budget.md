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

Chưa chạy tại thời điểm khóa dự đoán. Phần này sẽ được cập nhật chỉ từ artifact
`results/report/phase7_e2e_latency.json` sau khi commit thiết kế và dự đoán.

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
