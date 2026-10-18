#!/usr/bin/env python3
"""
chay_lai_muc.py — Chạy một lệnh đo hoặc phân tích mà không đè kết quả đã lưu của báo cáo.

Nhiều script ghi thẳng vào results/report/ hoặc results/probe/, đè lên kết quả của báo cáo. Công cụ
này chụp lại các thư mục đó trước khi chạy lệnh. Khi lệnh kết thúc, kể cả khi lỗi hay bị Ctrl-C:

  1. tệp mới hoặc được ghi lại (nội dung hay thời điểm sửa đổi thay đổi) được chép vào ket-qua-bao-cao/<mục>/chay-lai/<thời điểm>/. Tệp có trong
     danh sách của dong_bo_ket_qua_bao_cao.py được đặt tên đọc được và vào thư mục của đúng mục nó
     thuộc về; tệp khác vào khac/ của mục gọi lệnh, giữ tên gốc;
  2. tệp bị đổi được ghi lại nội dung cũ, tệp mới bị xóa khỏi thư mục theo dõi.

Các script chạy lại trong ket-qua-bao-cao/ gọi công cụ này; ít khi cần gọi trực tiếp:

    python3 scripts/chay_lai_muc.py --muc 5.2-dieu-khien-tu-xa --thoi-diem 20261017T120000Z \\
        [--theo-doi results/report ...] -- <lệnh> <tham số>...
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KQ = ROOT / 'ket-qua-bao-cao'
THEO_DOI_MAC_DINH = ('results/report',)


def ban_do_ten():
    """tệp gốc (tương đối so với ROOT) -> (thư mục mục, tên bản sao)."""
    spec = importlib.util.spec_from_file_location(
        'dong_bo', ROOT / 'scripts' / 'dong_bo_ket_qua_bao_cao.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Một tệp gốc có thể được chép tới hai chỗ (bản tên dễ đọc và bản trong du-lieu-tho/).
    # Giữ chỗ được khai báo trước, là bản tên dễ đọc.
    ten = {}
    for folder, pairs in mod.MAP.items():
        for src, name in pairs:
            ten.setdefault(src, (folder, name))
    return ten


def chup(dirs):
    """Mọi tệp trong các thư mục theo dõi: đường dẫn tương đối -> (bytes, mtime_ns).

    Giữ cả thời điểm sửa đổi để nhận ra tệp được lệnh ghi lại với nội dung y hệt (ví dụ phân tích
    lại cho đúng kết quả cũ): tệp đó vẫn phải có mặt trong thư mục chạy lại.
    """
    anh = {}
    for d in dirs:
        for p in sorted((ROOT / d).rglob('*')):
            if p.is_file():
                anh[p.relative_to(ROOT).as_posix()] = (p.read_bytes(), p.stat().st_mtime_ns)
    return anh


def ghi_lai(path: Path, data: bytes):
    try:
        path.write_bytes(data)
    except PermissionError:
        # tệp do root ghi: không sửa được tại chỗ, nhưng thư mục là của người chạy nên xóa rồi tạo lại
        path.unlink()
        path.write_bytes(data)


def _sigterm(*_):
    raise KeyboardInterrupt


def chay_lenh(cmd):
    proc = subprocess.Popen(cmd, cwd=ROOT)
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            # Ctrl-C cũng tới tiến trình con (cùng nhóm); chờ nó tự dừng rồi mới dọn
            print('\n[chay_lai_muc] nhận Ctrl-C, chờ lệnh dừng rồi trả kết quả cũ về...', flush=True)
            try:
                return proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.terminate()
            except KeyboardInterrupt:
                proc.terminate()


def gom_va_tra_lai(truoc, sau, muc, thoi_diem, ten):
    da_gom, khong_tra_duoc = [], []
    doi = [k for k in sau if k in truoc and sau[k] != truoc[k]]
    moi = [k for k in sau if k not in truoc]
    mat = [k for k in truoc if k not in sau]
    for rel in doi + moi:
        if rel in ten:
            folder, name = ten[rel]
            dst = KQ / folder / 'chay-lai' / thoi_diem / name
        else:
            dst = KQ / muc / 'chay-lai' / thoi_diem / 'khac' / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(sau[rel][0])
        da_gom.append((rel, dst, rel in truoc))
    for rel in doi + mat:
        try:
            p = ROOT / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            ghi_lai(p, truoc[rel][0])
            os.utime(p, ns=(truoc[rel][1], truoc[rel][1]))
        except OSError as e:
            khong_tra_duoc.append((rel, e))
    for rel in moi:
        try:
            (ROOT / rel).unlink()
        except OSError as e:
            khong_tra_duoc.append((rel, e))
    return da_gom, mat, khong_tra_duoc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--muc', required=True, help='thư mục mục trong ket-qua-bao-cao/, ví dụ 5.2-dieu-khien-tu-xa')
    ap.add_argument('--thoi-diem', help='tên thư mục chạy lại, mặc định là thời điểm UTC hiện tại')
    ap.add_argument('--theo-doi', nargs='+', default=list(THEO_DOI_MAC_DINH),
                    help='thư mục có thể bị lệnh ghi vào (tương đối so với gốc repo)')
    ap.add_argument('lenh', nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    cmd = args.lenh[1:] if args.lenh[:1] == ['--'] else args.lenh
    if not cmd:
        ap.error('thiếu lệnh sau --')
    if not (KQ / args.muc).is_dir():
        ap.error('không có thư mục ket-qua-bao-cao/%s' % args.muc)
    thoi_diem = args.thoi_diem or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ten = ban_do_ten()

    truoc = chup(args.theo_doi)
    signal.signal(signal.SIGTERM, _sigterm)
    print('[chay_lai_muc] đã chụp %d tệp trong %s; chạy: %s' % (
        len(truoc), ', '.join(args.theo_doi), ' '.join(cmd)), flush=True)
    rc = 1
    try:
        rc = chay_lenh(cmd)
    finally:
        sau = chup(args.theo_doi)
        da_gom, mat, loi = gom_va_tra_lai(truoc, sau, args.muc, thoi_diem, ten)
        print('\n[chay_lai_muc] lệnh kết thúc, mã thoát %s' % rc)
        if not da_gom:
            print('  lệnh không ghi tệp nào vào %s' % ', '.join(args.theo_doi))
        for rel, dst, co_san in da_gom:
            if co_san:
                cung = (ROOT / rel).read_bytes() == dst.read_bytes()
                ghi_chu = 'giống từng byte kết quả đã lưu' if cung else 'khác kết quả đã lưu'
            else:
                ghi_chu = 'tệp mới'
            print('  %s\n      -> %s  (%s)' % (rel, dst.relative_to(ROOT), ghi_chu))
        for rel in mat:
            print('  lệnh đã xóa %s, đã ghi lại bản cũ' % rel)
        for rel, e in loi:
            print('  KHÔNG trả lại được %s: %s' % (rel, e))
        if da_gom or mat:
            print('  Kết quả đã lưu trong %s đã được trả về như trước khi chạy.' % ', '.join(args.theo_doi))
    return 1 if loi else rc


if __name__ == '__main__':
    sys.exit(main())
