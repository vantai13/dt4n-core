#!/usr/bin/env bash
# Vẽ lại mọi hình của Chương 5 và sinh lại bảng kiểm mù what-if. Offline, chạy trong khoảng một phút.
#
#   ket-qua-bao-cao/hinh-va-bang/ve_lai.sh
#
# Hình của từng mục do script trong thư mục mục đó vẽ (<mục>/ve_hinh.sh), và được ghi đè vào
# <mục>/hinh/. Bảng kiểm mù ghi vào hinh-va-bang/chay-lai/<thời điểm>/whatif-blind.tex.
source "$(dirname "$0")/../_chung.sh"
for muc in 5.1-phan-chieu-trang-thai 5.3.3-su-co-link-chi-co-tcp 5.4-what-if 5.7-vong-kin; do
  echo "== $muc"
  bash "ket-qua-bao-cao/$muc/ve_hinh.sh"
done
mkdir -p "$RA"
"$PY" ket-qua-bao-cao/hinh-va-bang/receipt_to_table.py ket-qua-bao-cao/5.4-what-if/kiem-mu-ket-qua.json "$RA/whatif-blind.tex"
echo "Bảng kiểm mù: $RA/whatif-blind.tex"
