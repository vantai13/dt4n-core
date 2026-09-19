# Phase 7.6 — Ổn định live, race S11, contention và soak

## 0. Hiệu chỉnh Phase 7.5 bằng v2

Bản v1 được giữ nguyên. `phase7_e2e_latency_v2.json` chỉ thay hai trường chẩn
đoán qua `supersedes_field_only`; dữ liệu gốc và verdict không đổi. Lỗi v1 là
lấy `(tA-tick trước)/span`, trong khi chính `net_lock` kéo dài `span`, và một
tick có thể nằm trong `(tA,tB]`. Vì thế pha bị nén về 0 và span 2 s bị diễn giải
sai thành mất tick. Pha danh nghĩa v2 là `(tA-tick trước) mod 1 s`, cho phân bố
quý `[4,11,3,7]`; ba trial 4, 11, 24 có tick trong cửa sổ lệnh.

Đây là sửa định nghĩa hợp lệ vì verdict không đổi, dữ liệu thô không đổi, lý do
kiểm chứng độc lập từ vòng lặp Collector, và v1 vẫn tồn tại. Một sửa đổi làm số
đẹp hơn nhưng không thỏa cả bốn điều kiện sẽ là chỉnh hậu nghiệm và không được
phép.

Khi sắp `phys_obs` theo offset, snapshot đầu bắt được khi flood chiếm hơn khoảng
50–58% chu kỳ. Offset 0.053/0.082 cho 615/583 ms; offset 0.162/0.233 trượt
snapshot đầu và cho 1502/1433 ms. Rate trung bình chu kỳ làm loãng flood mới,
trong khi envelope cần nhiều cột cùng vượt biên.

## 1. S11: ba nhánh và verdict

Thí nghiệm dùng admin-down s1-s2 hoặc s1-s3, mỗi rep có thứ tự ngẫu nhiên:

- `log_first`: ghi InterventionLog trước rồi POST lệnh — treatment đúng WAL.
- `log_late`: POST, đợi detector đã chấm hậu quả rồi mới ghi — đối chứng âm.
- `no_log`: POST không ghi — chứng minh hành động thực sự có thể gây act.

Phát lại offline đã cho: `log_first` khoảng 21 tick suppressed và 0 act;
`log_late` một alarm nhưng 0 act; `no_log` một lần vào act. Kết quả live sẽ
được điền từ `phase7_s11_live.json` sau khi commit dự đoán.

## 2. Race và debounce

Chỉ POST rồi ghi ngay sau đó không ép được race vì command-agent xử lý bất đồng
bộ. Nhánh `log_late` đợi một tick hậu quả đã được detector đọc, tạo quan hệ
happens-before tất định. `n_act=2` là bộ đệm: một tick chưa suppress có thể tạo
suspect, rồi log tới trước tick kế tiếp reset bộ đếm, nên dự kiến không vào act.
Điều này không thay thế quy tắc bắt buộc “ghi trước, làm sau”.

## 3. Lease và fail noisy

Can thiệp mở chỉ suppress tối đa `MAX_OPEN_S=120`. Sau expiry, gate yêu cầu
`stale_intervention` xuất hiện trong 2 s và không còn tick suppressed. Published
có thể vẫn `normal` vì dữ liệu train s1008 chứa luồng chết hoàn toàn ở biên dưới
envelope bằng 0; gate không đòi alarm quay lại. Dashboard đã được sửa để cause
khác rỗng không bao giờ được tuyên bố “All systems normal”.

## 4. Residual trong can thiệp

Residual/conservation không bị InterventionLog suppress theo amendment 8. Báo
cáo riêng đếm `residual_only` và `held` trong các nhánh `log_first`; S11 yêu cầu
không có lần vào act do các tick này.

## 5. Contention ABBA và S5

Thiết kế ON, OFF, OFF, ON giữ nguyên Mininet, sync-agent, command-agent, Ditto và
Chromium; OFF vẫn chạy cùng Collector nhưng callback rỗng. So sánh gồm p95
`cycle_scan_ms`, nhịp tick, gap, CPU process và log overrun. S5 đo đúng
`observe()+step()` và lấy p95 của block ON xấu nhất để so với 50 ms và số offline
6R 0.943 ms.

## 6. Soak và dự đoán khóa trước live

| Chỉ số | Dự đoán trước live |
|---|---:|
| `log_first` act entries | 0/4 |
| `log_first` suppressed | khoảng 20 tick/lần |
| residual-only p50 / max | 0 / ≤2 tick |
| `log_late` alarm / act | khoảng 1 / 0 mỗi lần |
| `no_log` có act | ít nhất 3/4 lần |
| lease stale sau expiry | ≤1 tick; published có thể normal |
| S5 live p95 | 1–3 ms, dưới 50 ms |
| chênh p95 cycle scan ON–OFF | <5 ms |
| tick trễ / gap | khoảng 0 ở cả hai |
| CPU ON−OFF | +0.3–1 điểm phần trăm |
| ΔRSS sau 30 phút | <1 MiB; slope nửa sau gần 0 |
| ERROR/CRITICAL | 0 |

Soak lấy RSS hiện tại từ `/proc/self/statm`, bắt đầu sau warmup, lấy mẫu 30 s,
đo slope nửa sau và kiểm tra UI vẫn FRESH. Bảng live S11, ABBA và soak sẽ được
cập nhật sau ba campaign chạy tuần tự.

## 7. Giới hạn

- Suppression so sánh wall clock; controller và collector phải cùng máy hoặc có
  nguồn thời gian đồng bộ không step trong can thiệp.
- InterventionLog hiện là bộ nhớ cùng process, không phải IPC đa tiến trình và
  không được thiết kế cho nhiều writer.
- RSS là của process tích hợp gồm detector, collector và đối tượng Mininet.
- Journal MongoDB/Ditto có thể tăng dài hạn; 30 phút không đủ kết luận.
- S11 chỉ thử một loại hành động admin-down trên hai link backbone.
