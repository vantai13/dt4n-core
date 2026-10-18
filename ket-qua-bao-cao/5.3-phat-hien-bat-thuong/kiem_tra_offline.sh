#!/usr/bin/env bash
# Tính lại mọi con số của Mục 3.4 (học detector) và 5.3 từ dữ liệu thô, so với kết quả đã lưu.
# Offline, không ghi tệp nào. Khoảng 1 phút.
#
#   ket-qua-bao-cao/5.3-phat-hien-bat-thuong/kiem_tra_offline.sh
#
# In KHỚP hoặc LỆCH cho từng phần: học lại mô hình, tập phát triển, tập kiểm tra độc lập, và
# excess trên 5 run s1-s2 của Mục 5.3.3.
source "$(dirname "$0")/../_chung.sh"
"$PY" scripts/tai_lap_bao_cao.py --muc 3.4
"$PY" scripts/tai_lap_bao_cao.py --muc 5.3
