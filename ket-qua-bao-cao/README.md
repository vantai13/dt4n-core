# Kết quả theo từng mục của báo cáo

Mỗi thư mục con ứng với một mục trong Chương 5 và 6 của báo cáo. Trong mỗi thư mục có:

- bản sao các tệp kết quả của mục đó (tệp gốc vẫn ở `results/`, `models/`, nơi các script ghi ra);
- `README.md` nói tệp nào cho ra bảng hay hình nào, và lệnh để chạy lại.

## Ba mức chạy lại

| Mức | Cần gì | Dùng cho |
|---|---|---|
| Offline | môi trường `.venv` (xem [README chính](../README.md#tải-về-và-cài-đặt)) | chấm điểm detector, học lại mô hình, what-if hồi cứu, các phân tích |
| Testbed | Linux có root, Mininet, Open vSwitch, Ryu, Ditto chạy bằng Docker | đo độ trễ, thu dữ liệu, kiểm mù what-if, vòng kín |
| AWS | thêm tài khoản AWS (có chi phí) | tự động hóa đám mây |

## Kiểm nhanh mọi con số offline

```bash
export PYTHONPATH="$PWD"
.venv/bin/python scripts/tai_lap_bao_cao.py            # mọi mục, khoảng 1 phút
.venv/bin/python scripts/tai_lap_bao_cao.py --muc 5.3  # chỉ một mục
```

Script không ghi đè tệp nào. Nó tính lại từ dữ liệu thô bằng đúng code đã dùng, rồi so khớp tuyệt
đối với tệp kết quả đã lưu, và in `KHỚP` hoặc `LỆCH` cho từng mục.

## Bản đồ mục báo cáo

| Mục báo cáo | Thư mục | Nội dung | Mức chạy lại |
|---|---|---|---|
| 5.1 Phản chiếu trạng thái mạng (ND1) | [5.1-phan-chieu-trang-thai](5.1-phan-chieu-trang-thai/) | đối chiếu thực thể, 20 lần tắt link, độ trễ đồng bộ, chạy 30 phút | testbed |
| 5.2 Điều khiển từ xa (ND2) | [5.2-dieu-khien-tu-xa](5.2-dieu-khien-tu-xa/) | độ trễ lệnh, thời gian từng chặng, HTTP 408 | testbed |
| 5.3 Phát hiện bất thường (ND2) | [5.3-phat-hien-bat-thuong](5.3-phat-hien-bat-thuong/) | mô hình, tập phát triển, tập nghiệm thu, tiêu chí ghi trước | offline (chấm), testbed (thu dữ liệu) |
| 5.4 Phân tích what-if (MT2) | [5.4-what-if](5.4-what-if/) | kiểm hồi cứu, kiểm mù | offline, testbed |
| 5.5 Kiến trúc với Ditto (ND3) | [5.5-kien-truc-ditto](5.5-kien-truc-ditto/) | khởi tạo 52 Thing cho topology 22 host | cần Ditto |
| 5.6 Tự động hóa với AWS (ND4) | [5.6-tu-dong-hoa-aws](5.6-tu-dong-hoa-aws/) | ba kịch bản lặp, đối chứng, cân bằng tải | testbed và AWS |
| 5.7 Vòng kín (mở rộng) | [5.7-vong-kin](5.7-vong-kin/) | A/B bảo vệ, phép thử định vị | testbed |
| 6.2.2 Sự cố trên link chỉ có TCP | [6.2.2-co-che-bo-sot-s1-s2](6.2.2-co-che-bo-sot-s1-s2/) | excess trên 5 run giảm băng thông s1-s2, phép thử hàng đợi | offline, testbed |
| Hình và bảng tự sinh | [hinh-va-bang](hinh-va-bang/) | script vẽ hình độ trễ, hình A/B, bảng kiểm mù | offline |

## Giữ bản sao khớp với tệp gốc

Danh sách tệp của từng thư mục nằm ở `scripts/dong_bo_ket_qua_bao_cao.py`.

```bash
python3 scripts/dong_bo_ket_qua_bao_cao.py --check   # báo bản sao nào đã lệch
python3 scripts/dong_bo_ket_qua_bao_cao.py           # chép lại từ tệp gốc
```

## Hai lưu ý khi chạy lại

- Script ghi một lần. Các script tạo kết quả từ chối ghi đè tệp đã có, để kết quả cũ không bị
  thay ngầm. Muốn chạy lại thì dùng `tai_lap_bao_cao.py` (không ghi), hoặc truyền đường dẫn ra
  mới nếu script có tùy chọn `--out`.
- Hợp đồng thu dữ liệu ghi tên máy. Các chiến dịch thu của GĐ4 (`gd4`, `gd4r`) chỉ chạy trên
  máy `dt4n-research-01`, máy đã thu toàn bộ dữ liệu. Muốn thu lại trên máy khác, tạo hợp đồng
  mới theo mẫu `ml/gd4rcampaign.py` với tên máy mới, rồi chấm bằng `scripts/gd4_score.py`.
