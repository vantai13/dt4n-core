#!/usr/bin/env python3
"""Khóa hợp đồng R-campaign một lần, trước khi thu bất kỳ run nào."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ml import campaign as C
from ml import rcampaign as R

REPORT = C.ROOT / 'results/report'


def main() -> int:
    if R.CONTRACT_PATH.exists():
        print('[rcampaign] hop dong da khoa; khong ghi de')
        return 1
    if (C.ROOT / R.DATA_DIR).exists():
        raise SystemExit('%s da ton tai: khong khoa hop dong sau khi da thu' % R.DATA_DIR)
    amendment_1 = json.loads((REPORT / 'phase6r_amendment_1.json').read_text(encoding='utf-8'))
    slo = json.loads((REPORT / 'phase6r_slo.json').read_text(encoding='utf-8'))
    subset = R.contract_subset(amendment_1)
    validation = R.validate(subset, slo)
    provenance = C.collection_provenance(C.ROOT)
    doc = {
        'campaign_id': R.CAMPAIGN_ID, 'design_locked': True,
        'status': 'planned_not_collected', **subset, 'n_runs': len(subset['runs']),
        'validation': validation,
        'design_provenance': {
            'git_hash': provenance['git_hash'],
            'source_dirty': provenance['source_dirty'],
            'module_sha256': C.sha256_file(C.ROOT / 'ml/rcampaign.py'),
            'amendment_3_sha256': json.loads(
                (REPORT / 'phase6r_amendment_3.json').read_text())['content_sha256'],
            'amendment_4_sha256': json.loads(
                (REPORT / 'phase6r_amendment_4.json').read_text())['content_sha256'],
        },
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    if provenance['source_dirty']:
        raise SystemExit('commit source truoc khi khoa hop dong: %s' %
                         provenance['source_dirty_files'])
    doc['design_content_sha256'] = R.design_hash(doc)
    C.atomic_json(R.CONTRACT_PATH, doc)
    print('[rcampaign] %d run, design_content_sha256=%s' %
          (doc['n_runs'], doc['design_content_sha256']))
    print('[rcampaign] uoc tinh thoi gian thu: %.1f gio' %
          (validation['collection_seconds_estimate'] / 3600))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
