#!/usr/bin/env bash
# Chạy lại thí nghiệm vòng kín trên testbed (Mục 5.7). Cần testbed, Ditto với MongoDB trần ít
# nhất 1 GiB.
#
#   ket-qua-bao-cao/5.7-vong-kin/do_lai_tren_testbed.sh        # A/B (khoảng 1 giờ 30 phút) rồi định vị (khoảng 40 phút)
#   ket-qua-bao-cao/5.7-vong-kin/do_lai_tren_testbed.sh ab     # chỉ A/B bảo vệ
#   ket-qua-bao-cao/5.7-vong-kin/do_lai_tren_testbed.sh c1     # chỉ phép thử định vị
#
# Kết quả mới ở 5.7-vong-kin/chay-lai/<thời điểm>/: ab-bao-ve.json, thu-dinh-vi.json, kèm nhật ký
# của Ryu và từng runner. Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
sudo -v
DT4N_RA=$RA scripts/chay_vong_kin.sh "$@"
