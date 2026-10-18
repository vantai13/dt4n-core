#!/usr/bin/env bash
# Tính lại mọi con số offline của báo cáo và kiểm bản sao trong ket-qua-bao-cao/ còn khớp tệp gốc.
# Không cần Mininet, Ditto hay AWS, không ghi tệp nào. Khoảng 1 phút.
#
#   ket-qua-bao-cao/kiem_tra_tat_ca.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || { echo "Chưa có .venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-phase6r.lock.v2.txt"; exit 1; }
export PYTHONPATH=$PWD
"$PY" scripts/tai_lap_bao_cao.py
"$PY" scripts/dong_bo_ket_qua_bao_cao.py --check
"$PY" scripts/xuat_csv_du_lieu.py --check
