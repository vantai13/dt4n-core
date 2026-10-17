#!/usr/bin/env python3
"""
chay_lai_vong_kin.py — Chạy lại một phần thí nghiệm vòng kín, ghi receipt vào thư mục mới.

Được gọi bởi scripts/chay_vong_kin.sh (script đó lo Ryu, sudo và dọn Mininet). Dùng đúng
code của các runner đã tạo kết quả trong báo cáo, chỉ đổi nơi ghi receipt để không đụng
results/report/ (các runner gốc từ chối ghi đè tệp đã có).

    python3 scripts/chay_lai_vong_kin.py ab <tệp receipt ra>
    python3 scripts/chay_lai_vong_kin.py c1 <tệp receipt ra>

  ab : run_gd4cl_ab.py, 8 khối x 4 lượt (Mục 5.7, A/B bảo vệ).
  c1 : run_gd4cl_c1.py với phần chuẩn bị giữa các lượt của run_gd4cl_dinh_vi.py
       (tải nền đủ trước mỗi lượt, tự khởi động lại MongoDB nếu Ditto yếu), 20 lượt.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ('ab', 'c1'):
        sys.exit(__doc__)
    which, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if which == 'ab':
        import run_gd4cl_ab as runner
        runner.OUT = out
        sys.argv = [sys.argv[0], '--blocks', '8']
        return runner.main()
    import run_gd4cl_dinh_vi as dinh_vi
    base = dinh_vi.base
    base.OUT = out
    base.run_one = dinh_vi.run_one_ready
    base.infra_check = dinh_vi.check_with_recovery
    sys.argv = [sys.argv[0]]
    return base.main()


if __name__ == '__main__':
    sys.exit(main())
