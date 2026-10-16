#!/usr/bin/env python3
"""
declare_gd4_drift.py — khai báo TRÔI lần hai cho hai file đã ghim (sau phase6r_drift_gd2).

VÌ SAO CẦN:
  GĐ4 thêm binding 'gd4', 'gd4r' vào ml/campaign_binding.py và một nhánh elif vào
  scripts/launch_ml_dataset.py. Pin mới nhất của hai file này nằm ở
  phase6r_drift_gd2.json (khai báo trôi của GĐ2).
  Sổ ghim (test/test_amendment_pin_ledger.py) cho phép trôi nếu có một tài liệu
  niêm phong SAU nhận trách nhiệm; trôi IM LẶNG thì không. File JSON mà script
  này ghi ra chính là lời khai đó.

  Đây KHÔNG phải amendment của Phase 6R: không đổi giả thuyết, dữ liệu, ngưỡng hay
  kết quả nào của 6R. Tên bắt đầu bằng phase6r_ chỉ vì sổ ghim quét đúng mẫu
  results/report/phase6r_*.json.

  Script tự kiểm: (1) bản tại git head của khai báo GĐ2 khớp pin; (2) bản hiện tại
  khác pin (có trôi thật); (3) hai file đã commit (pin mới phải có trong lịch sử).
  Toàn văn diff được ghi vào tài liệu để người đọc thấy đúng cái gì đã đổi.

CÁCH CHẠY (code GĐ4 đã commit):
    python3 scripts/declare_gd4_drift.py
    git add scripts/declare_gd4_drift.py results/report/phase6r_drift_gd4.json
    git commit -m "GĐ4: khai báo trôi hai file đã ghim"
    python3 -m pytest -q test/test_amendment_pin_ledger.py    # phải qua SAU commit
"""
from __future__ import annotations

import difflib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # như các script khác

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / 'results/report/phase6r_drift_gd4.json'
AMENDMENT = C.ROOT / 'results/report/phase6r_drift_gd2.json'
CHANGES = {
    'ml/campaign_binding.py':
        'GĐ4: thêm hàm _gd4(), _gd4r() và hai khóa vào BINDINGS; các binding cũ giữ nguyên',
    'scripts/launch_ml_dataset.py':
        'GĐ4: thêm nhánh elif binding.name in ("gd4", "gd4r") (kiểm hợp đồng và máy thu); '
        'các nhánh cũ giữ nguyên',
}
VERIFIED_BY = ['test/test_campaign_binding.py', 'test/test_campaign_execution.py',
               'test/test_gd2.py', 'test/test_gd4.py']


def git(*args) -> bytes:
    return subprocess.run(['git', *args], cwd=C.ROOT, capture_output=True,
                          check=True).stdout


def main() -> int:
    if OUT.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % OUT.relative_to(C.ROOT))
    amend = json.loads(AMENDMENT.read_text(encoding='utf-8'))
    pins = amend['content']['code_sha256']
    base = amend['content']['git']['head']
    head = git('rev-parse', 'HEAD').decode().strip()
    dirty = [p for p in CHANGES if git('status', '--porcelain', '--', p).strip()]
    if dirty:
        raise SystemExit('Commit hai file trước khi khai báo: %s' % dirty)

    drift, diff, now_pins = [], [], {}
    for path in CHANGES:
        old = git('show', '%s:%s' % (base, path))
        if C.sha256_bytes(old) != pins[path]:
            raise SystemExit('Bản tại %s không khớp pin GĐ2: %s' % (base[:8], path))
        new_sha = C.sha256_file(C.ROOT / path)
        if new_sha == pins[path]:
            raise SystemExit('%s không trôi: không cần khai báo' % path)
        new = (C.ROOT / path).read_bytes()
        lines = list(difflib.unified_diff(
            old.decode('utf-8').splitlines(), new.decode('utf-8').splitlines(),
            'a/' + path, 'b/' + path, lineterm=''))
        drift.append({
            'path': path,
            'pinned_by_gd2_declaration': pins[path],
            'now': new_sha,
            'lines_added': sum(1 for x in lines if x.startswith('+') and not x.startswith('+++')),
            'lines_removed': sum(1 for x in lines if x.startswith('-') and not x.startswith('---')),
        })
        diff.extend(lines)
        now_pins[path] = new_sha

    content = {
        'declaration_id': 'DT4N-GD4-DRIFT-1',
        'kind': 'pin_drift_declaration',
        'scope_note': ('Không phải amendment của Phase 6R: không đổi giả thuyết, dữ liệu, '
                       'ngưỡng hay kết quả nào của 6R. Tên phase6r_ chỉ để sổ ghim quét được.'),
        'declares_drift_against': {
            'document': 'results/report/phase6r_drift_gd2.json',
            'gd2_declaration_content_sha256': amend['content_sha256'],
        },
        'reason': ('GĐ4 thu lại run train thay thế (gd4) và đợt nghiệm thu (gd4r) trên '
                   'máy GCP bằng đúng launcher và runner đã dùng cho Phase 5 và 6R, nên cần '
                   'đăng ký hai chiến dịch vào hai file này. Xem ml/gd4campaign.py, '
                   'ml/gd4rcampaign.py.'),
        'git': {'head': head, 'dirty_files': []},
        'code_sha256': now_pins,
        'changes': CHANGES,
        'drift': drift,
        'unchanged': ('Hành vi của binding phase5, phase6r và gd2 không đổi; runner '
                      '(scripts/generate_ml_dataset.py), ml/rcampaign.py và '
                      'ml/rcampaign_runtime.py không sửa.'),
        'verified_by': VERIFIED_BY,
        'diff': diff,
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    doc = {'content': content,
           'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8'))}
    C.atomic_json(OUT, doc)
    for d in drift:
        print('trôi %-30s +%d/-%d dòng  %s… -> %s…' % (
            d['path'], d['lines_added'], d['lines_removed'],
            d['pinned_by_gd2_declaration'][:8], d['now'][:8]))
    print('✅ đã ghi %s (head %s). Commit nó rồi chạy lại sổ ghim.'
          % (OUT.relative_to(C.ROOT), head[:8]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
