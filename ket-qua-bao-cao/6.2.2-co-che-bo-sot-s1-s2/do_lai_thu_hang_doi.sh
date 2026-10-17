#!/usr/bin/env bash
# Đo lại phép thử hàng đợi trên testbed (Mục 6.2.2). Cần testbed (Mininet chạy dưới quyền root).
# Bốn điều kiện, mỗi điều kiện hai lần như dữ liệu gốc; mỗi lần chạy 60 s, sự cố từ giây 20.
#
#   ket-qua-bao-cao/6.2.2-co-che-bo-sot-s1-s2/do_lai_thu_hang_doi.sh
#
#   s1-s2, offload bật, gỡ ở giây 40    như hang-doi-offload-bat-lan-*.json
#   s1-s2, tắt offload, gỡ ở giây 40    điều kiện C2 của hang-doi-3-dieu-kien.json
#   s1-s2, offload bật, gỡ ở giây 60    điều kiện C1 (sự cố kéo dài 40 s)
#   s2-s3, offload bật, gỡ ở giây 40    điều kiện C0 (đối chứng, link chỉ có UDP)
#
# Kết quả ở 6.2.2-co-che-bo-sot-s1-s2/chay-lai/<thời điểm>/: dữ liệu thô từng lần (.jsonl,
# .meta.json, .ping.log), tệp phân tích từng lần (.analysis.json, .analysis_v2.json) và bảng tổng
# hợp ba điều kiện hang-doi-3-dieu-kien.json. Kết quả đã lưu không bị đè.
source "$(dirname "$0")/../_chung.sh"
can_testbed
mkdir -p "$RA"
do_mot_lan() {
  sudo -n env PYTHONPATH="$ROOT" /usr/bin/python3 scripts/probe_degrade_sensor.py --out "$RA" "$@"
  sudo -n mn -c > /dev/null 2>&1 || true
}
for lan in 1 2; do
  echo "== Lần $lan"
  do_mot_lan --link s1-s2 --factor 0.8275
  do_mot_lan --link s1-s2 --factor 0.8275 --offload off
  do_mot_lan --link s1-s2 --factor 0.8275 --revert 60
  do_mot_lan --link s2-s3 --factor 0.8203
done
tra_quyen "$RA"

# Phân tích lượt 1: hai lần offload bật trên s1-s2.
for f in "$RA"/degrade_sensor_s1-s2_f0.8275_offon_rev40_*.jsonl; do
  "$PY" scripts/analyze_degrade_sensor_probe.py "$f"
done
# Phân tích lượt 2: ba điều kiện C0, C1, C2. Script ghi bảng tổng hợp vào results/probe/v2_report.json,
# nên chạy qua chay_va_gom để bảng mới vào thư mục chạy lại và bản đã lưu được giữ nguyên.
chay_va_gom --theo-doi results/probe -- "$PY" scripts/analyze_degrade_sensor_probe_v2.py \
  "$RA"/degrade_sensor_s2-s3_f0.8203_offon_rev40_*.jsonl \
  "$RA"/degrade_sensor_s1-s2_f0.8275_offon_rev60_*.jsonl \
  "$RA"/degrade_sensor_s1-s2_f0.8275_offoff_rev40_*.jsonl
xong
