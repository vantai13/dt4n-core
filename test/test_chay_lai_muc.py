#!/usr/bin/env python3
"""
test_chay_lai_muc.py — scripts/chay_lai_muc.py không được để lệnh chạy lại đè kết quả đã lưu.

  1. tệp có trong danh sách bị đổi -> bản mới vào chay-lai/ của đúng mục, tên đọc được; bản cũ trả về;
  2. tệp mới ngoài danh sách -> vào khac/ của mục gọi lệnh, bị xóa khỏi thư mục theo dõi;
  3. tệp bị xóa -> được ghi lại;
  4. lệnh lỗi -> vẫn trả bản cũ về, mã thoát của lệnh được giữ;
  5. lệnh không ghi gì -> không tạo thư mục chạy lại;
  6. lệnh ghi lại tệp với nội dung y hệt -> tệp vẫn có trong thư mục chạy lại.

    python3 -m pytest -q test/test_chay_lai_muc.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cl(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('chay_lai_muc', ROOT / 'scripts' / 'chay_lai_muc.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / 'results/report').mkdir(parents=True)
    (tmp_path / 'ket-qua-bao-cao/5.1-a').mkdir(parents=True)
    (tmp_path / 'ket-qua-bao-cao/5.2-b').mkdir(parents=True)
    (tmp_path / 'results/report/x.json').write_text('cu-x')
    (tmp_path / 'results/report/y.json').write_text('cu-y')
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    monkeypatch.setattr(mod, 'KQ', tmp_path / 'ket-qua-bao-cao')
    monkeypatch.setattr(mod, 'ban_do_ten', lambda: {
        'results/report/x.json': ('5.1-a', 'ten-doc-duoc-x.json'),
        'results/report/y.json': ('5.2-b', 'ten-doc-duoc-y.json'),
    })
    return mod, tmp_path


def run(mod, code, muc='5.2-b'):
    return mod.main(['--muc', muc, '--thoi-diem', 'T', '--', sys.executable, '-c', code])


def test_doi_tep_trong_danh_sach_gom_dung_muc_va_tra_lai(cl):
    mod, root = cl
    rc = run(mod, "open('results/report/x.json','w').write('moi-x')")
    assert rc == 0
    assert (root / 'results/report/x.json').read_text() == 'cu-x'
    assert (root / 'ket-qua-bao-cao/5.1-a/chay-lai/T/ten-doc-duoc-x.json').read_text() == 'moi-x'
    assert not (root / 'ket-qua-bao-cao/5.2-b/chay-lai/T/ten-doc-duoc-x.json').exists()


def test_tep_moi_ngoai_danh_sach_vao_khac_va_bi_xoa(cl):
    mod, root = cl
    run(mod, "open('results/report/z.json','w').write('z')")
    assert not (root / 'results/report/z.json').exists()
    assert (root / 'ket-qua-bao-cao/5.2-b/chay-lai/T/khac/results/report/z.json').read_text() == 'z'


def test_tep_bi_xoa_duoc_ghi_lai(cl):
    mod, root = cl
    run(mod, "import os; os.remove('results/report/y.json')")
    assert (root / 'results/report/y.json').read_text() == 'cu-y'


def test_lenh_loi_van_tra_lai_va_giu_ma_thoat(cl):
    mod, root = cl
    rc = run(mod, "open('results/report/y.json','w').write('do-dang'); raise SystemExit(3)")
    assert rc == 3
    assert (root / 'results/report/y.json').read_text() == 'cu-y'
    assert (root / 'ket-qua-bao-cao/5.2-b/chay-lai/T/ten-doc-duoc-y.json').read_text() == 'do-dang'


def test_lenh_khong_ghi_gi_khong_tao_thu_muc(cl):
    mod, root = cl
    assert run(mod, "print('khong ghi')") == 0
    assert not (root / 'ket-qua-bao-cao/5.2-b/chay-lai').exists()


def test_ghi_lai_noi_dung_y_het_van_duoc_gom(cl):
    mod, root = cl
    import os
    os.utime(root / 'results/report/x.json', ns=(1, 1))
    run(mod, "open('results/report/x.json','w').write('cu-x')")
    assert (root / 'ket-qua-bao-cao/5.1-a/chay-lai/T/ten-doc-duoc-x.json').read_text() == 'cu-x'
    assert (root / 'results/report/x.json').stat().st_mtime_ns == 1


def test_ban_do_ten_that_khop_danh_sach_dong_bo():
    spec = importlib.util.spec_from_file_location('chay_lai_muc', ROOT / 'scripts' / 'chay_lai_muc.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ten = mod.ban_do_ten()
    assert ten['results/report/command_flow.json'] == ('5.2-dieu-khien-tu-xa', 'thoi-gian-tung-chang.json')
    # Mỗi tệp gốc có đúng một tên đích; tệp chép tới hai chỗ lấy tên dễ đọc.
    spec2 = importlib.util.spec_from_file_location('dong_bo', ROOT / 'scripts' / 'dong_bo_ket_qua_bao_cao.py')
    dong_bo = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(dong_bo)
    nguon = {src for pairs in dong_bo.MAP.values() for src, _ in pairs}
    assert set(ten) == nguon
    assert ten['results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.analysis.json'] == (
        '5.3.3-su-co-link-chi-co-tcp', 'hang-doi-offload-bat-lan-1.json')
