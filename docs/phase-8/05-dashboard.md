# Phase 8.5 — Người vận hành thấy vòng kín thế nào

Từ 8.4 hệ **tự tác động lên mạng thật**. Người vận hành là lớp phòng thủ cuối
cùng — người duy nhất có thể nhận ra "controller đang làm sai" và tắt nó. Nếu UI
hiển thị sai, lớp phòng thủ đó biến mất. Lesson này vì thế là một **cơ chế an
toàn**, không phải lớp sơn.

---

## 1. Chế độ hỏng đặc thù của vòng kín

```
Controller đang bóp băng thông h1. Vì bóp đúng, mạng khoẻ lại.
Detector báo `normal`. Dashboard Phase 7 hiện "All systems normal", xanh toàn bộ.
Người vận hành thấy mọi thứ ổn. Thực tế: ĐANG CÓ SỰ CỐ, và hệ đang can thiệp.
```

Đây không phải bug hiển thị mà là **hệ quả trực tiếp của bài học 8.2**: sự khoẻ
mạnh quan sát được trong lúc đang can thiệp là do **chính mình** tạo ra. Cùng một
nguyên lý đã trả công ba lần:

| Tầng | Biểu hiện |
|---|---|
| 8.2 điều khiển | đừng gỡ can thiệp vì "trông có vẻ khoẻ" → gỡ theo lịch |
| 8.3 đo lường | `log_first` cho 0 act vì **đang ức chế**, không phải vì không có vấn đề |
| **8.5 giao diện** | đừng nói "ổn" vì detector báo `normal` khi controller đang làm việc |

## 2. Ý ĐỊNH ≠ HIỆN THỰC

`controlView.js` **chỉ** ánh xạ `(mode, stale)` từ Thing `controlloop`. Cấm suy
`mode` từ `capacity.bwMbps`, vì:

| | `bwMbps` nói gì | `controlloop.mode` nói gì |
|---|---|---|
| | **hiện thực**: băng thông đang là 7 | **ý định**: controller đang chủ đích giảm thiểu |

Ba tình huống chúng khác nhau, cả ba đều xảy ra thật:

1. Người vận hành gửi `setBandwidth` tay → bw = 7, `mode = IDLE`. Suy diễn sẽ
   **nói dối** rằng controller đang hành động.
2. Lệnh còn trên đường (p50 **667 ms**, đo ở 8.4) → `mode = MITIGATING`, bw vẫn
   20. Suy diễn **bỏ sót** đúng khoảnh khắc quan trọng nhất.
3. Lease hết hạn, watchdog phục hồi bw = 20 nhưng controller kẹt `MITIGATING` →
   suy diễn nói "không có gì"; sự thật là "controller hỏng, lưới an toàn vừa bắt".

Firewall test khoanh đúng **một file** (`controlView.js`), không cấm tràn lan:
đọc `bwMbps` ở `App.vue::watchForReflection` vẫn **hợp lệ** — đó là xác nhận
level-triggered cho lệnh người dùng vừa bấm, đúng mẫu đã chốt ở 8.3/8.4.

## 3. Hai nguồn, hai freshness — chống masking

| Detector | Controller | UI phải nói |
|---|---|---|
| tươi | tươi | theo MAP của cả hai |
| tươi | **chết** | 🚨 **ô nguy hiểm nhất** — mạng được quan sát nhưng **không ai hành động** |
| chết | tươi | ⚠️ controller đang mù → sẽ vào HOLD |
| chết | chết | 🚨 hệ tê liệt |

Ô thứ hai là ô mà UI ngây thơ hiển thị **xanh**: detector tươi + `normal` →
không cảnh báo. Nếu dùng **một** nhãn freshness chung (hoặc lấy `max` của hai
"cập nhật lần cuối"), **nguồn sống sẽ che nguồn chết** — hỏng kiểu *masking*.

