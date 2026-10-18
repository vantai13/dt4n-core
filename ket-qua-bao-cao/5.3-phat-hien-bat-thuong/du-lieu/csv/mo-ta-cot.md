# Mô tả cột của các tệp CSV

Sinh tự động bởi `scripts/xuat_csv_du_lieu.py`. Mỗi dòng là một giây của một run. Ô trống là
không đo được (ví dụ giây khởi động, hoặc bộ đếm vừa bị đặt lại), không phải 0.

## Cột thông tin

| Cột | Ý nghĩa |
|---|---|
| `run_id` | tên run, trùng tên tệp `.jsonl` trong `../huan-luyen/`, `../tap-phat-trien/`, `../tap-kiem-tra-doc-lap/` |
| `nhom` | N, C: bình thường. F: có sự cố (tập phát triển). RD giảm băng thông, RC flood và dịch nút cổ chai, RN tải cao, RS chạy nền 60 phút, RO tắt link bằng controller (không dùng trong báo cáo) |
| `loai_su_co`, `vi_tri_su_co` | loại và vị trí sự cố, trống nếu run không có sự cố |
| `tai_mbps` | tải mỗi máy khách, Mbps, hoặc "thay đổi" nếu tải đổi theo lịch |
| `tick` | giây thứ mấy trong run, bắt đầu từ 0 |
| `nhan` | 1 nếu giây đó nằm trong khoảng có sự cố (sau giây tạo, tới hết giây gỡ), 0 nếu không |
| `khoi_dong` | 1 ở giây đầu, khi chưa tính được tốc độ. Mô hình bỏ các giây này khi học |

## 71 cột detector dùng

Đơn vị: tốc độ tính bằng byte/s, đổi sang Mbps thì nhân 8 rồi chia 10^6.

