#!/usr/bin/env python3
"""
build_gd4cl_prereg.py — Ghi luật, thiết kế và tiêu chí của thí nghiệm vòng kín, trước khi chạy.

    python3 scripts/build_gd4cl_prereg.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / 'results/report/gd4cl_prereg.json'
CODE = ('scripts/gd4cl_common.py', 'scripts/run_gd4cl_ab.py', 'scripts/run_gd4cl_c1.py',
        'scripts/phase8_ab_common.py', 'scripts/run_phase8_c1_control.py',
        'scripts/phase7_live_common.py', 'controller/localize.py', 'controller/policy.py',
        'controller/runner.py', 'controller/twin_reader.py', 'bridge/detector_runner.py',
        'measurements/ab_stats.py')


def _content_sha(rel: str) -> str:
    return json.loads((C.ROOT / rel).read_text(encoding='utf-8'))['content_sha256']


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    prov = C.collection_provenance(C.ROOT)
    if prov['source_dirty']:
        raise SystemExit('Commit trước khi ghi tiêu chí: %s' % prov['source_dirty_files'])
    closure = json.loads((C.ROOT / 'results/report/phase8_closure_prereg.json').read_text())
    offline = json.loads((C.ROOT / 'results/report/gd4cl_offline_check.json').read_text())
    content = {
        'prereg_id': 'DT4N-GD4-CLOSED-LOOP-PREREG',
        'purpose': ('Chạy lại vòng kín của Phase 8 với detector-release-2.1.0. Với bản 2.1, '
                    'khi h1 flood thì h3 (máy bị hại) cũng vào evidence.affected, nên luật chọn '
                    'cũ "đúng một máy khách" đứng yên hoặc chọn nhầm. Thêm một luật chọn '
                    'ứng viên theo chiều, đơn giản nhất có thể.'),
        'rule': ('Máy khách trong evidence.affected chỉ được giữ khi txRate của nó trên twin '
                 'cao hơn biên trên txRate của chính nó trong envelope-2.1.0 (h1 5,376; h2 5,413; '
                 'h3 6,182 Mbps). Thiếu số đo hoặc rateValid sai thì bỏ. Thực thể khác giữ '
                 'nguyên. Luật chọn của controller không đổi: đúng một ứng viên thì hành động.'),
        'implementation': ('scripts/gd4cl_common.py qua tham số view_provider có sẵn của '
                           'ControlRunner; controller/*.py không sửa.'),
        'release': {'file': 'models/detector-release-2.1.0.json',
                    'content_sha256': _content_sha('models/detector-release-2.1.0.json')},
        'code_sha256': {p: C.sha256_file(C.ROOT / p) for p in CODE},
        'design_same_as_phase8': {
            'ab': ('8 khối x 4 lượt, thứ tự từ seed 20260920 như Phase 8; nhánh C (controller '
                   'với luật mới) thay cho A; h1 flood UDP 47 Mbps tới srv1 trong 120 s; biến '
                   'chính tốc độ gửi trung bình của h3 trong [t_flood + 2, t_flood + 122]'),
            'localization': ('4 kịch bản của phase8_closure_prereg.json -> E1_c1_control, 5 '
                             'lượt mỗi kịch bản, flood 60 s, thứ tự từ seed 20260921 như Phase 8'),
            'phase8_closure_prereg_sha256': closure['content_sha256'],
        },
        'criteria_same_as_phase8': {
            'protection': ('cận dưới khoảng tin cậy 95% của trung bình hiệu theo khối (C - B) '
                           'lớn hơn 0; báo thêm số khối C > B; đối chứng h2: khoảng tin cậy '
                           'chứa 0; phép đo hợp lệ khi tỉ lệ lượt hủy <= 20%'),
            'localization': ('đạt khi không có lượt nào tác động sai mục tiêu; phạm vi rộng khi '
                             'có thêm ít nhất 3 lượt chọn đúng thủ phạm khác h1'),
        },
        'offline_check_before_running': {
            'file': 'results/report/gd4cl_offline_check.json',
            'content_sha256': offline['content_sha256'],
            'summary': ('h1 flood: luật cũ đúng một ứng viên ở 7/23 và 6/22 giây cần hành động, '
                        'luật theo chiều 23/23 và 20/22; dịch nút cổ chai s1-s2: luật cũ chọn '
                        'nhầm máy khách ở 13 và 7 giây, luật theo chiều gần như không ứng viên.'),
        },
        'commitments': [
            'Báo kết quả dù tốt hay xấu; mỗi thí nghiệm chạy một lần.',
            'Không đổi luật, ngưỡng, detector hay thiết kế sau khi bắt đầu chạy.',
            'Lượt hủy được lưu và báo cáo; không thay lượt.',
            'Kết quả Phase 8 (detector 1.0.0, luật cũ) vẫn được giữ và báo cáo song song.',
        ],
        'git_head': prov['git_hash'],
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    doc = {'content': content,
           'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8'))}
    C.atomic_json(OUT, doc)
    print('✅ đã ghi %s sha=%s… (head %s)' % (OUT.relative_to(C.ROOT),
                                             doc['content_sha256'][:12], prov['git_hash'][:8]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
