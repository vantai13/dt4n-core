#!/usr/bin/env bash
# Tính lại excess của detector 2.1 trên 5 run giảm băng thông s1-s2 (Mục 5.3.3), so với kết quả
# đã lưu. Offline, không ghi tệp nào.
#
#   ket-qua-bao-cao/5.3.3-su-co-link-chi-co-tcp/kiem_tra_offline.sh
source "$(dirname "$0")/../_chung.sh"
"$PY" scripts/tai_lap_bao_cao.py --muc 5.3.3
