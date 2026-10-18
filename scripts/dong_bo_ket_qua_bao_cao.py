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
    '5.3-phat-hien-bat-thuong/tap-kiem-tra-doc-lap': [
        ('results/report/gd4r_contract.json', 'cau-hinh-25-run.json'),
        ('results/report/gd4r_manifest.json', 'ma-bam-du-lieu-kiem-tra.json'),
        ('results/report/gd4_acceptance_v21.json', 'cham-giam-bang-thong-flood-tai-cao.json'),
        ('results/report/gd4_acceptance_v21_rn_retry.json', 'cham-lai-mot-run-tai-cao.json'),
        ('results/report/gd4_acceptance_v21_rs.json', 'cham-chay-nen-2-gio.json'),
    ],
    '5.3-phat-hien-bat-thuong/tieu-chi-ghi-truoc': [
        ('results/report/gd4_acceptance_prereg.json', 'muc-dat-truoc.json'),
        ('results/gd4/prereg.md', 'muc-dat-truoc.md'),
    ],
    '5.3.3-su-co-link-chi-co-tcp': [
        ('results/report/gd4_s1s2_excess.json', 'excess-5-run-s1-s2.json'),
        ('results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045444Z.analysis.json',
         'hang-doi-offload-bat-lan-1.json'),
        ('results/probe/degrade_sensor_s1-s2_f0.8275_20260917T045726Z.analysis.json',
         'hang-doi-offload-bat-lan-2.json'),
        ('results/probe/v2_report.json', 'hang-doi-3-dieu-kien.json'),
    ],
    '5.4-what-if': [
        ('results/report/gd3_whatif_validation.json', 'kiem-hoi-cuu.json'),
        ('results/gd3/blind_predictions.json', 'kiem-mu-du-doan.json'),
        ('results/gd3/blind_result.json', 'kiem-mu-ket-qua.json'),
    ],
    '5.5-mo-hinh-du-lieu-ditto': [
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
}

# ------------------------------------------------------------------ dữ liệu thô
# Dữ liệu thô của từng mục, chép NGUYÊN TÊN (tên run đã đọc được: N-load2M-s1003-r1 ...).
# Thêm ngày 17/10/2026 để thư mục kết quả tự đủ khi nộp. Bản gốc vẫn ở data/ và results/,
# vì mọi script đọc ở đó và nhiều tệp tiêu chí ghi trước ghim mã băm theo đường dẫn gốc.
def _cung_ten(folder, paths):
    MAP.setdefault(folder, []).extend((rel, Path(rel).name) for rel in paths)


def _run(dirpath, run_ids):
    return [f'{dirpath}/{r}{ext}' for r in run_ids for ext in ('.jsonl', '.meta.json')]


# Tám run huấn luyện detector 2.1: bảy run N của tập phát triển (bỏ N-vary-s1008-r2 vì máy
# khách không gửi đủ tải) và run thu lại N-vary-s1008-r4 (ml/gd4_retrain.py: load_raw('v21')).
_HUAN_LUYEN_P5 = ('N-load1M-s1001-r1', 'N-load1M-s1002-r2', 'N-load2M-s1003-r1',
                  'N-load2M-s1004-r2', 'N-load4M-s1005-r1', 'N-load4M-s1006-r2',
                  'N-vary-s1007-r1')
_cung_ten('5.3-phat-hien-bat-thuong/du-lieu/huan-luyen',
          _run('data/phase5/raw', _HUAN_LUYEN_P5) + _run('data/phase5/gd4/raw', ('N-vary-s1008-r4',)))
# Phần kiểm tra của tập phát triển: 2 run C (bình thường) và 8 run F (có sự cố). Mục 5.4
# (kiểm hồi cứu what-if) dùng chính mười run này.
_PHAT_TRIEN = ('C-load2M-s2001-r1', 'C-vary-s2002-r1',
               'F-admin_down-s1-s2-s3001-r1', 'F-admin_down-s1-s3-s3002-r1',
               'F-degrade-s1-s2-s3003-r1', 'F-degrade-s2-s3-s3004-r1',
               'F-flood-h1_to_srv1-s3005-r1', 'F-flood-h2_to_srv2-s3006-r1',
               'F-shift-s1-s2-s3007-r1', 'F-shift-s1-s3-s3008-r1')
_cung_ten('5.3-phat-hien-bat-thuong/du-lieu/tap-phat-trien', _run('data/phase5/raw', _PHAT_TRIEN))
# Tập kiểm tra độc lập: mọi run đã thu trong data/phase5/gd4r/raw (24 run).
_cung_ten('5.3-phat-hien-bat-thuong/du-lieu/tap-kiem-tra-doc-lap',
          sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'data/phase5/gd4r/raw').glob('*')
                 if p.is_file()))
# Phép thử hàng đợi của Mục 5.3.3: dữ liệu thô từng lần đo và tệp phân tích.
_cung_ten('5.3.3-su-co-link-chi-co-tcp/du-lieu-tho',
          sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'results/probe').glob('degrade_sensor_*')))
# Nhật ký controller của 16 lượt bật controller trong thí nghiệm A/B của Mục 5.7 (một dòng mỗi
# quyết định, kèm trạng thái detector mà controller đọc trên twin). Hình diễn biến vòng kín vẽ từ đây.
_cung_ten('5.7-vong-kin/du-lieu-tho/nhat-ky-controller-ab',
          sorted(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / 'logs/gd4cl_from_gcp/gd4cl_ab/20261016T103632Z').glob('ab_C_*.jsonl')))
# Mẫu twin và AWS ghi trong từng lượt thí nghiệm của Mục 5.6.
_cung_ten('5.6-tu-dong-hoa-aws/du-lieu-tho',
          sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'results/cloud').glob('samples_*.jsonl')))

# Tệp kết quả bổ sung, đặt tên đọc được như phần trên.
MAP['5.3-phat-hien-bat-thuong/tap-phat-trien'] += [
    ('results/report/experiment_matrix.json', 'thiet-ke-18-run.json'),
    ('results/report/gd2_client_traffic_audit.json', 'kiem-tra-tai-may-khach.json'),
]
MAP['5.4-what-if'] += [('results/gd3/validate.txt', 'kiem-hoi-cuu-bang-tung-run.txt')]
MAP['5.6-tu-dong-hoa-aws'] += [('logs/cloud_controller_audit.jsonl', 'nhat-ky-cloud-controller.jsonl')]
MAP['5.7-vong-kin'] += [('results/report/phase7_e2e_latency.json', 'do-tre-quan-sat-cho-bang-3.8.json')]

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
