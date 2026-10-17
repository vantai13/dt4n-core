# _chung.sh — Phần dùng chung của các script chạy lại trong ket-qua-bao-cao/. Không chạy trực tiếp.
#
# Script của một mục đặt ở ket-qua-bao-cao/<mục>/ và nạp tệp này bằng
#     source "$(dirname "$0")/../_chung.sh"
# Sau khi nạp: đang đứng ở gốc repo, có sẵn $ROOT, $PY, $MUC (tên thư mục mục), $THOI_DIEM và
# $RA (ket-qua-bao-cao/<mục>/chay-lai/<thời điểm>/, nơi ghi kết quả mới, chưa được tạo).
set -euo pipefail

MUC_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUC=${MUC_DIR#"$ROOT/ket-qua-bao-cao/"}
THOI_DIEM=$(date -u +%Y%m%dT%H%M%SZ)
RA=$MUC_DIR/chay-lai/$THOI_DIEM
PY=$ROOT/.venv/bin/python
cd "$ROOT"
export PYTHONPATH=$ROOT

[ -x "$PY" ] || {
  echo "Chưa có môi trường .venv. Từ gốc repo, chạy:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements-phase6r.lock.v2.txt"
  exit 1
}

# Kiểm máy chạy testbed được không. Hỏi mật khẩu sudo một lần ở đầu, vì các runner gọi "sudo -n".
can_testbed() {
  echo "== Kiểm môi trường testbed (có thể hỏi mật khẩu sudo)"
  sudo -v
  RYU=${DT4N_RYU:-$(command -v ryu-manager || true)}
  export DT4N_RYU=$RYU
  "$PY" scripts/kiem_tra_moi_truong.py --testbed || { echo "Sửa các mục THIẾU ở trên rồi chạy lại."; exit 1; }
  sudo -n mn -c > /dev/null 2>&1 || true
}

# Chạy một lệnh mà không đè kết quả đã lưu: tệp lệnh ghi vào các thư mục theo dõi được gom vào
# chay-lai/<thời điểm>/ của mục tương ứng, rồi bản cũ được trả về (scripts/chay_lai_muc.py).
#     chay_va_gom [--theo-doi results/report results/probe] -- <lệnh> <tham số>...
chay_va_gom() {
  "$PY" scripts/chay_lai_muc.py --muc "$MUC" --thoi-diem "$THOI_DIEM" "$@"
}

# Trả quyền sở hữu các tệp do root ghi về người chạy.
tra_quyen() {
  sudo -n chown -R "$(id -u):$(id -g)" "$@" 2> /dev/null || true
}

# In chỗ có kết quả mới. Tham số (tùy chọn): kết quả mới nên so với gì.
xong() {
  echo
  if [ -d "$RA" ]; then
    echo "Xong. Kết quả mới ở ${RA#"$ROOT/"}/"
    echo "${1:-So với kết quả đã lưu cùng tên trong ${MUC_DIR#"$ROOT/"}/}. Cách đọc từng trường ở README.md."
  else
    echo "Xong."
  fi
}
