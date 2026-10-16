#!/usr/bin/env python3
"""
gd4rcampaign.py — GĐ4: thu lại đợt nghiệm thu (R-campaign) cho detector bản 2.1.

VÌ SAO THU LẠI THAY VÌ CHẤM LẠI 25 RUN CŨ:
  25 run nghiệm thu 6R đã được mở và kết quả của bản 1.0.0 trên đó đã được xem. Bản 2.1
  chỉ đổi dữ liệu train, nhưng nghiệm thu nó trên dữ liệu chưa ai xem thì kết quả không
  phụ thuộc vào việc ai đã biết gì. Thiết kế giữ ĐÚNG như 6R (cùng nhóm, cùng số run,
  cùng liều giảm băng thông từ amendment 1, cùng thời lượng); chỉ đổi seed (+1000), thứ
  tự chạy và thư mục dữ liệu. Máy thu ghi trong hợp đồng: máy GCP đã thu 6R.

  Dữ liệu nằm dưới data/phase5/ vì ml.campaign.collection_provenance coi tiền tố đó là
  dữ liệu runtime (thư mục data/phase6r của 6R làm 20/25 sidecar bị gắn cờ bẩn nguồn).

CÁCH CHẠY:
    python3 -m ml.gd4rcampaign build-contract
    python3 -m ml.gd4rcampaign check
    .venv/bin/python scripts/launch_ml_dataset.py --campaign gd4r --hard-every 6
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from ml import campaign as C
from ml import rcampaign as R

CAMPAIGN_ID = 'DT4N-GD4-RCAMPAIGN'
EXEC_ORDER_SEED = 20261016
SEED_OFFSET = 1000
DATA_DIR = 'data/phase5/gd4r'
CONTRACT_REL = 'results/report/gd4r_contract.json'
MANIFEST_REL = 'results/report/gd4r_manifest.json'
COLLECTION_HOST = 'dt4n-research-01'
SOURCE_DESIGN_REL = 'results/report/phase6r_rcampaign_matrix.json'
CONTRACT_KEYS = R.CONTRACT_KEYS + ('collection_host', 'source_design_sha256')
CONSTANTS = dict(R.CONSTANTS, campaign_id=CAMPAIGN_ID, exec_order_seed=EXEC_ORDER_SEED)


def _amendment_1(root: Path) -> dict:
    return json.loads((root / 'results/report/phase6r_amendment_1.json').read_text(
        encoding='utf-8'))


def _reseed(record: dict) -> dict:
    """Cùng record 6R, seed + 1000, run_id đổi theo seed; R-C tính lại mức độ từ seed mới."""
    old, new = record['seed'], record['seed'] + SEED_OFFSET
    out = dict(record, seed=new, run_id=record['run_id'].replace('-s%d-' % old, '-s%d-' % new))
    if out['run_id'] == record['run_id']:
        raise ValueError('run_id không chứa seed: %s' % record['run_id'])
    if record['group'] == 'RC':
        out['fault_parameters'] = R._severity(record['fault'], record['fault_target'], new)
    return out


def build_runs(amendment_1: dict) -> list[dict]:
    return [_reseed(r) for r in R.build_runs(amendment_1)]


def contract_subset(root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    runs = build_runs(_amendment_1(root))
    ids = [r['run_id'] for r in runs]
    order = random.Random(EXEC_ORDER_SEED).sample(ids, len(ids))
    pos = {run_id: i for i, run_id in enumerate(order)}
    for record in runs:
        record['exec_index'] = pos[record['run_id']]
    groups = {}
    for record in runs:
        groups.setdefault(record['group'], []).append(record['run_id'])
    return {
        'constants': dict(CONSTANTS), 'runs': runs, 'execution_order': order,
        'groups': {g: sorted(v) for g, v in sorted(groups.items())},
        'routing_table_sha256': C.sha256_file(root / 'ditto/routing_table.json'),
        'topology_spec_sha256': C.sha256_file(root / 'ditto/topology_spec.json'),
        'amendment_1_sha256': _amendment_1(root)['content_sha256'],
        'collection_host': COLLECTION_HOST,
        'source_design_sha256': R.load_contract(root / SOURCE_DESIGN_REL)[
            'design_content_sha256'],
    }


def design_hash(subset: dict) -> str:
    return C.sha256_bytes(C.canonical_json({k: subset[k] for k in CONTRACT_KEYS}).encode())


def build_contract(root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    subset = contract_subset(root)
    slo = json.loads((root / 'results/report/phase6r_slo.json').read_text(encoding='utf-8'))
    checks = R.validate(subset, slo)
    doc = dict(subset, campaign_id=CAMPAIGN_ID, design_locked=True,
               status='planned_not_collected', n_runs=len(subset['runs']),
               validation=checks, provenance=C.collection_provenance(root))
    doc['design_content_sha256'] = design_hash(subset)
    return doc


def load_contract(path=None) -> dict:
    doc = json.loads(Path(path or C.ROOT / CONTRACT_REL).read_text(encoding='utf-8'))
    if doc.get('campaign_id') != CAMPAIGN_ID or not doc.get('design_locked'):
        raise RuntimeError('không phải hợp đồng gd4r đã khóa')
    if doc['design_content_sha256'] != design_hash(doc):
        raise RuntimeError('nội dung hợp đồng gd4r đã bị sửa')
    return doc


def check_integrity(doc: dict, root: Path | None = None) -> dict:
    recomputed = design_hash(contract_subset(root))
    ok = doc['design_content_sha256'] == design_hash(doc) == recomputed
    if not ok:
        raise RuntimeError('HỢP ĐỒNG GD4R TRÔI LỆCH: stored=%s recomputed=%s'
                           % (doc['design_content_sha256'], recomputed))
    return {'stored': doc['design_content_sha256'], 'recomputed': recomputed, 'match': ok}


def run_paths(run_id: str, root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    p5 = C.run_paths(run_id, root)
    raw, quarantine = root / DATA_DIR / 'raw', root / DATA_DIR / 'quarantine'
    return {
        'partial': raw / p5['partial'].name,
        'final': raw / p5['final'].name,
        'meta': raw / p5['meta'].name,
        'quarantine': quarantine / p5['quarantine'].name,
        'quarantine_meta': quarantine / p5['quarantine_meta'].name,
        'log': root / ('logs/gd4r_%s.log' % run_id),
    }


verify_run = R.verify_rrun        # cùng cổng 6R: signal_present của R-D là covariate


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ''
    out = C.ROOT / CONTRACT_REL
    if cmd == 'build-contract':
        if out.exists():
            raise SystemExit('Đã tồn tại, không ghi đè: %s' % CONTRACT_REL)
        doc = build_contract()
        C.atomic_json(out, doc)
        print('✅ đã khóa %s  sha=%s…  %d run %s' % (
            CONTRACT_REL, doc['design_content_sha256'][:12], doc['n_runs'],
            {g: len(v) for g, v in doc['groups'].items()}))
        return 0
    if cmd == 'check':
        print('✅ hợp đồng gd4r nguyên vẹn: %s' % json.dumps(check_integrity(load_contract(out))))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
