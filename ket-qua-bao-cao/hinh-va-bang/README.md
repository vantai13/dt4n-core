# Hình và bảng sinh tự động

Các con số trong những hình và bảng dưới đây không gõ tay, mà được vẽ hoặc sinh thẳng từ tệp kết quả.
Hai script này cũng nằm trong thư mục `scripts/` của mã nguồn báo cáo LaTeX (lệnh `make hinh`,
`make bang`).

| Script | Đầu vào | Đầu ra | Trong báo cáo |
|---|---|---|---|
| `ve_hinh_ch5.py` | `results/report/latency_up_randomized.json`, `latency_command_randomized.json` | `do-tre-xep-hang.pdf` | Hình 5.1 |
| | `results/report/gd4cl_ab.json` | `ab-tung-luot.pdf` | Hình 5.2 |
| `receipt_to_table.py` | `results/gd3/blind_result.json` | `whatif-blind.tex` | Bảng 5.6 |

## Chạy (từ gốc repo)

```bash
mkdir -p /tmp/hinh
.venv/bin/python -I ket-qua-bao-cao/hinh-va-bang/ve_hinh_ch5.py "$PWD" /tmp/hinh
python3 ket-qua-bao-cao/hinh-va-bang/receipt_to_table.py results/gd3/blind_result.json /tmp/hinh/whatif-blind.tex
```

Hình dùng phông Times New Roman nếu tìm thấy `times.ttf` trong `fonts/` hoặc `C:\Windows\Fonts`
(qua WSL), nếu không thì dùng phông mặc định của matplotlib. Bảng LaTeX ghi mã băm của tệp
nguồn ở dòng đầu, để biết bảng sinh từ phiên bản kết quả nào.
