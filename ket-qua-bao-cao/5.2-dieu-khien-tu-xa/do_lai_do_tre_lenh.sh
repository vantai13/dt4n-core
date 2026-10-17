#!/usr/bin/env bash
# Đo lại độ trễ lệnh (Mục 5.2, Hình 5.1) và phép thử HTTP 408 (Mục 3.3.3). Cần testbed.
#
#   ket-qua-bao-cao/5.2-dieu-khien-tu-xa/do_lai_do_tre_lenh.sh
#
# Đây là cùng một lần chạy với 5.1-phan-chieu-trang-thai/do_lai_do_tre_dong_bo_len.sh: chạy một
# trong hai là đủ. Kết quả mới có ở:
#   5.2-dieu-khien-tu-xa/chay-lai/<thời điểm>/do-tre-lenh.json, phan-hoi-ditto-408.json
#   5.1-phan-chieu-trang-thai/chay-lai/<thời điểm>/do-tre-dong-bo-len.json
# Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
can_testbed
chay_va_gom -- "$PY" scripts/launch_ml_preflight.py
xong
