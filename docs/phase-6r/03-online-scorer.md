# Phase 6R.3 — Online scorer và chống training-serving skew

## 1. Đính chính kế hoạch

Artifact envelope khai `feature_spec.uses_delta=false` và
`uses_rolling=false`; model không dùng `d1`. Scorer vì thế không giữ cửa sổ
feature. Trạng thái duy nhất là trạng thái giao nhận có kích thước cố định.

Phạm vi so đúng là 1062 dòng sau warmup, không phải 1054: 1054 là số dòng
được chấm, còn 8 dòng `unknown` do counter reset cũng phải khớp. Ngoài ra có
18 snapshot đầu run được trả rõ ràng là `warming_up`.

## 2. Kết quả tương đương và latency

Môi trường receipt: Python 3.13.13, NumPy 2.5.3, pandas 3.0.5, x86_64.

| Đường chạy | Tương đương batch | p50 | p99 | max | Ngân sách 50 ms |
|---|---:|---:|---:|---:|---|
| Tham chiếu dùng chung pandas (`ml.serve`) | 1062/1062 bit-exact | 43.88 ms | 54.33 ms | 66.16 ms | Không đạt |
| NumPy được bảo vệ bởi differential test (`ml.serve_fast`) | 1062/1062 bit-exact | 0.47 ms | 0.66 ms | 0.86 ms | Đạt |

Cả hai đường khớp 59/59 ở từng run và khớp tuyệt đối cho `k`,
`k_indicator`, `k_rate`, `judgeable`, `envelope_suspect`, `act`, `excess`,
`cons_judgeable`, `cons_r_max`, `cons_alarm`, status và reason của unknown.
Không dùng `allclose`.

Đường pandas được giữ làm oracle dễ đọc. Vì p99 của oracle vượt ngân sách đã
niêm phong, đường NumPy mới được phép dùng khi receipt tương đương vẫn xanh;
ngân sách không bị sửa để vừa code.

## 3. Quyết định khoảng thời gian

Khoảng hợp lệ là `[0.5, 1.5]` giây. `rxRate` và `txRate` đã được collector
chia cho thời gian, nhưng `qdiscSentDelta` và `qdiscDropDelta` là số đếm thô
trong khoảng đo. Khoảng quá dài hoặc quá ngắn có thể làm chúng lệch khỏi đại
lượng đã hiệu chỉnh.

Trên 1062 khoảng lịch sử, Δt nằm trong `[0.985199451, 1.011968613]` giây,
trung vị `1.000770092` giây. Cửa sổ đã chọn rộng hơn jitter quan sát được,
nhưng vẫn chặn khoảng đôi. Scorer không phân biệt được “consumer bỏ lỡ một
snapshot” với “collector bỏ lỡ một chu kỳ”, nên chọn bảo thủ: trả `unknown`
một tick.

## 4. Chính sách giao nhận

- `t_source` cũ hơn bị `rejected` và không đổi trạng thái chấm điểm.
- Cùng `t_source`, cùng digest nội dung trả lại đúng Reading cũ.
- Cùng `t_source`, khác nội dung là xung đột và bị từ chối.
- Snapshot đầu mỗi run là `warming_up`; mỗi run phải có scorer riêng.
- Sai `collector_version`, Δt ngoài cửa sổ hoặc feature thiếu/không hữu hạn
  đều thành `unknown`, không bao giờ thành normal.

Khóa `t_source` dùng đồng hồ tường và có thể bị ảnh hưởng nếu NTP chỉnh lùi.
Một sequence number tăng đơn điệu từ collector là hướng nâng cấp v4; vòng này
không thay collector.

## 5. Residual ở shadow mode

Amendment 1 được kiểm SHA trước khi nạp. Residual luôn được tính và ghi vào
Reading, nhưng mặc định `conservation_mode=shadow`, nên không thay đổi cờ
`suspect`. Chỉ chuyển `active` sau khi amendment 1 vượt R-D ở 6R.5.

## 6. Differential test và mutation testing

Replay dữ liệu thật chứng minh tính tương đương trên các tình huống đã xảy ra;
test tổng hợp phủ các nhánh chính sách có thể xảy ra nhưng chưa có trong raw.

| Đột biến | Replay lịch sử | Cơ chế bảo vệ |
|---|---:|---|
| Bỏ `mask_invalid_rates` | Không bắt: 1062/1062 | Test tổng hợp rateValid=false giữa run |
| Tính lại link stats từ snapshot | Bắt | Frozen stats và replay bit-exact |
| Ép rate xuống float32 | Bắt | So float bằng `==`, không dùng tolerance |
| Thu hẹp Δt xuống 0.99 s | Bắt | Status/reason cũng nằm trong phép so |

Điểm mù thứ nhất tồn tại vì `rateValid=false` trong dữ liệu lịch sử chỉ nằm ở
tick warmup đã bị gạt. Test `test_invalid_rate_flag_masks_fabricated_rate` và
phép so fast/reference trên các snapshot tổng hợp đóng nhánh này.

## 7. Giới hạn đã biết

- `t_source` chưa phải sequence number đơn điệu.
- Oracle pandas vượt ngân sách compute trên VM này; đường nhanh phụ thuộc vào
  differential test và không được thay thế oracle.
- Cổng Δt bảo thủ có thể tạo một tick unknown dù collector vẫn tính delta đúng.
- Kết quả 1062/1062 không thay thế test tổng hợp cho trạng thái chưa từng xuất
  hiện trong dữ liệu lịch sử.

Receipt máy đọc được nằm tại `results/report/phase6r_equivalence.json` và có
SHA-256 nội dung tự kiểm tra.
