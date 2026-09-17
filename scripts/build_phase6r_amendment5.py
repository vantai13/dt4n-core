#!/usr/bin/env python3
"""Làm rõ hai chi tiết thủ tục runner trước khi thu R-campaign."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ml import campaign as C
from ml import rcampaign as R

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6r_amendment_5.json'
CODE = (
    'ml/campaign_binding.py',
    'ml/rcampaign_runtime.py',
    'scripts/generate_ml_dataset.py',
    'scripts/launch_ml_dataset.py',
    'ml/rcampaign.py',
)


def main() -> int:
    if OUT.exists():
        print('[6R-A5] da ton tai')
        return 1
    if (C.ROOT / R.DATA_DIR).exists():
        raise SystemExit('R-campaign da thu')
    provenance = C.collection_provenance(C.ROOT)
    allowed = {
        'scripts/build_phase6r_amendment5.py',
        'results/report/phase6r_amendment_5.json',
    }
    if set(provenance['source_dirty_files']) - allowed:
        raise SystemExit('commit truoc: %s' % provenance['source_dirty_files'])
    amendment_4 = json.loads(
        (REPORT / 'phase6r_amendment_4.json').read_text(encoding='utf-8'))
    matrix = R.load_contract()
    content = {
        'amendment_id': 'DT4N-P6R-AMENDMENT-5',
        'amends': {
            'amendment_4_sha256': amendment_4['content_sha256'],
            'rcampaign_design_sha256': matrix['design_content_sha256'],
        },
        'git_head': provenance['git_hash'],
        'code_sha256': {path: C.sha256_file(C.ROOT / path) for path in CODE},
        'clarification_1_rerun_identity': {
            'amendment_4_text': 'run_id moi hau to -rN',
            'implemented': ('GIU run_id trong hop dong; lan thu that bai duoc '
                            'archive_attempt doi ten <run_id>.*.attempt-<utc>-<uuid>.* '
                            'trong quarantine; manifest ghi lan thu cuoi'),
            'why': 'run_id nam trong hop dong da hash; them run_id moi la chay run NGOAI hop dong',
            'unchanged': 'cung seed/tham so; toi da 2 lan; chi loi dung cu; khong xoa lan thu nao',
        },
        'clarification_2_intervention_t_start': {
            'amendment_2_replay': 't_start = t_source cua su kien revert (ghi SAU khi apply)',
            'r_campaign_runtime': 't_start = time.time() NGAY TRUOC khi apply; ghi o sidecar.interventions',
            'why': 'hieu ung trong luc apply (toi 360 ms voi shift) phai nam trong cua so uc che; khop hop dong Phase 8 append-before-act',
            'analysis_rule': 'moi phan tich R-set dung sidecar.interventions, KHONG dung events cho uc che',
        },
        'timing_and_knowledge': {
            'r_campaign_collected': False,
            'outcome_information_used': 'khong',
        },
        'deviation_policy': 'bat bien sau commit',
    }
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        'content_sha256': C.sha256_bytes(
            C.canonical_json(content).encode('utf-8')),
    }
    C.atomic_json(OUT, document)
    print('[6R-A5] content_sha256 =', document['content_sha256'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
