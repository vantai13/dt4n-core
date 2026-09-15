#!/usr/bin/env python3
"""Lesson 5.3 — chốt ma trận thí nghiệm RA FILE, trước khi chạy dòng nào.

CHẠY:   python3 -m scripts.build_matrix
RA:     results/report/experiment_matrix.json
        docs/phase-5/03-experiment-matrix.generated.md   (bảng tự sinh)

Chạy lại phải cho kết quả GIỐNG HỆT (trừ khối provenance). Nếu khác, ma
trận không tất định -> không tái lập được -> sửa trước khi sinh dữ liệu.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from ml.design import (ALL_LINKS, COLLECTOR_VERSION, DURATION_SEC,
                       EXEC_ORDER_SEED, PERIOD_SEC, PRE_ROLL_SEC, T_INJECT,
                       T_REVERT, WARMUP_TICKS, build_matrix, execution_order,
                       expected_base_rate, flows_through, git_provenance,
                       matrix_to_records, snapshot_metadata, validate_matrix)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/report'
DOCS = ROOT / 'docs/phase-5'


def markdown_table(runs, order) -> str:
    pos = {rid: i for i, rid in enumerate(order)}
    head = ('| # | run_id | split | profile | tải (Mbps/client) | fault | target '
            '| t_inject | tick bất thường | link dự kiến đổi |\n'
            '|--:|---|---|---|---|---|---|--:|--:|---|\n')
    rows = []
    for r in sorted(runs, key=lambda r: pos[r.run_id]):
        load = (f'{r.load_mbps_per_client:g}' if r.load_mbps_per_client
                else 'biến thiên')
        rows.append('| {} | `{}` | {} | {} | {} | {} | {} | {} | {} | {} |'.format(
            pos[r.run_id], r.run_id, r.split, r.profile, load,
            r.fault or '—', f'`{r.fault_target}`' if r.fault_target else '—',
            f'{r.t_inject:g}s' if r.t_inject else '—',
            r.expected_anomalous_ticks(),
            ', '.join(f'`{x}`' for x in r.expected_links) or '—'))
    return head + '\n'.join(rows) + '\n'


def main() -> int:
    runs = build_matrix()
    order = execution_order(runs)
    checks = validate_matrix(runs)
    prov = git_provenance(ROOT)

    touched = set()
    for r in runs:
        touched |= set(r.expected_links)
    coverage = {ln: {'covered': ln in touched, 'flows': flows_through(ln)}
                for ln in ALL_LINKS}

    doc = {
        'design_locked': bool(checks['all_pass']),
        'status': 'planned_not_collected',
        'routing_table_sha256': hashlib.sha256((ROOT/'ditto/routing_table.json').read_bytes()).hexdigest(),
        'topology_spec_sha256': hashlib.sha256((ROOT/'ditto/topology_spec.json').read_bytes()).hexdigest(),
        'constants': {
            'duration_sec': DURATION_SEC, 'pre_roll_sec': PRE_ROLL_SEC,
            'warmup_ticks': WARMUP_TICKS, 'period_sec': PERIOD_SEC,
            't_inject': T_INJECT, 't_revert': T_REVERT,
            'collector_version': COLLECTOR_VERSION,
            'exec_order_seed': EXEC_ORDER_SEED,
        },
        'provenance': prov,
        'n_runs': len(runs),
        'execution_order': order,
        'split': {
            'train': sorted(r.run_id for r in runs if r.split == 'train'),
            'test': sorted(r.run_id for r in runs if r.split == 'test'),
        },
        'expected_base_rate_test': round(expected_base_rate(runs), 4),
        'link_coverage': coverage,
        'validation': checks,
        'runs': matrix_to_records(runs, order),
        'example_snapshot_metadata': snapshot_metadata(runs[-1], order.index(runs[-1].run_id), prov),
        'notes': [
            'Fault CHỈ có ở tập test: unsupervised anomaly detection phải học '
            '"bình thường" từ dữ liệu bình thường.',
            'Tập test có 2 run normal đối chứng, nếu không thì KHÔNG đo được FPR.',
            'Thứ tự chạy ngẫu nhiên hóa để khử nhiễu trôi theo thời gian của máy.',
            'Nền của mọi run fault là normal TCP 2 Mbps -> nền giữ giống '
            'với đối chứng; flood/shift vẫn thêm UDP nên không tách riêng tác động protocol và load.',
            'link dự kiến đổi tính TỪ bảng định tuyến tĩnh, không phải phỏng đoán; '
            'Lesson 5.5 sẽ đối chiếu thực tế với dự đoán này.',
        ],
    }

    contract = {k: doc[k] for k in ('constants','runs','execution_order','split','routing_table_sha256','topology_spec_sha256')}
    doc['design_content_sha256'] = hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    doc['provenance_scope'] = 'design-generation working tree; collection must record its own committed source and dirty state'
    doc['notes'].append('Expected links are routing-based hypotheses, not guaranteed measured effect or detection coverage. Independent experimental units are runs/events, not 160 independent fault ticks.')
    OUT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    (OUT / 'experiment_matrix.json').write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    (DOCS / '03-experiment-matrix.generated.md').write_text(
        '# Ma trận thí nghiệm Phase 5 (tự sinh — đừng sửa tay)\n\n'
        f'- git: `{prov["git_hash"]}` dirty=`{prov["git_dirty"]}`\n'
        f'- {len(runs)} run, base_rate test dự kiến '
        f'**{doc["expected_base_rate_test"]:.1%}**\n'
        f'- accuracy của mô hình ngu "luôn nói bình thường": '
        f'**{checks["dumb_always_normal_accuracy"]:.1%}**\n\n'
        + markdown_table(runs, order), encoding='utf-8')

    print(f'{len(runs)} run | base_rate test dự kiến = '
          f'{doc["expected_base_rate_test"]:.1%} | '
          f'accuracy mô hình ngu = {checks["dumb_always_normal_accuracy"]:.1%}')
    print(f'train = {len(doc["split"]["train"])} run, '
          f'test = {len(doc["split"]["test"])} run')
    uncovered = [ln for ln, v in coverage.items() if not v['covered']]
    print(f'phủ link: {8 - len(uncovered)}/8' +
          (f'  CHƯA PHỦ: {uncovered}' if uncovered else '  (đủ cả 8)'))
    for k, v in checks.items():
        if isinstance(v, bool) and not v:
            print(f'  FAIL: {k}')
    print(f'\n-> {OUT / "experiment_matrix.json"}')
    print(f'-> {DOCS / "03-experiment-matrix.generated.md"}')

    if not checks['all_pass']:
        print('\nGATE FAIL: ma trận chưa đạt. Sửa thiết kế TRƯỚC khi chạy.')
        return 1
    if prov['git_dirty']:
        print('\nCẢNH BÁO: git_dirty=True. Commit trước khi sinh dataset thật, '
              'nếu không dataset KHÔNG tái lập được.')
    print('GATE PASS: ma trận đạt mọi tiêu chí thiết kế.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
