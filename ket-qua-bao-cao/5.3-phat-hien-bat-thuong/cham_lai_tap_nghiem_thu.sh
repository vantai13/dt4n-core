#!/usr/bin/env bash
# Chấm lại detector 2.1 trên tập nghiệm thu, ghi ra tệp mới (Bảng 5.4, 5.5). Offline.
#
#   ket-qua-bao-cao/5.3-phat-hien-bat-thuong/cham_lai_tap_nghiem_thu.sh
#
# Kết quả mới ở 5.3-phat-hien-bat-thuong/chay-lai/<thời điểm>/:
#   cham-RD-RC-RN.json   giảm băng thông, flood và dịch nút cổ chai, tải cao
#   cham-RS.json         chạy nền, trên hai run đã thu (RS-soak2M-s5001-r1, RS-soak2M-s5003-r3)
# Hai tệp có cùng cấu trúc với các tệp cham-*.json trong tap-nghiem-thu/; kết luận ở content.verdicts.
#
# Dữ liệu của run RN-load8M-s5014-r2 hiện là bản thu lại, nên cham-RD-RC-RN.json ứng với
# cham-giam-bang-thong-flood-tai-cao.json cộng cham-lai-mot-run-tai-cao.json: mọi kết luận giống,
# riêng run đó có 0 giây báo động sau bộ chặn vùng tải như ở tệp chấm lại.
source "$(dirname "$0")/../_chung.sh"
R=models/detector-release-2.1.0.json
mkdir -p "$RA"
"$PY" scripts/gd4_score.py --release $R --set gd4r --groups RD RC RN --out "$RA/cham-RD-RC-RN.json"
"$PY" scripts/gd4_score.py --release $R --set gd4r --groups RS --runs RS-soak2M-s5001-r1 RS-soak2M-s5003-r3 \
  --out "$RA/cham-RS.json"
xong "So với các tệp cham-*.json trong tap-nghiem-thu/"
