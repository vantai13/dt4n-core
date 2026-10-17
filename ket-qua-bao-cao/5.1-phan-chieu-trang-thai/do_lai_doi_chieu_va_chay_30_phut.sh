#!/usr/bin/env bash
# Đo lại đối chiếu thực thể, 20 lần tắt link và chạy liên tục 30 phút (Bảng 5.1 các dòng Đủ,
# Đúng, Bắt được sự kiện, Bền). Cần testbed. Hơn 30 phút.
#
#   ket-qua-bao-cao/5.1-phan-chieu-trang-thai/do_lai_doi_chieu_va_chay_30_phut.sh
#
# Cùng một lần chạy còn đo thời gian từng chặng của lệnh (Mục 5.2), nên kết quả mới có ở:
#   5.1-phan-chieu-trang-thai/chay-lai/<thời điểm>/doi-chieu-va-20-lan-tat-link.json, chay-lien-tuc-30-phut.json
#   5.2-dieu-khien-tu-xa/chay-lai/<thời điểm>/thoi-gian-tung-chang.json
# Các tệp phụ (bản đo độ trễ khóa pha cũ, test bảo mật) vào khac/. Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
can_testbed
chay_va_gom -- "$PY" scripts/run_network_suite.py
xong
