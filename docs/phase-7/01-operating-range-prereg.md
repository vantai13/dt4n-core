# Phase 7.1 — Vùng vận hành hợp lệ

## 1. Câu hỏi và phép kiểm hai chiều

Envelope chỉ có thẩm quyền trong miền tải đã được train. Ngoài miền đó,
trạng thái công bố phải là `unknown(cause=out_of_operating_range)` thay vì
`normal` hoặc `act`.

Guard phải đồng thời đạt hai điều kiện:

- P1: bật trên mọi run normal 8/10 Mbps ở ít nhất 90% tick judgeable.
- P2: không bật tick nào trên các run fault RD, RC và F Phase 5.

P2 ngăn guard theo độ lớn tải che mất chính lỗi flood mà detector cần phát
hiện. Kết quả Phase 5 F đã được dùng khi chọn ứng viên nên bằng chứng đó là
in-sample; RD/RC là phép kiểm ngoài mẫu quan trọng hơn.

## 2. Đại lượng được chọn

Đại lượng đã đăng ký là:

```text
g(snapshot) = min(txRate * 8 / 1e6 của mọi host có role=client)
```

Tải hợp lệ tăng đều sẽ nâng mọi client và do đó nâng `min`. Flood một nguồn
chỉ nâng nguồn đó, nên hai client còn lại giữ `min` thấp. Các ứng viên tổng,
max và số cột gần biên bị loại vì đều có thể tăng trong fault flood.

Nếu bất kỳ client nào có `rateValid != true`, thiếu giá trị hoặc giá trị không
hữu hạn, `g=None`; không đổi dữ liệu thiếu thành 0.

## 3. Ngưỡng và hysteresis

Ngưỡng được tính duy nhất từ đủ tám run train Phase 5:

- `T = 4.312610240000001 Mbps`.
- Owner: `N-load4M-s1006-r2`, tick 51.
- Có 472 tick train, tất cả đều judgeable.
- So sánh strict: guard vào khi `g > T`.
- Guard vào sau một tick vượt ngưỡng và thoát sau ba tick liên tiếp `g <= T`.
- Ba tick tái sử dụng `fsm_params.release_m=3`, không thêm tham số mới.

Guard chỉ ghi đè trạng thái công bố sau `fsm.step`; evidence, scorer và trạng
thái FSM bên trong vẫn được giữ nguyên.

## 4. Tiêu chí và kết quả có thể xảy ra

- KN1: P1 PASS và P2 PASS — triển khai guard ở Lesson 7.3.
- KN2: P1 PASS, P2 FAIL — không triển khai vì guard che lỗi thật.
- KN3: P1 FAIL — không triển khai vì đại lượng không tách được tải hợp lệ cao.

Không thử ứng viên thứ hai sau khi nhìn kết quả.

## 5. Dự đoán đã niêm phong

Dự đoán giữ nguyên từ hướng dẫn: **KN1**. Lý do là ở 8/10 Mbps, client chậm
nhất dự kiến vẫn vượt ngưỡng train 4.31 Mbps; trong fault một nguồn, các client
còn lại giữ tải khoảng 2 Mbps.

## 6. Giới hạn và deviation

- Flood phối hợp từ mọi client có thể giống tải đều và bị guard che.
- Một client im lặng kéo `min` về 0, làm guard fail-open.
- Đại lượng phụ thuộc topology và giả định các client có cùng profile tải.
- Ngưỡng là max mẫu nên một run normal mới vẫn có thể vượt ngưỡng.
- `N-vary-s1008-r2` có h1/h3 im lặng dù check process pass; không sửa tham số
  đã đóng băng, nhưng campaign sau cần gate traffic thực tế theo từng client.

Deviation được ghi công khai trong prereg: khi kiểm tra file có còn là Git LFS
pointer hay không, ba dòng đầu của `RN-load8M-s4014-r2` đã vô tình được hiển
thị trước khi build. Thiết kế, ngưỡng và dự đoán không được thay đổi theo dữ
liệu đó, nhưng artifact không tuyên bố blind prereg tuyệt đối.

Ngoài ra, prereg chưa được commit/push trước khi probe. Hash của prereg được
probe tham chiếu giúp phát hiện sửa đổi nội dung, nhưng commit timestamp của
lần triển khai này không được dùng làm bằng chứng về thứ tự blind-prereg.

Prereg content SHA-256:
`aeefdad0e1f02189af950967c88d03d826006bfa15c38aa1d36bff30d7fb5d1a`.

## 7. Kết quả probe thực tế

Probe chạy trên dữ liệu thật cho kết quả **KN1, đúng với dự đoán**:

| Nhóm | Số run | Kết quả |
|---|---:|---|
| P1, RN 8M/10M | 4 | PASS; từng run bật 59/59 tick |
| P2, RD/RC/F | 22 | PASS; từng run bật 0/59 tick |
| Report-only RN 6M | 2 | từng run bật 59/59 tick |
| Report-only RS soak 2M | 3 | từng run bật 0/3597 tick |
| Report-only RO/C | 4 | từng run bật 0/59 tick |

Median `g` của RN 8M là 8.5784–8.5790 Mbps; RN 10M là
10.0447–10.0590 Mbps. Median `g` của các run lỗi nằm khoảng
2.1098–2.1461 Mbps, dưới ngưỡng train.

Kết quả máy đọc đầy đủ, gồm `g_values_mbps` cho từng tick, nằm tại
`results/report/phase7_operating_range_probe.json`.

Probe content SHA-256:
`a305e2cc844b99109a13b8957cd858eecec1208a427b7ab157188ef3430a8762`.
