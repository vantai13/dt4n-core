#!/usr/bin/env bash
# Phân tích lại phép thử hàng đợi từ dữ liệu thô đã lưu trong results/probe/ (Mục 5.3.3). Offline.
#
#   ket-qua-bao-cao/5.3.3-su-co-link-chi-co-tcp/phan_tich_lai_hang_doi.sh
#
# Kết quả mới ở 5.3.3-su-co-link-chi-co-tcp/chay-lai/<thời điểm>/:
#   hang-doi-offload-bat-lan-1.json, hang-doi-offload-bat-lan-2.json, hang-doi-3-dieu-kien.json
# và các tệp phân tích phụ trong khac/. Chạy bằng Python khác bản 3.13 đã dùng khi thu, kết quả
# chỉ khác kết quả đã lưu ở chữ số thập phân cuối và dòng ghi phiên bản Python.
source "$(dirname "$0")/../_chung.sh"
P=results/probe
chay_va_gom --theo-doi $P -- "$PY" scripts/analyze_degrade_sensor_probe.py $P/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.jsonl
chay_va_gom --theo-doi $P -- "$PY" scripts/analyze_degrade_sensor_probe.py $P/degrade_sensor_s1-s2_f0.8275_20260917T045726Z.jsonl
chay_va_gom --theo-doi $P -- "$PY" scripts/analyze_degrade_sensor_probe_v2.py $P/degrade_sensor_*_off*_rev*_*.jsonl
xong