| Cột | Nhóm | Ý nghĩa | Đơn vị |
|---|---|---|---|
| `agg.links_down` | chỉ báo | số link đang tắt | link |
| `agg.loss_max` | chỉ báo | tỉ lệ mất gói lớn nhất trong 8 link | % |
| `agg.loss_n_above_alert` | chỉ báo | số link có tỉ lệ mất gói trên 1% | link |
| `agg.rate_absz_max` | tốc độ | độ lệch lớn nhất của các cột tốc độ link so với trung bình huấn luyện, tính theo số lần độ lệch chuẩn |  |
| `agg.rate_absz_n_above_3` | tốc độ | số cột tốc độ link lệch quá 3 lần độ lệch chuẩn | cột |
| `host-h1.status.state_up` | chỉ báo | trạng thái bật, tắt của host-h1 | 1 = up, 0 = down |
| `host-h1.traffic.rxRate` | tốc độ | tốc độ nhận của host-h1 | byte/s |
| `host-h1.traffic.txRate` | tốc độ | tốc độ gửi của host-h1 | byte/s |
| `host-h2.status.state_up` | chỉ báo | trạng thái bật, tắt của host-h2 | 1 = up, 0 = down |
| `host-h2.traffic.rxRate` | tốc độ | tốc độ nhận của host-h2 | byte/s |
| `host-h2.traffic.txRate` | tốc độ | tốc độ gửi của host-h2 | byte/s |
| `host-h3.status.state_up` | chỉ báo | trạng thái bật, tắt của host-h3 | 1 = up, 0 = down |
| `host-h3.traffic.rxRate` | tốc độ | tốc độ nhận của host-h3 | byte/s |
| `host-h3.traffic.txRate` | tốc độ | tốc độ gửi của host-h3 | byte/s |
| `host-srv1.status.state_up` | chỉ báo | trạng thái bật, tắt của host-srv1 | 1 = up, 0 = down |
| `host-srv1.traffic.rxRate` | tốc độ | tốc độ nhận của host-srv1 | byte/s |
| `host-srv1.traffic.txRate` | tốc độ | tốc độ gửi của host-srv1 | byte/s |
| `host-srv2.status.state_up` | chỉ báo | trạng thái bật, tắt của host-srv2 | 1 = up, 0 = down |
| `host-srv2.traffic.rxRate` | tốc độ | tốc độ nhận của host-srv2 | byte/s |
| `host-srv2.traffic.txRate` | tốc độ | tốc độ gửi của host-srv2 | byte/s |
| `link-h1-s1.status.state_up` | chỉ báo | trạng thái bật, tắt của link-h1-s1 | 1 = up, 0 = down |
| `link-h1-s1.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-h1-s1 | % |
| `link-h1-s1.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-h1-s1 | gói/giây |
| `link-h1-s1.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-h1-s1 | gói/giây |
| `link-h1-s1.traffic.rxRate` | tốc độ | tốc độ nhận của link-h1-s1 | byte/s |
| `link-h1-s1.traffic.txRate` | tốc độ | tốc độ gửi của link-h1-s1 | byte/s |
| `link-h2-s1.status.state_up` | chỉ báo | trạng thái bật, tắt của link-h2-s1 | 1 = up, 0 = down |
| `link-h2-s1.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-h2-s1 | % |
| `link-h2-s1.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-h2-s1 | gói/giây |
| `link-h2-s1.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-h2-s1 | gói/giây |
| `link-h2-s1.traffic.rxRate` | tốc độ | tốc độ nhận của link-h2-s1 | byte/s |
| `link-h2-s1.traffic.txRate` | tốc độ | tốc độ gửi của link-h2-s1 | byte/s |
| `link-h3-s1.status.state_up` | chỉ báo | trạng thái bật, tắt của link-h3-s1 | 1 = up, 0 = down |
| `link-h3-s1.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-h3-s1 | % |
| `link-h3-s1.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-h3-s1 | gói/giây |
| `link-h3-s1.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-h3-s1 | gói/giây |
| `link-h3-s1.traffic.rxRate` | tốc độ | tốc độ nhận của link-h3-s1 | byte/s |
| `link-h3-s1.traffic.txRate` | tốc độ | tốc độ gửi của link-h3-s1 | byte/s |
| `link-s1-s2.status.state_up` | chỉ báo | trạng thái bật, tắt của link-s1-s2 | 1 = up, 0 = down |
| `link-s1-s2.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-s1-s2 | % |
| `link-s1-s2.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-s1-s2 | gói/giây |
| `link-s1-s2.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-s1-s2 | gói/giây |
| `link-s1-s2.traffic.rxRate` | tốc độ | tốc độ nhận của link-s1-s2 | byte/s |
| `link-s1-s2.traffic.txRate` | tốc độ | tốc độ gửi của link-s1-s2 | byte/s |
| `link-s1-s3.status.state_up` | chỉ báo | trạng thái bật, tắt của link-s1-s3 | 1 = up, 0 = down |
| `link-s1-s3.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-s1-s3 | % |
| `link-s1-s3.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-s1-s3 | gói/giây |
| `link-s1-s3.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-s1-s3 | gói/giây |
| `link-s1-s3.traffic.rxRate` | tốc độ | tốc độ nhận của link-s1-s3 | byte/s |
| `link-s1-s3.traffic.txRate` | tốc độ | tốc độ gửi của link-s1-s3 | byte/s |
| `link-s2-s3.status.state_up` | chỉ báo | trạng thái bật, tắt của link-s2-s3 | 1 = up, 0 = down |
| `link-s2-s3.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-s2-s3 | % |
| `link-s2-s3.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-s2-s3 | gói/giây |
| `link-s2-s3.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-s2-s3 | gói/giây |
| `link-s2-s3.traffic.rxRate` | tốc độ | tốc độ nhận của link-s2-s3 | byte/s |
| `link-s2-s3.traffic.txRate` | tốc độ | tốc độ gửi của link-s2-s3 | byte/s |
| `link-s2-srv1.status.state_up` | chỉ báo | trạng thái bật, tắt của link-s2-srv1 | 1 = up, 0 = down |
| `link-s2-srv1.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-s2-srv1 | % |
| `link-s2-srv1.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-s2-srv1 | gói/giây |
| `link-s2-srv1.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-s2-srv1 | gói/giây |
| `link-s2-srv1.traffic.rxRate` | tốc độ | tốc độ nhận của link-s2-srv1 | byte/s |
| `link-s2-srv1.traffic.txRate` | tốc độ | tốc độ gửi của link-s2-srv1 | byte/s |
| `link-s3-srv2.status.state_up` | chỉ báo | trạng thái bật, tắt của link-s3-srv2 | 1 = up, 0 = down |
| `link-s3-srv2.traffic.lossPct` | chỉ báo | tỉ lệ gói bị bỏ ở hàng đợi, cả hai chiều link của link-s3-srv2 | % |
| `link-s3-srv2.traffic.qdiscDropDelta` | chỉ báo | số gói bị bỏ ở hàng đợi trong giây đó, cả hai chiều link của link-s3-srv2 | gói/giây |
| `link-s3-srv2.traffic.qdiscSentDelta` | tốc độ | số gói đã gửi qua hàng đợi trong giây đó, cả hai chiều link của link-s3-srv2 | gói/giây |
| `link-s3-srv2.traffic.rxRate` | tốc độ | tốc độ nhận của link-s3-srv2 | byte/s |
| `link-s3-srv2.traffic.txRate` | tốc độ | tốc độ gửi của link-s3-srv2 | byte/s |
| `switch-s1.status.state_up` | chỉ báo | trạng thái bật, tắt của switch-s1 | 1 = up, 0 = down |
| `switch-s2.status.state_up` | chỉ báo | trạng thái bật, tắt của switch-s2 | 1 = up, 0 = down |
| `switch-s3.status.state_up` | chỉ báo | trạng thái bật, tắt của switch-s3 | 1 = up, 0 = down |

## Cột thêm

| Cột | Ý nghĩa |
|---|---|
| `residual.r_max` | residual lớn nhất trên ba switch của kênh bảo toàn lưu lượng (Mục 3.4.3), (vào - ra) / max(vào, 10^4 byte/s) |
