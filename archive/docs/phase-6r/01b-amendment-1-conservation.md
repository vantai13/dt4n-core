# Phase 6R — Amendment 1: tầng residual bảo toàn lưu lượng

Artifact: `results/report/phase6r_amendment_1.json`  
`content_sha256`: `15bd6a96793d7b1a262435d0073b343acded6e01bb4ce9053ecea6048d611929`  
Commit niêm phong: `16736db38dd90c07fe3af8013d0e58eecbdf640f`

## 1. Nguồn gốc và điều đã biết

Ý tưởng residual sinh từ phân tích post-hoc run `F-degrade-s1-s2`; tập test đó
đã tiêu. Tóm tắt residual của cả 10 run test cũng đã được xem. Dự đoán nháp rằng
residual bắt admin-down nhưng không bắt shift đã sai: admin-down gần như không
phản ứng, còn shift phản ứng rất mạnh. Vì vậy chỉ họ degrade trên R-D chưa thu
được dùng để kiểm chứng. Admin-down, flood và shift chỉ được báo cáo mô tả.

## 2. Định nghĩa

Với mỗi switch `S`:

`r(S) = (Σin(S) - Σout(S)) / max(Σin(S), 10,000 byte/s)`

Hướng link lấy từ `twin.link_direction.UPSTREAM_OF_CORE`, không suy từ tên cột.
Counter trên interface upstream có `txRate` theo chiều upstream→downstream và
`rxRate` theo chiều ngược lại. Thứ tự link/cột được sort để phép cộng tất định.

Alarm một phía và strict: `judgeable AND r_max > R`. Thiếu bất kỳ counter cần
thiết nào làm residual unknown, không được fill zero hay gọi normal. Floor dùng
lại floor rate của envelope, không tạo tham số mới.

Failure mode đã biết: một counter link sai có thể tạo chữ ký cặp âm/dương ở hai
switch kề nhau và làm switch bên dương báo nhầm. Đây là dấu hiệu lỗi đo cần ghi
trong reason sau này, chưa phải một luật lọc mới trong amendment.

## 3. Ngưỡng R chỉ từ train

```text
R = 0.0796613817054327
owner.run_id = N-vary-s1008-r2
owner.tick = 6
owner.switch = s1
owner.config_id = normal_varying|vary
n_train_rows = 472
rule-of-three upper bound = 3/472 ≈ 0.00636 per tick
```

Residual là thống kê row-local: mỗi hàng chỉ dùng chính hàng đó và topology đã
đóng băng, không có tham số được fit. Vì vậy LOCO và in-sample tạo cùng residual.
Ngưỡng R vẫn do dòng train xấu nhất quyết định nên owner được công bố.

## 4. Dự đoán P1–P3 theo ρ

`ρ = offered_load / degraded_capacity`, trong đó offered load là median txRate
tick 2–20 của chính run R-D.

- P1: mọi run `ρ ≥ 1.10` phải được phát hiện ở ít nhất 50% tick dương.
- P2: mọi run `ρ ≤ 0.90` phải im lặng.
- P3: trên tick alarm, `argmax_switch` phải là upstream của link degrade.
- Không dự đoán trong dải `(0.90, 1.10)`.

## 5. Điều kiện bác bỏ và quyết định

- F1: dưới 75% run P1 đạt → bác cơ chế saturation.
- F2: bất kỳ run `ρ≤0.90` bị phát hiện → bác specificity cơ chế.
- F3: alarm trên hơn 2% tick nền R-D → bác tính dùng được.
- F4: định vị đúng dưới 90% tick alarm → bỏ tuyên bố định vị.
- F5: không có tick dương nào residual bắt thêm so với excess → không thêm.
- F6: kết hợp làm vi phạm S2 trên R-S → không thêm.

Nếu tất cả đạt, phát hành `conservation-1.0.0` và suspect bằng excess OR
residual; act giữ nguyên. Nếu chỉ F4 fail thì giữ phát hiện nhưng bỏ định vị. Nếu
F1/F2/F3/F5/F6 fail thì giữ `envelope-1.0.0` và báo cáo kết quả âm.

## 6. Sửa thiết kế R-D

Thiết kế 6R.1 dùng factor `{0.95,0.90,0.80,0.60,0.40}`. Do
`LinkDegrade` kẹp capacity tối thiểu 1 Mbps, ba factor đầu của link s2-s3 là
cùng một liều. Lỗi được suy từ code trước R-campaign.

Factor mới được suy theo các mục tiêu `ρ={2.0,1.5,1.25,0.8,0.5}`:

| Link | Factors đã đăng ký |
|---|---|
| s1-s2 | 0.8925, 0.8567, 0.8280, 0.7312, 0.5700 |
| s2-s3 | 0.7843, 0.7124, 0.6549, 0.4608, 0.1373 |

Số run, links, seed policy, inject/revert, load 2M và dose axis separation giữ
nguyên. ρ thực vẫn phải đo từ tick 2–20 của từng run.

## 7. Điều amendment này không quyết định

- Không đổi E/K, bounds hoặc act của envelope.
- Không sửa collector trước R-campaign.
- Không dùng R-set để hiệu chỉnh tham số.
- Không tuyên bố kiểm chứng cho admin-down, flood hoặc shift.
- Không phân biệt residual do drop với residual do backlog hàng đợi.
