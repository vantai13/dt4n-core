# GĐ4 — Kết quả thô của detector 2.1 (16/10/2026)

Detector 2.1 chỉ đổi dữ liệu huấn luyện so với 1.0.0. Run lỗi `N-vary-s1008-r2` được thay bằng
`N-vary-s1008-r4`, thu lại trên cùng máy GCP và qua cổng lưu lượng máy khách. Ngưỡng mới:
K = 18, E ≈ 5,61, R ≈ 0,075 (bản cũ 31 / 8,97 / 0,080). Ngưỡng bộ chặn vùng tải (4,31 Mbps)
và trần tải máy khách (6,18 Mbps) không đổi.

Cách chấm được ghi trước khi đọc dữ liệu: `results/report/gd4_acceptance_prereg.json`,
`results/gd4/deviation_1.md`, `deviation_2.md`, `deviation_3.md`. Script chấm tái lập đúng
số 6R khi chạy bản 1.0.0 trên 25 run cũ.

## 1. Tập nghiệm thu mới

Đã thu 24 run trên máy GCP:
- 2 run chạy nền 60 phút (chủ nhiệm quyết định 2 run thay vì 3);
- 6 run tải cao, 10 run giảm băng thông, 4 run flood và dịch nút cổ chai;
- 2 run controller tắt link (không chấm).

Run tải cao `RN-load8M-s5014-r2` được thu hai lần. Lần 1 có h1 và h3 = 0 Mbps suốt run,
không qua cổng lưu lượng máy khách, và được lưu trong thư mục cách ly. Lần 2 qua cổng.

### Giảm băng thông (10 run R-D), S1 và S4

| Link | ρ | Envelope | Combined (thêm residual) |
|---|---|---|---|
| s1–s2 | 0,50 | không | không |
| s1–s2 | 0,80 | không | không |
| s1–s2 | 1,25 | không | có, 11,01 s |
| s1–s2 | 1,50 | có, 20,00 s (giây 40, đúng giây gỡ sự cố) | có, 3,99 s |
| s1–s2 | 2,00 | không | có, 6,00 s |
| s2–s3 | 0,50 | không | không |
| s2–s3 | 0,80 | không | không |
| s2–s3 | 1,25 | có, 2,01 s | có, 2,01 s |
| s2–s3 | 1,50 | có, 2,00 s | có, 2,00 s |
| s2–s3 | 2,00 | có, 2,00 s | có, 2,00 s |

- S1 (envelope): 4/10 = 0,40, mục tiêu ≥ 0,875 → **không đạt**. Theo ρ: ρ ≥ 1,10 là 4/6, ρ ≤ 0,90 là 0/4.
- Combined: 6/10. Theo ρ: ρ ≥ 1,10 là 6/6, ρ ≤ 0,90 là 0/4.
- S4: thời gian phát hiện của envelope là 2,00; 2,00; 2,01; 20,00 s, trung vị 2,0 [2,0; 20,0].
  Giá trị lớn nhất 20,00 s > 3 s → **không đạt**. Lần 20,00 s rơi đúng giây gỡ sự cố.
- Combined: 2,00; 2,00; 2,01; 3,99; 6,00; 11,01 s, trung vị 3,0 [2,0; 11,0].

### Chạy nền (2 run R-S × 60 phút), S2

Không có báo động sai nào trong 2,0 giờ, ở cả kênh envelope và combined. Cũng không có giây nào
có báo động thô. Cận trên 95% là 1,5 lần mỗi giờ, mục tiêu ≤ 3 → **đạt**.

### Flood và dịch nút cổ chai (4 run R-C), chỉ mô tả

Phát hiện 4/4, ở cả hai kênh. Flood h1→srv1: 1,00 s. Flood h2→srv2: 1,00 s.
Dịch nút cổ chai s1–s2: 2,00 s. Dịch nút cổ chai s1–s3: 2,00 s.

### Tải cao (6 run R-N), S10 chỉ báo cáo

| Run | Chưa áp bộ chặn: giây báo động | Đã áp bộ chặn: giây bộ chặn bật | Đã áp bộ chặn: giây còn báo động |
|---|---|---|---|
| 6 Mbps (2 run) | 59/59 và 59/59 | 59/60 và 59/60 | 0 và 0 |
| 8 Mbps (2 run, s5014 là lần thu lại) | 59/59 và 59/59 | 59/60 và 59/60 | 0 và 0 |
| 10 Mbps (2 run) | 59/59 và 59/59 | 59/60 và 59/60 | 0 và 0 |

Lần thu đầu của s5014 (h1, h3 = 0 Mbps) cũng báo động 59/59 giây. Ở lần đó bộ chặn không bật,
vì máy khách chậm nhất gửi 0 Mbps.

### Kiểm khác
- Cổng lưu lượng máy khách: 24/24 run dùng để chấm đạt. Chỉ lần thu đầu của s5014 không đạt.
  Như vậy lỗi kiểu `s1008` lặp lại 1 lần trong 25 lần thu của đợt này.
- Bộ chặn vùng tải không bật ở run nào của R-D, R-S, R-C.

## 2. So sánh khai trước

| | S1 env | Lớn nhất | S2 | R-N 6 Mbps chưa áp bộ chặn | R-C |
|---|---|---|---|---|---|
| 1.0.0 trên 6R cũ (số đã công bố) | 0,30 | 2,01 s | 0 trong 3,0 giờ | 0 giây | 4/4 |
| 2.1 trên 6R cũ | 0,30 | 2,01 s | 0 trong 3,0 giờ | 59/59 giây | 4/4 |
| 1.0.0 trên tập mới | 0,40 | 20,00 s | 0 trong 2,0 giờ | 0 giây | 4/4 |
| 2.1 trên tập mới | 0,40 | 20,00 s | 0 trong 2,0 giờ | 59/59 giây | 4/4 |

Đổi mô hình không làm đổi S1, S2, S4 trên cả hai tập. Khác biệt duy nhất là ở tải 6 Mbps khi
chưa áp bộ chặn. Đổi tập dữ liệu thêm đúng một lần phát hiện, chính là lần ở giây gỡ sự cố.

## 3. Tập phát triển (đã mở từ trước, chỉ mô tả)

| | 1.0.0 | 2.1 |
|---|---|---|
| Excess: recall / FPR | 85,6% / 5,35% | 85,6% / 5,35% |
| Excess: báo nhầm | 23 lần, giây 41–47, cụm dài nhất 7 s | giống hệt |
| Dual: recall / FPR | 79,4% / 0,47% (2 lần, giây 41) | 79,4% / 1,16% (5 lần, giây 41–43) |
| Báo nhầm ở run bình thường hoặc trước khi tạo sự cố | 0 | 0 |
| Theo loại sự cố (excess, số giây phát hiện/40) | tắt link 40, giảm băng thông 19, flood 40, dịch 38 | giống hệt |
| Isolation Forest (72 cột, max_samples 256, q 0,01, 5 seed): recall / FPR | 0,13% / 2,4% | 0% / 0,56% |

Cụm báo nhầm sau khi gỡ vẫn dài 7 s, nên cửa sổ ức chế 8 s vẫn có cùng lý do. Isolation Forest
học trên dữ liệu sạch không tốt hơn.

## 4. Tệp kết quả
`results/report/gd4_acceptance_v21.json` (R-D, R-N lần 1, R-C), `gd4_acceptance_v21_rn_retry.json`,
`gd4_acceptance_v21_rs.json`, các tệp `..._v1_...` cho bản 1.0.0, `gd4_acceptance_v21_on_6r.json`,
`gd4_devset.json`, `gd4_retrain.json`.