Quy tắc: **mỗi nguồn một tracker; không bao giờ gộp, không bao giờ lấy max.**
`createFreshness()` trả về **instance** nên chỉ cần tạo hai. Bẫy cụ thể: dùng
chung một tracker thì `tr.retired` sẽ nhận `bootId` của cả hai → **cả hai từ chối
bản tin của nhau → cả hai STALE vĩnh viễn**. Có test.

## 4. `allClear` chặt hơn

```js
allClear(deviceAlertCount, detector, control)
  = deviceAlertCount === 0
 && detector.present && !detector.stale && detector.state === 'normal' && !detector.cause
 && control.present            // chưa bootstrap Thing -> không được nói "ổn"
 && !control.stale             // chống masking
 && control.mode === 'IDLE'    // MITIGATING/PROBING/HOLD đều là "đang có chuyện"
```

`mode === 'IDLE'` là vế quan trọng nhất — nó chính là bài học §1 ở tầng giao diện.

**Hệ quả có chủ đích lên Phase 7:** `test_s12_kill_to_stale_under_5s` nay phải
cho controller đập nhịp, nếu không "All systems normal" **không bao giờ** xuất
hiện. Đó là ngữ nghĩa mới, đúng thiết kế — đã sửa test và ghi lý do tại chỗ.

## 5. Bốn quyết định trong `controlView`

| Quyết định | Vì sao |
|---|---|
| thiếu `mode` → **`HOLD`**, không phải `IDLE` | fail-safe, cùng nguyên tắc với `initial_controlloop_body` (8.3) |
| `mode` lạ → **`'unknown'`**, không phải `null` | dashboard cũ + controller mới phải nói "tôi không hiểu", không im lặng coi như ổn (*forward compatibility* an toàn) |
| `PROBING` là **`'active'`** | giới hạn đã gỡ nhưng **episode chưa kết thúc** — sự cố có thể còn; nói "rảnh" là sai |
| `HOLD` là **`'warning'`** | controller **tự nguyện rút lui** vì không tin dữ liệu → đó là lúc cần con người nhất |

## 6. Kênh thị giác: 🛡 khác ⚑

Phase 8 thêm một biến **thứ ba, trực giao**: *"entity này là mục tiêu của một can
thiệp đang mở"*. Nhồi nó vào màu `health` là ba biến một kênh → mất thông tin, và
người vận hành không phân biệt được hai việc rất khác nhau:

```
h1 bị NGHI NGỜ (detector nêu tên)          -> cần điều tra
h1 đang BỊ GIỚI HẠN (controller hành động) -> đã có hệ xử lý
```

| Biến | Kênh | Lý do |
|---|---|---|
| sức khoẻ thiết bị | **màu** nền | quen từ Phase 5 |
| detector nêu tên | **⚑ + viền dày liền nét** | quen từ Phase 7 |
| **mục tiêu giảm thiểu** | **🛡 + viền NÉT ĐỨT** | kênh *kiểu nét*, trực giao với cả màu lẫn độ dày; nét đứt gợi đúng "tạm thời, sẽ được gỡ" |

Một node có thể **vừa dày vừa đứt** (vừa bị nêu tên vừa bị giới hạn) và cả hai
kênh vẫn đọc được.

## 7. Đếm ngược bằng đồng hồ của chính trình duyệt

`holdRemainingS` là **KHOẢNG** (hợp đồng D, 8.3), nên UI neo vào **thời điểm
nhận** và đo bằng đồng hồ của chính nó:

```js
remaining = max(0, holdRemainingS - (nowMs - receivedAtMs) / 1000)
```

- Sai số = độ trễ mạng (~22 ms), **không phụ thuộc lệch đồng hồ** máy chủ/trình duyệt.
- `nowMs` lấy từ **`performance.now()`**, không phải `Date.now()`: `Date.now()`
  có thể **nhảy lùi** khi NTP hiệu chỉnh (bài học 7.2/7.5).
