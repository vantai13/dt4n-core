# 5.4 Phân tích what-if (MT2)

What-if là mô hình giải tích (cộng tải theo đường đi, so với dung lượng link), không học từ dữ liệu.

## Tệp kết quả

| Tệp | Dùng ở báo cáo | Tệp gốc |
|---|---|---|
| `kiem-hoi-cuu.json` | kiểm hồi cứu trên 10 run kiểm tra: trong vùng hợp lệ 62 chiều link, sai số tải trung vị 0,009 Mbps, lớn nhất 0,10 Mbps; ngoài vùng 18 chiều, lớn nhất 1,73 Mbps; sai số mất gói | `results/report/gd3_whatif_validation.json` |
| `kiem-mu-du-doan.json` | dự đoán của phép kiểm mù, đã commit vào git trước khi đo | `results/gd3/blind_predictions.json` |
| `kiem-mu-ket-qua.json` | chấm 10 dự đoán của hai tình huống chưa từng chạy: 10/10 trong ngưỡng; Bảng 5.6 sinh tự động từ tệp này | `results/gd3/blind_result.json` |

## Đọc tệp

| Tệp | Trường | Ý nghĩa |
|---|---|---|
| `kiem-hoi-cuu.json` | `rules` | quy tắc chấm cố định trước: nhu cầu lấy ở giây 5-19, chấm ở giây 25-39, chỉ chấm chiều link có tải từ 0,5 Mbps |
| | `summary_rates_mbps.trong`, `.ngoài`, `.giả định phá` | sai số tải theo ba vùng: `n` số chiều link, `median_abs`, `max_abs` (Mbps) |
| | `summary_loss_pp` | sai số tỉ lệ mất gói, điểm phần trăm |
| | `runs[]` | từng run: nhu cầu đọc từ twin (`inputs_mbps`), dự đoán và số đo từng chiều link (`rates`) |
| `kiem-mu-du-doan.json` | `content.cases.case1`, `.case2` | dự đoán của từng tình huống, kèm ngưỡng sai số (`content.tolerances`) |
| `kiem-mu-ket-qua.json` | `predictions_sha256`, `predictions_commit` | ràng buộc kết quả với đúng tệp dự đoán đã commit trước khi đo |
| | `cases.<tình huống>.items[]` | từng dự đoán: `pred` dự đoán, `meas` đo được, `tol` ngưỡng, `verdict` |
| | `summary` | `pass` 10 / `n` 10 |

## Chạy lại

| Script | Làm gì | Cần |
|---|---|---|
| `kiem_tra_offline.sh` | kiểm hồi cứu: so khớp với kết quả đã lưu, rồi tính lại và in bảng từng run; bản tính lại là `kiem-hoi-cuu.json` | offline |

```bash
ket-qua-bao-cao/5.4-what-if/kiem_tra_offline.sh
```

Mỗi script chạy được từ bất kỳ thư mục nào. Kết quả mới ghi vào `chay-lai/<thời điểm>/` ngay trong thư mục này, cùng tên với tệp đã lưu ở trên, nên mở hai tệp cạnh nhau là so được. Kết quả đã lưu không bị đè, kể cả khi script lỗi hay bị Ctrl-C. Bản tính lại chỉ khác bản đã lưu ở commit và thời điểm ghi (`provenance.git_head`,
`provenance.generated_at_utc`).

Phép kiểm mù không có script, vì phải làm từng bước và commit dự đoán vào git trước khi đo.

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
giảm băng thông s2-s3 xuống 1,5 Mbps. Tệp gốc `results/gd3/blind_result.json` đã có sẵn trong repo, nên muốn chạy
lại phải dời tệp cũ đi trước, hoặc làm trên một bản clone riêng.

### Trang what-if

```bash
PYTHONPATH="$PWD" python3 -m whatif.server     # mở http://127.0.0.1:8091
```
