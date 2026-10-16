#!/usr/bin/env python3
"""
build_gd4_prereg.py — GĐ4: ghi tiêu chí nghiệm thu detector 2.1 TRƯỚC khi thu gd4r.

Tiêu chí giữ NGUYÊN như 6R (results/report/phase6r_slo.json): S1, S2, S4 có mục tiêu,
S10 chỉ báo cáo. Cách chấm giữ nguyên: cùng hàm của ml/acceptance_metrics.py, cùng hai
kênh FSM (envelope_only, combined), cùng chế độ log như 6R. Tài liệu ghim mã băm của bản
2.1.0, hợp đồng gd4r, SLO và code chấm; viết một lần, không sửa.

    python3 scripts/build_gd4_prereg.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / 'results/report/gd4_acceptance_prereg.json'
SLO = 'results/report/phase6r_slo.json'
RELEASE = 'models/detector-release-2.1.0.json'
RELEASE_V1 = 'models/detector-release-1.0.0.json'
CONTRACT = 'results/report/gd4r_contract.json'
CODE = ('ml/acceptance_metrics.py', 'ml/acceptance_pass.py', 'ml/acceptance_stats.py',
        'ml/serve_fast.py', 'ml/serve.py', 'ml/fsm.py', 'ml/blast_radius.py',
        'ml/intervention_log.py', 'ml/labels.py', 'ml/model.py', 'ml/release.py',
        'ml/gd4rcampaign.py', 'ml/gd4_retrain.py')


def _content_sha(rel: str) -> str:
    return json.loads((C.ROOT / rel).read_text(encoding='utf-8'))['content_sha256']


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    slo = {s['id']: s for s in json.loads((C.ROOT / SLO).read_text())['content']['slo']}
    release = json.loads((C.ROOT / RELEASE).read_text())['content']
    contract = json.loads((C.ROOT / CONTRACT).read_text())
    head = C.collection_provenance(C.ROOT)
    if head['source_dirty']:
        raise SystemExit('Commit trước khi ghi tiêu chí: %s' % head['source_dirty_files'])
    content = {
        'prereg_id': 'DT4N-GD4-ACCEPTANCE-PREREG',
        'purpose': ('Nghiệm thu detector-release-2.1.0 (chỉ đổi dữ liệu train so với 1.0.0) '
                    'trên đợt gd4r thu sau khi tài liệu này được commit.'),
        'frozen': {
            'release': {'file': RELEASE, 'content_sha256': _content_sha(RELEASE)},
            'components': release['components'],
            'fsm_params': release['fsm_params'],
            'conservation_mode': release['conservation_mode'],
            'gd4r_contract_sha256': contract['design_content_sha256'],
            'slo': {'file': SLO, 'content_sha256': _content_sha(SLO)},
            'code_sha256': {p: C.sha256_file(C.ROOT / p) for p in CODE},
        },
        'targets_unchanged_from_6r': {
            k: slo[k]['target'] for k in ('S1', 'S2', 'S4', 'S10')},
        'primary': {
            'S1': ('tỉ lệ sự cố R-D được phát hiện ở mức đáng ngờ; kênh envelope_only, chế '
                   'độ with_log; ml.acceptance_metrics.incident + s1_s4 -> detection_rate'),
            'S2': ('cận trên 95% số báo động sai mỗi giờ trên 3 run R-S; kênh envelope_only, '
                   'no_log; s2_s3 -> rate_upper_per_hour'),
            'S4': ('p95 thời gian phát hiện trên các sự cố R-D được phát hiện; envelope_only; '
                   's1_s4 -> t_detect_p95_ms'),
            'S10': 'R-N 6/8/10 Mbps: chỉ báo cáo alarm_ticks và fp (s10), không có mục tiêu',
            'verdict_rule': 'giá trị so với target 6R bằng toán tử đã ghi; không người nào gõ tay',
        },
        'descriptive_pre_declared': {
            'combined': 'S1, S2, S4 của kênh combined (envelope hoặc residual), như 6R',
            'by_rho': ('S1 tách theo rho của từng sự cố R-D (ml.acceptance_metrics.residual_run): '
                       'rho >= 1,10 và rho <= 0,90'),
            'v1_on_gd4r': ('detector-release-1.0.0 chấm trên cùng gd4r: tách ảnh hưởng của dữ '
                           'liệu mới khỏi ảnh hưởng của mô hình mới'),
            'v21_on_6r': ('detector-release-2.1.0 chấm trên 25 run 6R cũ (đã mở): chỉ mô tả, '
                          'nếu dữ liệu LFS lấy được'),
        },
        'validation_before_opening': (
            'Script chấm phải tái lập ĐÚNG số 6R đã công bố khi chạy 1.0.0 trên 25 run 6R '
            '(S1 0,3; S2 0,9994; S4 2007 ms; combined 0,6 và 11001 ms; S10 từng run) trước khi '
            'đọc byte gd4r đầu tiên. Không tái lập được thì sửa script, không chạm gd4r.'),
        'commitments': [
            'Báo kết quả của 2.1.0 dù tốt hay xấu hơn 1.0.0; không quay về 1.0.0 vì số xấu.',
            'Chấm gd4r một lần; không đổi ngưỡng, cột, FSM, luật ức chế sau khi mở.',
            'Run hỏng ở cổng thiết bị được thu lại, mọi lần thử được lưu và báo cáo; '
            'signal_present của R-D là covariate như 6R.',
            'Không chạy lại vòng kín; kết quả vòng kín vẫn là của 1.0.0.',
            'R-O (2 run) được thu để giữ thiết kế giống 6R nhưng không vào S1/S2/S4.',
        ],
        'git_head': head['git_hash'],
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    doc = {'content': content,
           'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8'))}
    C.atomic_json(OUT, doc)
    print('✅ đã ghi %s sha=%s… (head %s)' % (
        OUT.relative_to(C.ROOT), doc['content_sha256'][:12], head['git_hash'][:8]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