- **Kẹp sàn 0**: controller chết thì số sẽ trôi âm; `"probe sau 0 s"` đỡ hơn `"-47 s"`.
- **STALE → ngừng đếm hoàn toàn** (`countdown()` trả `null`): đếm ngược từ một
  bản tin đã chết là nói dối có chủ đích.

## 8. UI phải nói rằng hệ đang bị thu hẹp quan sát

Từ 8.1/8.2/8.3: vùng ức chế **15/16 entity**, dự đoán 94–97% thời gian có can
thiệp mở trong lúc flood, và 8.3 đo thật **87 tick** `suppressed_intervention` ở
nhánh `log_first`. Người vận hành **phải biết**, vì nó đổi hành vi của họ: khi hệ
đang bị thu hẹp quan sát, con người phải nhìn kỹ hơn, không phải lơi ra.

Và nó **suy ra thuần bằng MAP**, không thêm suy diễn nào: detector **tự công bố**
`cause = "suppressed_intervention"`.

**Trung thực về mức độ:** 8.3 đo được **1/3 round** dưới flood **không** bị ức chế
(`link-s2-s3` nằm ngoài vùng 15/16). Nên nhãn nói **"QUAN SÁT BỊ THU HẸP"**, tuyệt
đối không nói "hệ thống đang mù" — và có test khẳng định chuỗi "mù" không xuất
hiện trên trang.

Con số 15/16 **chưa** hiện trên UI: nó nằm trong `intervention.blast_radius_n` của
audit, không nằm trên twin. Thêm `blastRadiusN` vào `features.decision` của
`controlloop` sẽ phải sửa **hợp đồng D đã niêm phong** (`47464487…`) → cần một
**amendment**. Quyết định hiện tại: **nhãn định tính trước**, amendment để lại cho
8.7 khi C12 cần con số; ghi ra đây để không ai tưởng là bỏ quên.

## 9. Lỗi tìm được khi thi công

1. **TDZ trong `resync`:** dùng `things.find(...)` trước dòng `const things = …`
   → `ReferenceError: Cannot access 'things' before initialization` → topology
   không tải được. Sửa: lọc từ `all`.
2. **Khai báo thiếu sau khi vá TopologyView:** `graphKey` tham chiếu `shAttr`
   nhưng khối khai báo `shieldedSet`/`shAttr` không khớp anchor nên không được
   chèn → `ReferenceError` trong một computed → **Vue ngừng cập nhật**, SSE vẫn
   chạy nhưng UI đứng im ở trạng thái đầu.

   > Bài học chẩn đoán: cả hai lỗi biểu hiện y hệt nhau — "SSE có sự kiện, UI
   > không đổi". Cách tìm ra nhanh nhất là **build không minify** rồi bắt
   > `pageerror`; với bản minify thông báo chỉ còn `Cannot access 'Te' …`.

3. **Không có test nào bắt được hai lỗi này ngoài E2E.** Unit test JS vẫn xanh
   30/30 khi trang hỏng hoàn toàn. Đây là lý do 8.5 phải có E2E Chromium.

## 10. Receipt

| File | Nội dung |
|---|---|
| `dashboard/src/lib/controlView.js` | MAP thuần `(mode, stale)`, `allClear` mở rộng, `observabilityNote` |
| `dashboard/src/App.vue` | tracker thứ hai, `acceptControl`, lọc controlloop khỏi graph |
| `dashboard/src/components/AlertPanel.vue` | dòng "Vòng kín" + STALE riêng + dòng quan sát bị thu hẹp |
| `dashboard/src/components/TopologyView.vue` | kênh 🛡 + nét đứt, trực giao với ⚑ |
| `dashboard/test/controlView.test.mjs` | 11 test: firewall, thuần, đếm ngược, all-clear, masking, hai tracker |
| `test/test_phase8_ui_e2e.py` | 5 kịch bản Chromium với twin giả |
| `scripts/phase7_fake_ditto.py` | `controlloop_doc`, `push_control`, `stop_control_heartbeat` (nhịp tim **riêng**) |
