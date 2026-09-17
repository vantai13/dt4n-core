# Phase 6R — Sensor probe vòng 2

## Vì sao có vòng 2

Luật v1 không có lớp cho cơ chế hỗn hợp nên đối chứng s2-s3 bị kết luận
`UNEXPLAINED` dù 49,1% byte thiếu được giải thích bởi leaf drop và phần còn lại
nằm trong backlog. Analyzer v1 còn cộng trùng drop của HTB cha phản chiếu từ
netem con. Luật v2 được viết sau khi đã thấy kết quả v1; vì vậy v1 được giữ
nguyên và không được chấm lại bằng luật mới.

## Mô tả từ v1 — không phải kết luận xác nhận

Mô hình chất lỏng khớp byte thiếu của s2-s3 trong khoảng 0,2%. Drop bắt đầu ở
tick 31 khi qlen đạt 1000. Với s1-s2, kích thước trung vị xấp xỉ 2,9 kB/skb,
qlen chỉ đạt 769 trước revert và backlog bị hủy khi qdisc được dựng lại. Đây là
cơ sở để lập dự đoán mới, không phải bằng chứng để chấm v2.

## Điều kiện và dự đoán đăng ký trước

Mỗi điều kiện chạy hai lần lặp độc lập. Các cửa sổ dưới đây được đóng trong
`PREDICTIONS` của analyzer v2 trước khi chạy Mininet.

| Điều kiện | Cấu hình | Dự đoán |
|---|---|---|
| C0 | s2-s3, offload on, fault 20 s | `QUEUE_THEN_DROP`; drop đầu tick 29–33; collector thấy drop |
| C1 | s1-s2, offload on, fault 40 s | drop đầu tick 40–55 khi qlen ≥ 995; collector thấy drop |
| C2 | s1-s2, offload off, fault 20 s | median ≤ 1600 byte/skb; drop đầu tick 21–40; collector thấy drop |

Luật kết luận:

- C0 không đạt: phép đo không đáng tin và không rút kết luận từ C1/C2.
- C1 đạt: `SENSOR_CORRECT_ON_S1S2`.
- C2 không đạt manipulation check: `C2_INVALID`, không được diễn giải là bác bỏ.
- C2 đạt manipulation check và drop đúng cửa sổ: `GSO_EXPLAINS_DELAYED_DROP`.
- C2 đạt manipulation check nhưng không có drop đúng cửa sổ:
  `GSO_EXPLANATION_REFUTED`.

Luật loại run chỉ kiểm tra ping có reply và link có lưu lượng ở pha pre. Luật
này nằm trong `validity()` và không được nhìn kết quả cơ chế.

## Run bị loại ở vòng 1

Các run sau không có port map runtime, controller không cài route, ping có 0
reply và được loại theo luật hợp lệ. Raw data không được dùng và không commit:

- `20260917T044727Z` — s1-s2
- `20260917T044859Z` — s2-s3
- `20260917T045029Z` — s1-s2
- `20260917T045159Z` — s2-s3

Probe v2 ghi `DT4N_PORT_MAP`, SHA-256 của port map, Python executable, yêu cầu
offload và trạng thái offload quan sát được vào meta để điều kiện chạy có thể
tái lập.

## Rủi ro khai trước cho amendment 1

Ở R-D s1-s2 với rho = 2,0, phần dư dự kiến khoảng 269 kB/s làm bể đầy sau
khoảng 11 giây; drop có thể bắt đầu gần tick 31, CUBIC giảm tốc và residual có
thể xuống dưới R trong nửa sau. Tỷ lệ tick báo động vì thế có thể sát ngưỡng
50% của P1. Đây là rủi ro đã khai trước, không phải lý do đổi P1.

## Ràng buộc

- Không sửa collector trước R-campaign.
- Không đổi threshold hoặc tham số amendment 1 từ kết quả probe v2.
- Không dùng v2 để chấm lại dữ liệu v1.
- Chỉ các run mới có `_off*_rev*` trong tên được analyzer v2 đọc.
