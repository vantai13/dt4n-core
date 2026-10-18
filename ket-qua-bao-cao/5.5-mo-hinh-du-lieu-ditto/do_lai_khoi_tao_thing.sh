#!/usr/bin/env bash
# Đo lại thời gian khởi tạo 52 Thing cho topology 22 host (Mục 5.5). Cần Ditto đang chạy, không
# cần Mininet. Script tạo Thing trong namespace riêng org.dt4n.scale rồi xóa hết khi xong.
#
#   ket-qua-bao-cao/5.5-mo-hinh-du-lieu-ditto/do_lai_khoi_tao_thing.sh
#
# Kết quả mới ở 5.5-mo-hinh-du-lieu-ditto/chay-lai/<thời điểm>/khoi-tao-thing-22-host.json; đặc tả
# topology 22 host sinh kèm vào khac/. Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
chay_va_gom -- "$PY" scripts/bootstrap_scale.py
xong
