#!/usr/bin/env bash
# Kiểm hồi cứu what-if (Mục 5.4): so khớp với kết quả đã lưu, rồi tính lại và in bảng đầy đủ
# từng run. Offline.
#
# Bản tính lại ở 5.4-what-if/chay-lai/<thời điểm>/kiem-hoi-cuu.json. Kết quả đã lưu không bị đè.
#
#   ket-qua-bao-cao/5.4-what-if/kiem_tra_offline.sh
#
# Phép kiểm mù cần testbed và phải làm từng bước bằng tay, xem README.md.
source "$(dirname "$0")/../_chung.sh"
"$PY" scripts/tai_lap_bao_cao.py --muc 5.4
chay_va_gom -- "$PY" -m whatif.validate
xong
