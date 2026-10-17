#!/usr/bin/env bash
# Kiểm offline luật chọn ứng viên của controller vòng kín (Mục 5.7): so khớp với kết quả đã lưu
# và chạy bộ test của luật. Không ghi tệp nào.
#
#   ket-qua-bao-cao/5.7-vong-kin/kiem_tra_offline.sh
source "$(dirname "$0")/../_chung.sh"
"$PY" scripts/tai_lap_bao_cao.py --muc 5.7
"$PY" -m pytest -q -p no:cacheprovider test/test_gd4cl.py
