#!/usr/bin/env bash
# chay_vong_kin.sh — Chạy lại thí nghiệm vòng kín của Mục 5.7 bằng một lệnh.
#
#   scripts/chay_vong_kin.sh            # A/B (khoảng 1 giờ 30 phút) rồi phép thử định vị (khoảng 40 phút)
#   scripts/chay_vong_kin.sh ab         # chỉ A/B
#   scripts/chay_vong_kin.sh c1         # chỉ phép thử định vị
#
# Cần: Ditto đang chạy (ditto/docker-compose.yml của repo), Mininet, Open vSwitch, iperf,
# Ryu (đặt DT4N_RYU nếu ryu-manager không nằm trong PATH), sudo không hỏi mật khẩu.
# Script tự kiểm môi trường, tự dọn Mininet và bật Ryu riêng cho từng runner (mn -c dừng
# luôn Ryu, nên Ryu phải được bật lại trước mỗi runner), và ghi receipt vào
# logs/chay_lai_vong_kin/<thời điểm>/ để không đụng results/report/.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
PHAN=${1:-tat-ca}
case "$PHAN" in ab|c1|tat-ca) ;; *) echo "Dùng: $0 [ab|c1]"; exit 2;; esac
PY=$ROOT/.venv/bin/python
[ -x "$PY" ] || { echo "Chưa có .venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-phase6r.lock.v2.txt"; exit 1; }
export PYTHONPATH=$ROOT
RYU=${DT4N_RYU:-$(command -v ryu-manager || true)}
export DT4N_RYU=$RYU

"$PY" scripts/kiem_tra_moi_truong.py --testbed || { echo "Sửa các mục THIẾU ở trên rồi chạy lại."; exit 1; }

OUT=$ROOT/logs/chay_lai_vong_kin/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
RYU_PID=""

bat_ryu() {
  sudo -n mn -c > "$OUT/mn_c_$1.log" 2>&1 || true
  sudo -n rm -f ditto/port_map.json
  setsid "$RYU" mininet.controller_static --ofp-tcp-listen-port 6653 > "$OUT/ryu_$1.log" 2>&1 < /dev/null &
  RYU_PID=$!
  for _ in $(seq 1 100); do
    if (exec 3<>/dev/tcp/127.0.0.1/6653) 2>/dev/null; then return 0; fi
    sleep 0.2
  done
  echo "Ryu không lên, xem $OUT/ryu_$1.log"; exit 1
}

tat_ryu() {
  [ -n "$RYU_PID" ] && kill "$RYU_PID" 2>/dev/null || true
  RYU_PID=""
  sudo -n mn -c > /dev/null 2>&1 || true
  sudo -n chown -R "$(id -u):$(id -g)" "$OUT" logs ditto 2>/dev/null || true
}
trap tat_ryu EXIT

chay() {
  echo "== $1: bắt đầu $(date -u +%H:%M:%S) UTC, nhật ký $OUT/$1.out"
  bat_ryu "$1"
  sudo -n -E env PYTHONPATH="$ROOT" "$PY" -u scripts/chay_lai_vong_kin.py "$1" "$OUT/gd4cl_$1.json" \
    > "$OUT/$1.out" 2>&1 || echo "$1 kết thúc với lỗi, xem $OUT/$1.out"
  tat_ryu
  grep -E "^(bảo vệ|primary|theo kịch bản|sai mục tiêu)" "$OUT/$1.out" || true
}

if [ "$PHAN" != c1 ]; then chay ab; fi
if [ "$PHAN" != ab ]; then chay c1; fi
echo "Xong. Receipt mới ở $OUT, so với results/report/gd4cl_ab.json và gd4cl_c1.json."
