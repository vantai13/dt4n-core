# Hình và bảng sinh tự động

Mọi hình kết quả của Chương 5 được vẽ bằng code từ tệp kết quả, không gõ tay số nào. Mỗi hình nằm
trong thư mục `hinh/` của đúng mục báo cáo, cạnh script vẽ ra nó:

| Hình trong báo cáo | Thư mục | Tệp hình | Vẽ từ |
|---|---|---|---|
| Độ trễ đồng bộ lên và độ trễ lệnh, xếp từ nhỏ tới lớn (Mục 5.1, 5.2) | `5.1-phan-chieu-trang-thai/hinh/` | `do-tre-xep-hang` | `5.1-.../do-tre-dong-bo-len.json`, `5.2-.../do-tre-lenh.json` |
| Diễn biến sự cố giảm băng thông ở hệ số tải 1,25 (Mục 5.3.3) | `5.3.3-su-co-link-chi-co-tcp/hinh/` | `dien-bien-s1-s2` | run chẩn đoán trong `5.3.3-.../du-lieu-tho/`, hai run của tập kiểm tra độc lập |
| Kiểm mù what-if, tải dự đoán so với đo được (Mục 5.4) | `5.4-what-if/hinh/` | `whatif-du-doan-vs-do` | `5.4-what-if/kiem-mu-ket-qua.json` |
| Tốc độ gửi của h3 ở từng lượt A/B (Mục 5.7) | `5.7-vong-kin/hinh/` | `ab-tung-luot` | `5.7-vong-kin/ab-bao-ve.json` |
| Diễn biến một lượt bật controller (Mục 5.7) | `5.7-vong-kin/hinh/` | `dien-bien-vong-kin` | nhật ký controller trong `5.7-.../du-lieu-tho/nhat-ky-controller-ab/` |

Mỗi hình có hai bản: `.pdf` (vector, chèn vào LaTeX) và `.png` (xem nhanh trên GitHub). Đầu tệp
`hinh/ve_hinh.py` của mỗi mục mô tả hình vẽ gì, đọc tệp nào và cách đọc hình.

Bảng kiểm mù what-if (`whatif-blind.tex`) được `receipt_to_table.py` sinh từ
`5.4-what-if/kiem-mu-ket-qua.json`. Bảng ghi mã băm của tệp nguồn ở dòng đầu.

Tệp `kieu_hinh.py` trong thư mục này chứa kiểu vẽ dùng chung (phông, màu, dấu phẩy thập phân), để
mọi hình trông thống nhất.

## Chạy

Vẽ lại hình của một mục:

```bash
ket-qua-bao-cao/5.7-vong-kin/ve_hinh.sh
```

Vẽ lại mọi hình và sinh lại bảng kiểm mù:

```bash
ket-qua-bao-cao/hinh-va-bang/ve_lai.sh
```

Hình được ghi đè vào `hinh/` của từng mục. Nếu hình đổi so với bản trong git, `git status` sẽ cho
thấy. Bảng kiểm mù ghi vào `chay-lai/<thời điểm>/` trong thư mục này.

Hình dùng phông Times New Roman nếu tìm thấy `times.ttf` trong `fonts/` hoặc `C:\Windows\Fonts`
(qua WSL), nếu không thì dùng phông serif khác.
