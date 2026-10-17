#!/usr/bin/env bash
# Tính lại excess của detector 2.1 trên 5 run giảm băng thông s1-s2 (Mục 6.2.2), so với kết quả
# đã lưu. Offline, không ghi tệp nào.
#
#   ket-qua-bao-cao/6.2.2-co-che-bo-sot-s1-s2/kiem_tra_offline.sh
source "$(dirname "$0")/../_chung.sh"
"$PY" scripts/tai_lap_bao_cao.py --muc 6.2.2
