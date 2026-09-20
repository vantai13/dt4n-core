# Phase 8.3 — Hợp đồng vòng kín A–E và S11 cho actuator mới

Niêm phong: `results/report/phase8_contract.json`
`content_sha256 = 47464487d438f32212e53a0e599c2fc605023248fb8e06ed0c521e81ce7cbc93`
Ghim SHA của **18 file** (6 module `controller/`, 4 `bridge/`, `env_runner`,
`intervention_log`, `blast_radius`, release detector, 3 prereg/dự đoán).

Đây là lesson đầu tiên chạm vào hệ sống. Hợp đồng được niêm phong **trước** khi
đo S11 và **trước** khi viết `controller/runner.py`.

---

## A — Controller đọc detector **qua twin**

Controller chạy cùng tiến trình với vòng chạy của detector (M9) nên nó *có thể*
đọc thẳng biến trạng thái trong bộ nhớ. **Không được.** `DittoTransport` PATCH
một lần, **không retry**: một PATCH rớt là dashboard thấy một đằng, controller
thấy một nẻo — hai nguồn sự thật, đúng thứ mà luận điểm "twin là single source
of truth" chống lại.

| Chi phí của việc làm đúng | p95 |
|---|---|
| `write_2xx` | 11.173 ms |
| `fanout_sse` | 11.030 ms |
| **tổng** | **22.203 ms** trên ngân sách C3 10 000 ms = **0,22%** |

`controller/twin_reader.py` là consumer SSE **ngang hàng với dashboard**, dùng
đúng endpoint mà `dashboard/src/services/sseClient.js` dùng
(`fields=thingId,attributes,features`) — có test đối chiếu hai chuỗi.

Ba cái bẫy, cả ba đều có test:

1. **SSE trả delta, không trả Thing đầy đủ** → `deep_merge` vào cache; nếu quên,
   `affected` rỗng ở mọi tick mà `affected` không đổi →
   `test_delta_khong_lam_mat_affected`.
2. **Reconnect có thể trả bản cũ** → R3 kiểm **trước khi gộp**; seq lùi/trùng
   hoặc `bootId` đã retired → **bỏ cả bản tin** →
   `test_r3_kiem_truoc_khi_gop` chứng minh cache không đổi một byte.
3. **Một stream, hai loại dữ liệu** (`detector` và `link-*`) → một kết nối duy
   nhất → `test_mot_stream_hai_loai_du_lieu`.

Firewall bằng máy: `test_controller_khong_doc_tat_runner` quét **toàn bộ**
`controller/*.py` tìm `detector_runner`, `DetectorRunner`, `runner.published`,
`runner.timeline`.

## B — Can thiệp và vùng ức chế

| Quyết định | Giá trị | Lý do |
|---|---|---|
| tên hành động | `inject:rate_limit` / `revert:rate_limit` | không trộn với `inject:admin_down` của Phase 7 — hai loại có vùng ảnh hưởng và hậu quả khác hẳn |
| `targets` | `{'links': ['<client>-s1'], 'flows': []}` | dùng `flows` làm mù **16/16** entity thay vì 15/16 |
| hàm bán kính | `radius` | `setBandwidth` **không** đổi topology → Ryu không reroute → không có hành lang vòng. Luật đã ghim trong release: `radius_with_detour` **chỉ** cho can thiệp admin_down |

Với `h1-s1`, `radius` và `radius_with_detour` cho **cùng 15 entity** — nhưng vẫn
phải gọi đúng hàm vì luật đã ghim và nghiệm thu sẽ đối chiếu.

**Quy tắc append (cạm bẫy do chính `policy.py` tạo ra):** `_iid()` tất định +
`InterventionLog.append` ném `ValueError` khi id trùng ⇒

```
Mỗi Action do decide() phát ra  →  ĐÚNG MỘT lần append().
Gửi lại lệnh (reconcile)        →  KHÔNG append; chỉ POST lại với CÙNG cid.
```

