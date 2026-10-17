# 5.4 Phân tích what-if (MT2)

What-if là mô hình giải tích (cộng tải theo đường đi, so với dung lượng link), không học từ dữ liệu.

## Tệp kết quả

| Tệp | Dùng ở báo cáo |
|---|---|
| `gd3_whatif_validation.json` | kiểm hồi cứu trên 10 run kiểm tra: trong vùng hợp lệ 62 chiều link, sai số tải trung vị 0,009 Mbps, lớn nhất 0,10 Mbps; ngoài vùng 18 chiều, lớn nhất 1,73 Mbps; sai số mất gói |
| `blind_predictions.json` | dự đoán của phép kiểm mù, đã commit vào git trước khi đo |
| `blind_result.json` | chấm 10 dự đoán của hai tình huống chưa từng chạy: 10/10 trong ngưỡng; Bảng 5.6 sinh tự động từ tệp này |

## Chạy lại

### Kiểm hồi cứu (offline)

```bash
PYTHONPATH="$PWD" .venv/bin/python scripts/tai_lap_bao_cao.py --muc 5.4   # so khớp, không ghi
PYTHONPATH="$PWD" .venv/bin/python -m whatif.validate                      # in bảng đầy đủ
```

### Kiểm mù (cần testbed, Ditto và Sync Agent đang chạy)

Thứ tự dưới đây do code ép: `measure` từ chối chạy nếu tệp dự đoán chưa được commit hoặc đã bị
sửa sau khi commit.

```bash
export PYTHONPATH="$PWD"
python3 -m whatif.blind predict                     # đọc twin lúc mạng bình thường, ghi dự đoán
git add results/gd3/blind_predictions.json && git commit -m "dự đoán mù"
python3 -m whatif.blind measure case1               # in lệnh iperf để gõ ở mininet>, lấy mẫu twin 70 s
python3 -m whatif.blind measure case2               # tự gửi setBandwidth s2-s3 = 1,5 Mbps, rồi trả về 5 Mbps
python3 -m whatif.blind score                       # ghi results/gd3/blind_result.json
```

Hai tình huống: `case1` flood UDP srv2 → srv1 8 Mbps (ngược chiều qua nút cổ chai), `case2`
giảm băng thông s2-s3 xuống 1,5 Mbps. Tệp `blind_result.json` đã có sẵn trong repo, nên muốn chạy
lại phải dời tệp cũ đi trước, hoặc làm trên một bản clone riêng.

### Trang what-if

```bash
PYTHONPATH="$PWD" python3 -m whatif.server     # mở http://127.0.0.1:8091
```
