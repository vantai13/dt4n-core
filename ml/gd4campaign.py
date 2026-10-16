#!/usr/bin/env python3
"""
gd4campaign.py — GĐ4: thu lại run train thay thế cho N-vary-s1008-r2 trên MÁY NGHIỆM THU.

VÌ SAO CẦN CHIẾN DỊCH THỨ HAI (sau gd2):
  Run thay thế của gd2 (N-vary-s1008-r3) được thu trên WSL2. Bảy run train còn lại, cả
  tập test Phase 5 và 25 run nghiệm thu 6R đều thu trên máy ảo GCP. Trên r3, residual
  bảo toàn lớn nhất là 0,182, trong khi run cùng lịch tải s1007 (GCP) chỉ 0,073; học lại
  R từ r3 sẽ làm R tăng hơn gấp đôi vì khác máy chứ không vì mạng. GĐ4 thu lại đúng
  record s1008 trên máy GCP, giữ cổng client_traffic của gd2. Dữ liệu r3 giữ nguyên.

  Hợp đồng ghi tên máy thu (collection_host); launcher từ chối chạy ở máy khác.

CÁCH CHẠY:
    python3 -m ml.gd4campaign build-contract     # tạo + khóa hợp đồng (một lần)
    python3 -m ml.gd4campaign check
    .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4    # THU, trên máy GCP
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ml import campaign as C
from ml import client_gate as CG
from ml import gd2campaign as G2

CAMPAIGN_ID = 'DT4N-GD4-REPLACE-S1008-GCP'
SOURCE_CONTRACT_REL = G2.SOURCE_CONTRACT_REL
CONTRACT_REL = 'results/report/gd4_contract.json'
MANIFEST_REL = 'results/report/gd4_manifest.json'
DATA_REL = 'data/phase5/gd4'
SOURCE_RUN = G2.SOURCE_RUN
NEW_RUN = 'N-vary-s1008-r4'
COLLECTION_HOST = 'dt4n-research-01'      # máy ảo GCP đã thu Phase 5 và 6R
CONTRACT_KEYS = G2.CONTRACT_KEYS + ('collection_host',)


def design_hash(doc: dict) -> str:
    subset = {k: doc[k] for k in CONTRACT_KEYS}
    return C.sha256_bytes(C.canonical_json(subset).encode('utf-8'))


def expected_record(p5: dict) -> dict:
    src = next(r for r in p5['runs'] if r['run_id'] == SOURCE_RUN)
    return dict(src, run_id=NEW_RUN, exec_index=0)


def build_contract(root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    p5 = G2._source(root)
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
        'collection_host': COLLECTION_HOST,
        'reason': ('Run thay thế gd2 (N-vary-s1008-r3) thu trên WSL2, khác máy với 7 run '
                   'train còn lại và toàn bộ dữ liệu test/nghiệm thu; residual lớn nhất '
                   '0,182 so với 0,073 ở s1007. Thu lại record s1008 trên máy GCP.'),
        'provenance': C.collection_provenance(root),
    }
    doc['design_content_sha256'] = design_hash(doc)
    return doc


def load_contract(path=None) -> dict:
    return C.load_contract(Path(path or C.ROOT / CONTRACT_REL))


def check_integrity(doc: dict, root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    stored = doc.get('design_content_sha256')
    recomputed = design_hash(doc)
    p5 = G2._source(root)
    ok = (stored == recomputed
          and doc['source_contract_sha256'] == p5['design_content_sha256']
          and doc['runs'] == [expected_record(p5)]
          and doc['constants'] == p5['constants']
          and doc['collection_host'] == COLLECTION_HOST)
    result = {'stored': stored, 'recomputed': recomputed, 'match': ok}
    if not ok:
        raise RuntimeError('Hợp đồng gd4 lệch (hash, nguồn Phase 5, record hoặc máy): %s'
                           % result)
    return result


def run_paths(run_id: str, root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
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
        'log': root / ('logs/gd4_gen_%s.log' % run_id),
    }


verify_gd4_run = G2.verify_gd2_run          # cổng Phase 5 + client_traffic, không đổi


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
        return 0
    if cmd == 'check':
        print('✅ hợp đồng gd4 nguyên vẹn: %s' % json.dumps(check_integrity(load_contract(out))))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
