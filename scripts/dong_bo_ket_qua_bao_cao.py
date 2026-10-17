#!/usr/bin/env python3
"""
dong_bo_ket_qua_bao_cao.py — Chép các tệp kết quả vào ket-qua-bao-cao/, theo mục của báo cáo.

Danh sách ánh xạ dưới đây là nơi DUY NHẤT ghi tệp nào thuộc mục nào. Tệp gốc vẫn nằm ở
chỗ cũ (results/, models/, ...) vì các script đọc và ghi ở đó; bản trong ket-qua-bao-cao/ chỉ
để người đọc báo cáo tìm nhanh. Lệnh --check báo bản sao nào đã lệch so với tệp gốc.

    python3 scripts/dong_bo_ket_qua_bao_cao.py           # chép (ghi đè bản sao)
    python3 scripts/dong_bo_ket_qua_bao_cao.py --check   # chỉ kiểm, mã thoát 1 nếu lệch
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'ket-qua-bao-cao'

MAP = {
    '5.1-phan-chieu-trang-thai': [
        'results/report/verification.json',
        'results/report/latency_up_randomized.json',
        'results/report/soak_30min.json',
    ],
    '5.2-dieu-khien-tu-xa': [
        'results/report/latency_command_randomized.json',
        'results/report/command_flow.json',
        'results/report/command_ack_timeout3.json',
    ],
    '5.3-phat-hien-bat-thuong/mo-hinh': [
        'models/envelope-2.1.0.json',
        'models/detector-release-2.1.0.json',
        'results/report/gd4_conservation.json',
        'results/report/gd4_retrain.json',
        'results/report/gd4_manifest.json',
    ],
    '5.3-phat-hien-bat-thuong/tap-phat-trien': [
        'results/report/gd4_devset.json',
    ],
    '5.3-phat-hien-bat-thuong/tap-nghiem-thu': [
        'results/report/gd4r_contract.json',
        'results/report/gd4r_manifest.json',
        'results/report/gd4_acceptance_v21.json',
        'results/report/gd4_acceptance_v21_rn_retry.json',
        'results/report/gd4_acceptance_v21_rs.json',
    ],
    '5.3-phat-hien-bat-thuong/tieu-chi-ghi-truoc': [
        'results/report/gd4_acceptance_prereg.json',
        'results/gd4/prereg.md',
    ],
    '5.4-what-if': [
        'results/report/gd3_whatif_validation.json',
        'results/gd3/blind_predictions.json',
        'results/gd3/blind_result.json',
    ],
    '5.5-kien-truc-ditto': [
        'results/report/bootstrap_scale.json',
    ],
    '5.6-tu-dong-hoa-aws': [
        'results/cloud/gd1_trials.jsonl',
        'results/cloud/gd1_receipt.json',
    ],
    '5.7-vong-kin': [
        'results/report/gd4cl_prereg.json',
        'results/report/gd4cl_offline_check.json',
        'results/report/gd4cl_ab.json',
        'results/report/gd4cl_c1.json',
    ],
    '6.2.2-co-che-bo-sot-s1-s2': [
        'results/report/gd4_s1s2_excess.json',
        'results/probe/v2_report.json',
        'results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.analysis.json',
        'results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045726Z.analysis.json',
    ],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    bad, missing = [], []
    for folder, sources in MAP.items():
        for rel in sources:
            src = ROOT / rel
            dst = DEST / folder / src.name
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
    n = sum(len(v) for v in MAP.values())
    print('%d tệp trong danh sách, %d thiếu, %d lệch%s' % (
        n, len(missing), len(bad), '' if args.check else ' (đã chép)'))
    return 1 if (bad or (args.check and missing)) else 0


if __name__ == '__main__':
    sys.exit(main())