`test_append_hai_lan_cung_id_thi_no` khoá điều này. Và
`test_inject_va_revert_cung_pair_key` khoá chuyện `_revert()` dùng **cùng**
`attempt` với `_inject()`: nếu lệch, `InterventionLog.active()` không bao giờ
đóng được khoảng và lease 120 s sẽ hết hạn mỗi lần.

## C — Lệnh

- **Tuyệt đối, không tương đối**: `{'bw': 7.0}`. Kênh truyền là **at-least-once**;
  *exactly-once* ở tầng truyền là bất khả thi, nên cách duy nhất có hiệu ứng
  exactly-once là **at-least-once + lũy đẳng**.
- **`correlation_id = intervention_id`** (tất định). Dedup LRU của
  `command_agent` khớp id này → reconcile gửi lại **không chạm Mininet**.
- **Dedup chỉ là tối ưu hoá; lũy đẳng mới là bảo đảm.** Agent restart làm mất
  cache LRU → lệnh chạy lại → **vô hại** vì lệnh lũy đẳng.
- **Sửa một dòng** ở `mininet/env_runner.py`: `send_command(self, cmd, cid=None)`
  và `cid = str(cid or cmd.get('cid') or uuid.uuid4())`. Caller Phase 4 không
  truyền `cid` → vẫn sinh uuid như cũ; `test_phase4_command_regression.py`
  chứng minh hai lần gọi liên tiếp vẫn ra hai cid khác nhau.
- **202 ≠ hiệu lực.** `?timeout=0` nghĩa là Ditto đã nhận thư, không phải việc đã
  xong. Xác nhận bằng **trạng thái quan sát được**:
  `command_agent.py:258 (ln.dt4n_bw)` → `collector.py:403` → `collector.py:639
  (features['capacity'])` → PATCH → SSE → `TwinReader.observed_bw()`. `capacity`
  không nằm trong 71 cột của `envelope-1.0.0` nên đọc nó không phạm N13.

## D — Thing `org.dt4n:controlloop`

Controller **cũng có thể chết**. Tổ hợp nguy hiểm:

```
detector   SỐNG, báo normal        ← trông rất ổn
controller CHẾT, đang MITIGATING   ← không ai gỡ giới hạn nữa
```

Một nhãn freshness duy nhất sẽ để detector sống **che mất** controller chết. Do
đó controlloop có `freshness` **riêng** (C9).

- **Khởi tạo `HOLD/never_started`, không bao giờ `IDLE`.** `IDLE` nghĩa là "tôi
  đang chạy và không có gì để làm"; sự thật trước lần chạy đầu là "tôi chưa từng
  chạy". Fail-safe: mặc định = giá trị **an toàn nhất**, không phải **thường gặp
  nhất**. Đã tạo thật trên Ditto (HTTP 201) qua `bridge/bootstrap.py`.
- **`holdRemainingS` / `probeRemainingS` là KHOẢNG, không phải mốc**, vì ba lý do
  độc lập: (1) đồng hồ trình duyệt không đồng bộ; (2) `time.time()` có thể nhảy
  lùi khi NTP hiệu chỉnh → "còn lại −4 giây"; (3) `time.monotonic()` **không có
  ý nghĩa liên tiến trình**. Consumer tự đếm ngược; sai số tối đa = độ trễ mạng
  (~22 ms), không phụ thuộc lệch đồng hồ.
- **Không bao giờ sinh `null`** — `check_document` quét đệ quy.

## E — Audit có chuỗi hash

Mỗi dòng chứa SHA-256 của dòng trước. Sửa một dòng → chuỗi **gãy tại dòng kế
tiếp** → `test_sua_mot_dong_thi_lo_ngay_va_dung_vi_tri` khẳng định đúng số dòng.
**Tamper-evident**, không phải tamper-proof: không ngăn được ai sửa, nhưng bảo
đảm việc sửa bị phát hiện.

