#!/usr/bin/env bash
# Đo lại thời gian từng chặng của 60 lệnh tắt, bật link h1-s1 (Mục 5.2). Cần testbed. Hơn 30 phút.
#
#   ket-qua-bao-cao/5.2-dieu-khien-tu-xa/do_lai_thoi_gian_tung_chang.sh
#
# Đây là cùng một lần chạy với 5.1-phan-chieu-trang-thai/do_lai_doi_chieu_va_chay_30_phut.sh
# (bộ nghiệm thu mạng đo luôn cả đối chiếu và chạy liên tục 30 phút): chạy một trong hai là đủ.
# Kết quả mới có ở:
#   5.2-dieu-khien-tu-xa/chay-lai/<thời điểm>/thoi-gian-tung-chang.json
#   5.1-phan-chieu-trang-thai/chay-lai/<thời điểm>/doi-chieu-va-20-lan-tat-link.json, chay-lien-tuc-30-phut.json
# Nhật ký từng mốc thời gian của lệnh ở logs/command_flow.log. Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
can_testbed
chay_va_gom -- "$PY" scripts/run_network_suite.py
xong
