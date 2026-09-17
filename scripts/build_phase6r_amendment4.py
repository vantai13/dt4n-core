#!/usr/bin/env python3
"""Phase 6R amendment 4: khóa R-O split, acceptance gates và rerun policy."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / 'results/report'
OUT = REPORT / 'phase6r_amendment_4.json'
ALLOWED_DIRTY = {
    'scripts/build_phase6r_amendment4.py',
    'test/test_phase6r_amendment4.py',
    'results/report/phase6r_amendment_4.json',
}


def git_state():
    result = subprocess.run(['git', 'status', '--porcelain'], cwd=C.ROOT,
                            capture_output=True, text=True, check=True)
    dirty = sorted(line[3:] for line in result.stdout.splitlines() if line)
    bad = [path for path in dirty if path not in ALLOWED_DIRTY and
           not path.startswith('logs/') and path != 'results/report/feature_audit.csv']
    if bad:
        raise RuntimeError('commit truoc: %s' % bad)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=C.ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    return {'head': head, 'dirty_files': dirty}


def build_content():
    if (C.ROOT / 'data/phase6r').exists():
        raise RuntimeError('R-campaign da thu')
    amendment_3 = json.loads(
        (REPORT / 'phase6r_amendment_3.json').read_text(encoding='utf-8'))
    return {
        'amendment_id': 'DT4N-P6R-AMENDMENT-4',
        'amends': {'amendment_3_sha256': amendment_3['content_sha256']},
        'git': git_state(),
        'code_sha256': {
            path: C.sha256_file(C.ROOT / path)
            for path in ('ml/rcampaign.py', 'ml/campaign.py', 'ml/serve_fast.py', 'ml/fsm.py')
        },
        'r_o_split': {
            'R-O1_restart_S9': {
                'mode': 'phat lai offline tren raw R-S',
                'where': 'tick 600, 1800, 3000 moi run R-S',
                'procedure': 'huy scorer+FSM, tao moi, tiep tuc tu snapshot ke tiep',
                'pass': 'snapshot dau sau restart -> warming_up; khong act truoc n_act tick scored; 0 tick normal truoc khi scored',
            },
            'R-O2_gap_S8': {
                'mode': 'phat lai offline tren raw R-S',
                'where': 'bo 5 snapshot lien tiep tai tick 600, 1800, 3000',
                'pass': 'snapshot dau sau khoang trong -> unknown(cause=gap); 0% tick khong judgeable thanh normal',
            },
            'R-O3_controller_S11': {
                'mode': 'THU 2 run (RO-ctl_admin_down-s1-s2)',
                'intervention': 'actor=controller, ghi log luc inject VA revert',
                'pass': 'so lan vao act trong [inject, revert+cooldown] co log == 0; S7 v2 dat',
            },
            'R-O4_kill_detector_S12': {
                'mode': 'DOI SANG PHASE 7',
                'why': 'thuoc tinh tich hop detector-Ditto-TTL, khong ton tai trong harness 6R',
            },
            'gate_status_in_6R': {
                'G3': 'MOT PHAN (controller mo phong bang harness)',
                'G4_S12': 'KHONG DONG DUOC TRONG 6R',
                'consequence': 'FSM khong the phat hanh cho Phase 8 truoc khi Phase 7 do S12 va S11 live',
            },
        },
        'run_acceptance_gates': {
            'principle': 'gate chi kiem THIET BI DO va KICH BAN CO XAY RA, khong bao gio kiem KET CUC DANG DO',
            'R-D': 'signal_present KHONG la gate; ghi thanh covariate_signal_present (truc lieu max_separation)',
            'R-O3': 'admin_down_observed la manipulation check, giu lam gate',
            'R-C': 'signal_present giu lam gate: R-C hieu chinh cooldown, can transient that; ghi ro day la thiet ke hieu chinh',
            'R-S, R-N': 'gate Phase 5 cho run normal (tick count, invalid fraction, no_unexpected_down)',
            'implementation': 'ml.rcampaign.verify_rrun',
        },
        'rerun_policy': {
            'allowed_when': 'run bi cach ly vi gate THIET BI (tick count, invalid fraction, event timing, unexpected down)',
            'how': 'run_id moi hau to -rN, CUNG seed va tham so; moi lan thu (ke ca that bai) giu trong quarantine va manifest',
            'max_attempts_per_cell': 2,
            'forbidden': 'chay lai vi ket cuc detector/tin hieu; xoa file cach ly',
        },
        'r_n_classification': {
            'why': '6-10 Mbps/client co the bao hoa s1-s2 THAT; bao dong luc do co the dung',
            'physically_justified_tick': 'bat ky link co qdiscDropDelta > 0, hoac lossPct > 1.0, hoac residual r_max > R (amendment 1)',
            'report': 'hai cot: moi tick alarm / tick alarm KHONG co can cu vat ly; S10 danh gia tren cot thu hai',
            'evidence_source_note': 'probe v2: collector thay drop khi drop xay ra (6/6 run)',
        },
        'forbidden': [
            'doi gate sau khi thay run nao bi cach ly',
            'them run ngoai hop dong',
            'mo R-set de tinh recall truoc 6R.7',
        ],
        'deviation_policy': 'bat bien sau commit',
    }


def main():
    if OUT.exists():
        print('[6R-A4] da ton tai')
        return 1
    content = build_content()
    doc = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8')),
    }
    C.atomic_json(OUT, doc)
    print('[6R-A4] content_sha256 =', doc['content_sha256'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