Ba chi tiết dễ làm sai, cả ba có test:
1. `canonical()` phải **tất định** (`sort_keys`, `separators`) — nếu không,
   `verify_chain` báo gãy **giả**.
2. `_resume()` nối tiếp chuỗi cũ sau restart — nếu bắt đầu lại từ GENESIS thì
   chuỗi gãy đúng tại điểm restart.
3. `fsync` mỗi dòng — chaos test 8.7 sẽ giết controller đúng lúc ghi.

Xoay vòng giữ chuỗi **qua nhiều file** bằng `rotated_head_sha256`
(`test_xoay_vong_giu_chuoi_qua_nhieu_file`: 10 dòng, 4 file, chuỗi vẫn liền).

**C10 chứng minh được ngay bây giờ:** `test_c10_dung_lai_bit_exact_tu_audit` chạy
7 bước vòng đời (inject → hold → revert → probe fail → HOLD → resume → N15), ghi
audit, rồi đọc lại và gọi `decide()` — actions và `cstate_after` trùng **từng
bit**. Bốn trường `input` + `roles` + `now_mono` + `cstate_before` là **tối
thiểu**: `test_c10_gay_neu_thieu_mot_truong` cho thấy bỏ `now_mono` vẫn ra cùng
action nhưng khác `deadline_mono`.

## S11 cho `setBandwidth` — dự đoán đã KHOÁ trước khi đo

Đã ghi trong `phase8_contract.json` (`s11_predictions`), niêm phong trước khi
chạy harness:

```
quiet/log_first          : act_entries == 0                    ← GATE C8
quiet/log_late           : alarm_entries >= 1                  ← đối chứng ÂM
quiet/no_log             : act_entries >= 1                    ← đối chứng DƯƠNG
first_tick_after_inject  : unknown/missing_data                ← F8-6 (reset qdisc)
flood/during MITIGATING  : nghiêng về khả năng A (suppressed_intervention)
lease                    : không chạm (hold 20 s << 120 s)

Điều kiện VÔ HIỆU: nếu quiet/no_log = 0 act thì phép đo vô nghĩa (không phân
biệt được "write-ahead hiệu quả" với "actuator vô hại") → phải tăng nhiễu loạn,
ghi amendment, chạy lại.
```

**Vì sao hai kịch bản** (đây là chỗ tôi phải sửa kế hoạch gốc):

- Ở `bw = 7` với tải nền 2 Mbps, **7 > 2 nên không gói nào bị drop** → nhánh
  `no_log` cũng sẽ cho 0 act → đối chứng dương thất bại → **phép đo vô hiệu**.
  Nên kịch bản **quiet** bóp xuống **1 Mbps**, dưới tải nền.
  1 Mbps là tham số của **phép đo**, không phải của policy:
  `PolicyParams.limit_mbps` vẫn là 7.0 (có test).
- Kịch bản **flood** dùng đúng 7.0 với flood 47 Mbps đang chạy. Nó **không dùng
  làm gate** vì đã có `act` do flood nên không quy kết nhân quả được; nó tồn tại
  để **đóng ẩn số 9.3** của Lesson 8.2.

## Receipt

| File | Nội dung |
|---|---|
| `results/report/phase8_contract.json` | **niêm phong** `47464487…`, 18 SHA + dự đoán S11 |
| `controller/twin_reader.py` | hợp đồng A |
| `controller/intervene.py` | hợp đồng B + C |
| `bridge/controlloop_contract.py` | hợp đồng D |
| `controller/audit.py` | hợp đồng E |
| `scripts/run_phase8_s11_bw.py` | harness đo S11 (hai kịch bản, ba nhánh) |
| `test/test_phase8_contract.py` (20) · `test_phase8_twin_reader.py` (13) · `test_phase8_audit.py` (9) · `test_phase4_command_regression.py` (4) | kiểm bằng máy |
