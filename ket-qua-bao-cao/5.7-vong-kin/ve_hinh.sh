#!/usr/bin/env bash
# Vẽ lại hình của mục này từ các tệp kết quả đã lưu. Offline, chạy trong vài giây.
#
#   ket-qua-bao-cao/<mục>/ve_hinh.sh
#
# Hình được ghi đè vào thư mục hinh/ bên cạnh: bản .pdf để chèn vào LaTeX, bản .png để xem nhanh.
# Mọi số trong hình đọc thẳng từ tệp kết quả, không gõ tay. Cách vẽ từng hình mô tả ở đầu
# hinh/ve_hinh.py. Nếu hình đổi so với bản trong git, `git diff --stat` sẽ cho thấy.
source "$(dirname "$0")/../_chung.sh"
"$PY" "$MUC_DIR/hinh/ve_hinh.py"
