#!/usr/bin/env python3
"""
dong_bo_ket_qua_bao_cao.py — Chép các tệp kết quả vào ket-qua-bao-cao/, theo mục của báo cáo.

Danh sách ánh xạ dưới đây là nơi DUY NHẤT ghi tệp nào thuộc mục nào, và tên đọc được của nó.
Tệp gốc vẫn nằm ở chỗ cũ, với tên cũ (results/, models/, ...), vì các script đọc và ghi ở đó
và nhiều tệp tiêu chí ghi trước đã ghim mã băm theo đường dẫn gốc. Bản trong ket-qua-bao-cao/
là bản sao y nguyên từng byte, chỉ khác tên, để người đọc báo cáo tìm nhanh.

Lệnh --check báo bản sao nào thiếu, lệch so với tệp gốc, hoặc thừa (tệp nằm trong một thư mục
của danh sách nhưng không có trong danh sách, ví dụ bản sao mang tên cũ).

    python3 scripts/dong_bo_ket_qua_bao_cao.py           # chép (ghi đè bản sao)
    python3 scripts/dong_bo_ket_qua_bao_cao.py --check   # chỉ kiểm, mã thoát 1 nếu thiếu, lệch, thừa
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'ket-qua-bao-cao'

# thư mục trong ket-qua-bao-cao/ -> [(tệp gốc, tên bản sao)]
MAP = {
    '5.1-phan-chieu-trang-thai': [
        ('results/report/verification.json', 'doi-chieu-va-20-lan-tat-link.json'),
        ('results/report/latency_up_randomized.json', 'do-tre-dong-bo-len.json'),
        ('results/report/soak_30min.json', 'chay-lien-tuc-30-phut.json'),
    ],
    '5.2-dieu-khien-tu-xa': [
        ('results/report/latency_command_randomized.json', 'do-tre-lenh.json'),
        ('results/report/command_flow.json', 'thoi-gian-tung-chang.json'),
        ('results/report/command_ack_timeout3.json', 'phan-hoi-ditto-408.json'),
    ],
    '5.3-phat-hien-bat-thuong/mo-hinh': [
        ('models/envelope-2.1.0.json', 'envelope-2.1.0.json'),
        ('models/detector-release-2.1.0.json', 'detector-release-2.1.0.json'),
        ('results/report/gd4_conservation.json', 'bang-bao-toan-residual.json'),
        ('results/report/gd4_retrain.json', 'bien-ban-hoc-lai.json'),
        ('results/report/gd4_manifest.json', 'ma-bam-du-lieu-huan-luyen.json'),
    ],
    '5.3-phat-hien-bat-thuong/tap-phat-trien': [
        ('results/report/gd4_devset.json', 'excess-dual-va-iforest.json'),
    ],
    '5.3-phat-hien-bat-thuong/tap-nghiem-thu': [
        ('results/report/gd4r_contract.json', 'cau-hinh-25-run.json'),
        ('results/report/gd4r_manifest.json', 'ma-bam-du-lieu-nghiem-thu.json'),
        ('results/report/gd4_acceptance_v21.json', 'cham-giam-bang-thong-flood-tai-cao.json'),
        ('results/report/gd4_acceptance_v21_rn_retry.json', 'cham-lai-mot-run-tai-cao.json'),
        ('results/report/gd4_acceptance_v21_rs.json', 'cham-chay-nen-2-gio.json'),
    ],
    '5.3-phat-hien-bat-thuong/tieu-chi-ghi-truoc': [
        ('results/report/gd4_acceptance_prereg.json', 'tieu-chi-nghiem-thu.json'),
        ('results/gd4/prereg.md', 'tieu-chi-nghiem-thu.md'),
    ],
    '5.4-what-if': [
        ('results/report/gd3_whatif_validation.json', 'kiem-hoi-cuu.json'),
        ('results/gd3/blind_predictions.json', 'kiem-mu-du-doan.json'),
        ('results/gd3/blind_result.json', 'kiem-mu-ket-qua.json'),
    ],
    '5.5-kien-truc-ditto': [
        ('results/report/bootstrap_scale.json', 'khoi-tao-thing-22-host.json'),
    ],
    '5.6-tu-dong-hoa-aws': [
        ('results/cloud/gd1_trials.jsonl', 'tung-luot.jsonl'),
        ('results/cloud/gd1_receipt.json', 'tong-hop-theo-kich-ban.json'),
    ],
    '5.7-vong-kin': [
        ('results/report/gd4cl_prereg.json', 'tieu-chi-ghi-truoc.json'),
        ('results/report/gd4cl_offline_check.json', 'kiem-offline-luat-chon.json'),
        ('results/report/gd4cl_ab.json', 'ab-bao-ve.json'),
        ('results/report/gd4cl_c1.json', 'thu-dinh-vi.json'),
    ],
    '6.2.2-co-che-bo-sot-s1-s2': [
        ('results/report/gd4_s1s2_excess.json', 'excess-5-run-s1-s2.json'),
        ('results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.analysis.json',
         'hang-doi-offload-bat-lan-1.json'),
        ('results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045726Z.analysis.json',
         'hang-doi-offload-bat-lan-2.json'),
        ('results/probe/v2_report.json', 'hang-doi-3-dieu-kien.json'),
    ],
}

# Tệp không phải bản sao kết quả, được phép nằm trong các thư mục trên: README và script chạy lại.
KHONG_PHAI_BAN_SAO = {'README.md'}
DUOI_KHONG_PHAI_BAN_SAO = {'.sh'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    bad, missing, extra = [], [], []
    for folder, pairs in MAP.items():
        names = {name for _, name in pairs}
        for p in sorted((DEST / folder).glob('*')):
            if (p.is_file() and p.name not in names and p.name not in KHONG_PHAI_BAN_SAO
                    and p.suffix not in DUOI_KHONG_PHAI_BAN_SAO):
                extra.append(str(p.relative_to(ROOT)))
        for rel, name in pairs:
            src = ROOT / rel
            dst = DEST / folder / name
            if not src.exists():
                missing.append(rel)
                continue
            if args.check:
                if not dst.exists() or sha(dst) != sha(src):
                    bad.append(str(dst.relative_to(ROOT)))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    for rel in missing:
        print('THIẾU tệp gốc: %s' % rel)
    for rel in bad:
        print('LỆCH so với tệp gốc: %s' % rel)
    for rel in extra:
        print('THỪA (không có trong danh sách): %s' % rel)
    n = sum(len(v) for v in MAP.values())
    print('%d tệp trong danh sách, %d thiếu, %d lệch, %d thừa%s' % (
        n, len(missing), len(bad), len(extra), '' if args.check else ' (đã chép)'))
    return 1 if (bad or extra or (args.check and missing)) else 0


if __name__ == '__main__':
    sys.exit(main())
