#!/usr/bin/env bash
# Đo lại độ trễ đồng bộ lên (Bảng 5.1 dòng Kịp thời, Hình 5.1). Cần testbed.
#
#   ket-qua-bao-cao/5.1-phan-chieu-trang-thai/do_lai_do_tre_dong_bo_len.sh
#
# Cùng một lần chạy còn đo độ trễ lệnh và phép thử HTTP 408 của Mục 5.2, nên kết quả mới có ở:
#   5.1-phan-chieu-trang-thai/chay-lai/<thời điểm>/do-tre-dong-bo-len.json
#   5.2-dieu-khien-tu-xa/chay-lai/<thời điểm>/do-tre-lenh.json, phan-hoi-ditto-408.json
# Launcher cũng thu một ít dữ liệu ML và chạy test bảo mật lệnh trên mạng thật; các tệp đó vào khac/.
# Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
can_testbed
chay_va_gom -- "$PY" scripts/launch_ml_preflight.py
xong
