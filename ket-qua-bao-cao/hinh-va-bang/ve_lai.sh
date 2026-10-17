#!/usr/bin/env bash
# Vẽ lại Hình 5.1, Hình 5.2 và sinh lại Bảng 5.6 thẳng từ tệp kết quả. Offline.
#
#   ket-qua-bao-cao/hinh-va-bang/ve_lai.sh
#
# Kết quả ở hinh-va-bang/chay-lai/<thời điểm>/: do-tre-xep-hang.pdf, ab-tung-luot.pdf, whatif-blind.tex.
source "$(dirname "$0")/../_chung.sh"
mkdir -p "$RA"
"$PY" -I ket-qua-bao-cao/hinh-va-bang/ve_hinh_ch5.py "$ROOT" "$RA"
"$PY" ket-qua-bao-cao/hinh-va-bang/receipt_to_table.py results/gd3/blind_result.json "$RA/whatif-blind.tex"
xong "So với hình và bảng trong báo cáo (thư mục figures/ và tables/ của mã nguồn LaTeX)"
