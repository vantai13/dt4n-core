# GĐ4 — Tiêu chí nghiệm thu detector 2.1 (viết trước khi thu)

Tài liệu máy đọc: `results/report/gd4_acceptance_prereg.json` (ghim mã băm bản 2.1.0,
hợp đồng gd4r, bảng SLO 6R và code chấm).

## Đối tượng
`detector-release-2.1.0`: chỉ đổi dữ liệu train so với 1.0.0 (bỏ `N-vary-s1008-r2`,
thêm `N-vary-s1008-r4` thu lại trên máy GCP). Học lại K, E, biên, `link_stats`, R bằng
đúng code đã dựng 1.0.0. FSM, ức chế, định tuyến giữ nguyên.

## Dữ liệu
Đợt `gd4r`: 25 run, cùng thiết kế R-campaign 6R, seed +1000, thu trên máy GCP sau khi
tài liệu này được commit.

## Tiêu chí (giữ nguyên 6R)
| Chỉ tiêu | Đo trên | Mục tiêu |
|---|---|---|
| S1 tỉ lệ phát hiện sự cố giảm băng thông (envelope) | 10 run R-D | ≥ 0,875 |
| S2 báo động sai mỗi giờ, cận trên 95% | 3 run R-S × 60 phút | ≤ 3 |
| S4 thời gian phát hiện p95 (envelope) | các sự cố R-D được phát hiện | ≤ 3000 ms |
| S10 tải ngoài vùng hiệu chỉnh | 6 run R-N | chỉ báo cáo |

Mô tả, khai trước: kênh combined; S1 tách theo ρ ≥ 1,10 và ρ ≤ 0,90; bản 1.0.0 chấm
trên gd4r; bản 2.1.0 chấm trên 25 run 6R cũ.

## Cam kết
- Báo kết quả của 2.1.0 dù tốt hay xấu hơn 1.0.0.
- Script chấm phải tái lập đúng số 6R (1.0.0 trên 25 run cũ) trước khi mở gd4r.
- Chấm gd4r một lần; không chỉnh tham số sau khi mở.
- Run hỏng ở cổng thiết bị được thu lại; mọi lần thử được lưu và báo cáo.
- Không chạy lại vòng kín.
