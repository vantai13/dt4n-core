#!/usr/bin/env python3
"""
gd2campaign.py — GĐ2: chiến dịch thu MỘT run train thay thế cho N-vary-s1008-r2.

VÌ SAO LÀ CHIẾN DỊCH RIÊNG (giống tiền lệ phase6r):
  Hợp đồng Phase 5 (experiment_matrix.json) đã khóa bằng hash; thêm run vào đó là
  "dời vạch đích". Run thay thế có hợp đồng RIÊNG, nhỏ, cũng khóa bằng hash, và
  tham chiếu ngược hash của hợp đồng Phase 5 mà nó bổ sung.

  Run mới = bản sao ĐÚNG của record s1008 (cùng lịch tải A, cùng seed 1008, cùng
  hằng số), chỉ khác run_id (r3) và exec_index (0). Thứ duy nhất được thêm là CỔNG
  client_traffic (ml/client_gate.py): run nào có client im lặng -> cách ly, không
  vào train.

  Dữ liệu nằm ở data/phase5/gd2/ (KHÔNG phải data/phase5/raw/): tiền tố data/phase5/
  được ml.campaign.collection_provenance coi là dữ liệu runtime, nên file mới ghi ra
  không làm "bẩn nguồn"; và thư mục con riêng không đụng phép đếm 18 run của Phase 5.

CÁCH CHẠY:
    python3 -m ml.gd2campaign build-contract     # tạo + khóa hợp đồng (một lần)
    python3 -m ml.gd2campaign check              # kiểm hợp đồng còn nguyên
    .venv/bin/python scripts/launch_ml_dataset.py --campaign gd2    # THU (cần sudo -n)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ml import campaign as C
from ml import client_gate as CG

CAMPAIGN_ID = 'DT4N-GD2-REPLACE-S1008'
SOURCE_CONTRACT_REL = 'results/report/experiment_matrix.json'
CONTRACT_REL = 'results/report/gd2_contract.json'
MANIFEST_REL = 'results/report/gd2_manifest.json'
DATA_REL = 'data/phase5/gd2'
SOURCE_RUN = 'N-vary-s1008-r2'
NEW_RUN = 'N-vary-s1008-r3'
CONTRACT_KEYS = ('campaign_id', 'constants', 'runs', 'execution_order', 'split',
                 'replaces', 'source_contract_sha256', 'gate')


def design_hash(doc: dict) -> str:
    subset = {k: doc[k] for k in CONTRACT_KEYS}
    return C.sha256_bytes(C.canonical_json(subset).encode('utf-8'))


def _source(root: Path) -> dict:
    p5 = C.load_contract(root / SOURCE_CONTRACT_REL)
    C.check_contract_integrity(p5, root)          # ném lỗi nếu Phase 5 đã trôi
    return p5


def expected_record(p5: dict) -> dict:
    src = next(r for r in p5['runs'] if r['run_id'] == SOURCE_RUN)
    return dict(src, run_id=NEW_RUN, exec_index=0)


def build_contract(root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    p5 = _source(root)
    doc = {
        'campaign_id': CAMPAIGN_ID,
        'design_locked': True,
        'status': 'planned_not_collected',
        'n_runs': 1,
        'constants': p5['constants'],
        'runs': [expected_record(p5)],
        'execution_order': [NEW_RUN],
        'split': {'train': [NEW_RUN], 'test': []},
        'replaces': SOURCE_RUN,
        'source_contract_sha256': p5['design_content_sha256'],
        'gate': {'client_traffic': {'ratio': CG.RATIO, 'min_fraction': CG.MIN_FRACTION,
                                    'clients': list(CG.CLIENTS)}},
        'reason': ('%s có h1, h3 txRate = 0 suốt run nhưng qua mọi cổng cũ; envelope-1.0.0 '
                   'học biên dưới 0 cho h1, h3. Thu lại đúng cấu hình đó, thêm cổng '
                   'client_traffic. Xem results/report/gd2_client_traffic_audit.json.'
                   % SOURCE_RUN),
        'provenance': C.collection_provenance(root),
    }
    doc['design_content_sha256'] = design_hash(doc)
    return doc


def load_contract(path=None) -> dict:
    path = Path(path or C.ROOT / CONTRACT_REL)
    return C.load_contract(path)        # cùng các kiểm tra hình dạng của Phase 5


def check_integrity(doc: dict, root: Path | None = None) -> dict:
    """Hash trong file == hash tính lại; Phase 5 chưa trôi; record đúng bản sao s1008."""
    root = Path(root or C.ROOT)
    stored = doc.get('design_content_sha256')
    recomputed = design_hash(doc)
    p5 = _source(root)
    ok = (stored == recomputed
          and doc['source_contract_sha256'] == p5['design_content_sha256']
          and doc['runs'] == [expected_record(p5)]
          and doc['constants'] == p5['constants'])
    result = {'stored': stored, 'recomputed': recomputed, 'match': ok}
    if not ok:
        raise RuntimeError('Hợp đồng gd2 lệch (hash, nguồn Phase 5 hoặc record): %s' % result)
    return result


def run_paths(run_id: str, root: Path | None = None) -> dict:
    """Giống ml.campaign.run_paths nhưng trong data/phase5/gd2/."""
    root = Path(root or C.ROOT)
    import re
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('run_id không hợp lệ: %r' % run_id)
    raw = root / DATA_REL / 'raw'
    quar = root / DATA_REL / 'quarantine'
    return {
        'partial': raw / ('%s.jsonl.partial' % run_id),
        'final': raw / ('%s.jsonl' % run_id),
        'meta': raw / ('%s.meta.json' % run_id),
        'quarantine': quar / ('%s.jsonl' % run_id),
        'quarantine_meta': quar / ('%s.meta.json' % run_id),
        'log': root / ('logs/gd2_gen_%s.log' % run_id),
    }


def verify_gd2_run(record, constants, snapshots, events) -> dict:
    """Mọi cổng cũ của Phase 5 + cổng client_traffic mới."""
    checks = C.verify_run(record, constants, snapshots, events)
    checks.update(CG.client_traffic_check(record, snapshots, events,
                                          int(constants['warmup_ticks'])))
    if not checks['client_traffic_ok']:
        checks['passed'] = False
        if 'client_traffic_ok' not in checks['failed_gates']:
            checks['failed_gates'].append('client_traffic_ok')
    return checks


def build_manifest(*args) -> dict:
    manifest = C.build_manifest(*args)
    manifest['campaign'] = CAMPAIGN_ID
    return manifest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ''
    out = C.ROOT / CONTRACT_REL
    if cmd == 'build-contract':
        if out.exists():
            raise SystemExit('Đã tồn tại, không ghi đè: %s' % CONTRACT_REL)
        doc = build_contract()
        C.atomic_json(out, doc)
        print('✅ đã khóa %s  sha=%s…' % (CONTRACT_REL, doc['design_content_sha256'][:12]))
        print('   run: %s (bản sao %s), nguồn Phase 5 sha=%s…' % (
            NEW_RUN, SOURCE_RUN, doc['source_contract_sha256'][:12]))
        return 0
    if cmd == 'check':
        res = check_integrity(load_contract(out))
        print('✅ hợp đồng gd2 nguyên vẹn: %s' % json.dumps(res))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
