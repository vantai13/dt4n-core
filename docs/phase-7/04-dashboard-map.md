# Phase 7.4 — Dashboard MAP và S12

## 1. Luật MAP

Dashboard không chạy lại detector. Mức độ hiển thị là hàm duy nhất:

```text
severity = f(decision.state, stale)
```

| `stale` | `decision.state` | Severity |
|---|---|---|
| `true` | bất kỳ | `stale` |
| `false` | `act` | `critical` |
| `false` | `suspect` | `warning` |
| `false` | `warming_up`, `unknown`, giá trị lạ | `unknown` |
| `false` | `normal` | không cảnh báo |

Evidence chỉ tạo nhãn “kênh nhanh”, “kênh chậm”, “cả hai” hoặc “đang giữ
trạng thái (hysteresis)”. Nó không được đổi severity. Property test thử mọi tổ
hợp evidence và firewall cấm logic ngưỡng detector trong `dashboard/src`.

Highlight cũng là MAP: chỉ id trong `evidence.affected` khớp node/edge hiện có
mới được đánh cờ và tăng độ dày. Id không khớp được báo ra; dữ liệu STALE không
được highlight. Màu health của topology không bị detector ghi đè.

## 2. Amendment 1 — monotonic freshness

Quy tắc C.5 đã niêm phong ở 7.2 coi mọi thay đổi `(bootId, seq)` là heartbeat.
Nó nhận cả seq lùi, nên snapshot cũ từ things-search hoặc PATCH đến muộn có thể
làm tươi UI và tua trạng thái về quá khứ. Tracker cũ được giữ nguyên và có test
chứng minh lỗi này.

Amendment `DT4N-P7-CONTRACT-A1` thay quy tắc phía consumer:

- Lần đầu chỉ ARM: được hiển thị nhưng vẫn STALE.
- Cùng boot chỉ nhận seq tăng chặt; seq lùi hoặc trùng bị bỏ cả bản tin.
- Boot mới chưa thấy được nhận và boot trước đi vào tập retired.
- Bản tin từ boot retired bị từ chối, không hiển thị và không làm tươi TTL.
- TTL vẫn đo bằng đồng hồ monotonic của consumer; schema producer không đổi.

Giới hạn còn lại: bootId là chuỗi ngẫu nhiên không có thứ tự. Nếu bản tin boot
cũ tới trước khi consumer từng nhìn thấy boot mới, consumer không thể biết đó là
bản cũ. Đóng hoàn toàn trường hợp này cần thêm incarnation có thứ tự vào schema.

## 3. Phát hiện trong dashboard hiện tại

`resync()` đọc `/search/things`, là chỉ mục có thể trễ so với stream. Mỗi lần SSE
kết nối lại đều resync, nên consumer cần tự bảo đảm monotonic reads. Detector
được tách khỏi `thingsById`; heartbeat một giây không còn kích hoạt dựng lại graph.

`AlertPanel` trước đây nói “All systems normal” chỉ dựa trên cảnh báo thiết bị.
Luật mới chỉ cho phép câu này khi không có cảnh báo thiết bị, detector có mặt,
tươi và ở `normal`.

Thời gian không reactive trong Vue. `nowMs` được gõ nhịp mỗi 250 ms và cập nhật
ngay khi tab hiện lại. `TopologyView` đặt tường minh cả trạng thái có/không có cờ
vì `DataSet.update()` chỉ merge. E2E quan sát `data-highlight`, không dựa vào nội
bộ Vue chỉ có ở bản dev.

## 4. Khoảng S12

Heartbeat cuối nằm trong một tick trước lúc detector chết. TTL là 3000 ms, độ
trễ producer-to-browser là `L`, và timer UI có độ phân giải tối đa 250 ms:

```text
S12 ∈ [3000 - 1000 + L, 3000 + L + 250]
    = [2000 + L, 3250 + L] ms
```

Với Ditto giả, sáu mẫu là `2799, 2296, 2477, 3100, 2717, 2135` ms: min 2135
ms, max 3100 ms, đều nằm trong khoảng lý thuyết khi `L ≈ 0` và dưới S12 5 s.

## 5. Bốn tầng kiểm thử

| Tầng | Kết quả |
|---|---|
| Node unit: MAP + shared vectors + firewall | **17/17 pass** |
| Python conformance: 8 vectors + lỗi tracker cũ + gọi JS | **pass** |
| Chromium + Ditto giả | **4/4 pass** |
| Toàn bộ pytest | **pass** (4 skip hiện hữu), không sửa `ml/*.py` hay hợp đồng 7.2 |

Chromium xác nhận bốn kịch bản: tải trang với detector đã chết luôn STALE; sáu
lần kill ngẫu nhiên đều dưới 5 s; snapshot seq cũ sau reconnect bị từ chối; và
`act` chỉ highlight id đã join, báo id lạ, rồi nhận boot restart ở `warming_up`.

## 6. Dự đoán trước phép đo live

| Chỉ số | Dự đoán trước đo | Kết quả live |
|---|---|---|
| `kill_to_stale` min | khoảng 2.0–2.1 s | Chưa đo |
| `kill_to_stale` max | khoảng 3.2–3.5 s, không quá 5 s | Chưa đo |
| crash và hang | cùng phân phối | Chưa đo |
| `start_to_fresh` p95 | dưới 1.5 s | Chưa đo |
| `all_clear_while_stale` | 0 | Chưa đo |
| tải trang khi detector chết | `always_stale=true`, `all_clear_ever=false` | Chưa đo |

Bảng này được ghi trước khi chạy `measure_phase7_s12_live.py` và sẽ giữ nguyên
cột dự đoán khi bổ sung số đo.

## 7. Giới hạn

- S12 chỉ cam kết cho tab đang hiển thị; browser có thể throttle timer ở tab ẩn.
- STALE có thể xuất hiện khi Ditto hoặc đường SSE nghẽn dù detector vẫn sống.
  Phép đo 7.3 đã quan sát đúng tình huống này khi nginx bị pause 5 giây.
- BootId không có thứ tự nên còn giới hạn được nêu trong amendment.
- `scripts/dashboard_live.py` cũ dựa vào nội bộ Vue bản dev, không dùng được để
  kiểm chứng bản production build.
