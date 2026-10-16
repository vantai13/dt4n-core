#!/usr/bin/env python3
"""
gd4_score.py — GĐ4: chấm một detector release trên một đợt nghiệm thu (6R hoặc gd4r).

Dùng ĐÚNG đường chấm của 6R (scripts/run_phase6r_acceptance.py): FastOnlineScorer ở chế
độ conservation 'shadow', FSM riêng cho từng kênh (ml.acceptance_pass.specs_for), một lần
quét mỗi run (run_one), rồi các hàm thuần của ml.acceptance_metrics cho S1, S2, S4, S10 và
rho. Không chấm các gate phát hành (cần receipt vòng kín), không chấm S7.

Trước khi mở gd4r, script phải tái lập đúng số 6R đã công bố:
    python3 scripts/gd4_score.py --release models/detector-release-1.0.0.json --set 6r \
        --raw-dir ~/dt4n-data/phase6r_raw --check-6r --out /tmp/v1_on_6r.json

Chấm chính (một lần, sau khi gd4r thu xong):
    python3 scripts/gd4_score.py --release models/detector-release-2.1.0.json --set gd4r \
        --out results/report/gd4_acceptance.json
"""
from __future__ import annotations

import argparse
import json
import operator
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402
from ml.acceptance_guard import SnapshotReader  # noqa: E402
from ml.acceptance_metrics import incident, residual_run, s1_s4, s2_s3, s10  # noqa: E402
from ml.acceptance_pass import _num, run_one, specs_for  # noqa: E402
from ml.blast_radius import Routing  # noqa: E402
from ml.fsm import DetectorFSM, FSMParams  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from ml.serve_fast import FastOnlineScorer  # noqa: E402

REPORT = C.ROOT / 'results/report'
SETS = {
    '6r': {'contract': 'phase6r_rcampaign_matrix.json',
           'manifest': 'phase6r_rcampaign_manifest.json', 'raw': 'data/phase6r/raw'},
    'gd4r': {'contract': 'gd4r_contract.json',
             'manifest': 'gd4r_manifest.json', 'raw': 'data/phase5/gd4r/raw'},
}
CHANNELS = ('envelope_only', 'combined')
PASS_CONSERVATION_MODE = 'shadow'      # như prereg 6R: kênh được tách bằng DERIVE
OPS = {'>=': operator.ge, '<=': operator.le}


def probes_for(record: dict) -> dict:
    """Như run_phase6r_acceptance: txRate của link bị giảm, đọc từ chính snapshot."""
    target = record.get('fault_target')
    if record.get('fault') != 'degrade' or not target:
        return {}
    column = 'link-%s.traffic.txRate' % target
    return {'target_tx': lambda flat, column=column: _num(flat.get(column))}


def _content(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding='utf-8'))
    return doc['content'] if 'content' in doc else doc


def score(release_path: Path, set_name: str, raw_dir: Path | None) -> dict:
    spec = SETS[set_name]
    release = DetectorRelease.load(release_path)
    contract = json.loads((REPORT / spec['contract']).read_text(encoding='utf-8'))
    manifest = _content(REPORT / spec['manifest'])
    if not manifest.get('complete'):
        raise SystemExit('đợt %s chưa thu xong: %s' % (set_name, spec['manifest']))
    raw = Path(raw_dir) if raw_dir else C.ROOT / spec['raw']
    records = {r['run_id']: r for r in contract['runs']}
    groups = {}
    for record in contract['runs']:
        groups.setdefault(record['group'], []).append(record['run_id'])
    order = [r['run_id'] for r in sorted(contract['runs'], key=lambda r: r['exec_index'])]

    params = FSMParams(**release.content['fsm_params'])
    routing = Routing.load(C.ROOT / 'ditto/routing_table.json')
    version = release.content['collector_version']
    threshold = release.conservation.threshold
    reader = SnapshotReader({k: v['sha256'] for k, v in manifest['runs'].items()})

    traces, metas = {}, {}
    for run_id in order:
        meta = json.loads((raw / (run_id + '.meta.json')).read_text(encoding='utf-8'))
        snapshots = reader.read_once(run_id, raw / (run_id + '.jsonl'))
        record = records[run_id]
        if meta['record'] != record:
            raise ValueError('sidecar lệch record hợp đồng: %s' % run_id)
        specs = specs_for(record['group'], meta, routing,
                          lambda log: DetectorFSM(params, log))
        scorer = FastOnlineScorer(release.model, expected_collector_version=version,
                                  conservation=release.conservation,
                                  conservation_mode=PASS_CONSERVATION_MODE)
        traces[run_id] = run_one(run_id, snapshots, scorer, specs, threshold,
                                 probes=probes_for(record))
        metas[run_id] = meta

    rd, rs, rn = groups['RD'], groups['RS'], groups['RN']
    per_run = {rid: residual_run(traces[rid], metas[rid]) for rid in rd}
    rho = {rid: per_run[rid]['rho'] for rid in rd}
    out = {'S1_S4': {}, 'S2_S3': {}, 'S10': {}, 'by_rho': {}}
    for channel in CHANNELS:
        incidents = {rid: incident(traces[rid], metas[rid], '%s@with_log' % channel)
                     for rid in rd}
        out['S1_S4'][channel] = {'summary': s1_s4(incidents), 'per_incident': incidents}
        out['S2_S3'][channel] = s2_s3([traces[r] for r in rs], '%s@no_log' % channel)
        out['S10'][channel] = {rid: s10(traces[rid], '%s@no_log' % channel) for rid in rn}
        hi = [r for r in rd if rho[r] is not None and rho[r] >= 1.10]
        lo = [r for r in rd if rho[r] is not None and rho[r] <= 0.90]
        out['by_rho'][channel] = {
            'rho_ge_1_10': [sum(incidents[r]['detected'] for r in hi), len(hi)],
            'rho_le_0_90': [sum(incidents[r]['detected'] for r in lo), len(lo)],
        }
    out['residual_per_run'] = per_run
    out['process'] = {
        'release': release.version, 'release_sha256': release.sha256,
        'set': set_name, 'contract_sha256': contract['design_content_sha256'],
        'n_files_read': reader.n_files_read, 'n_runs_scored': len(order),
        'pass_conservation_mode': PASS_CONSERVATION_MODE,
        'groups': {g: len(v) for g, v in groups.items()},
    }
    return out


def verdicts(result: dict) -> dict:
    slo = {s['id']: s for s in _content(REPORT / 'phase6r_slo.json')['slo']}
    env, comb = result['S1_S4']['envelope_only'], result['S1_S4']['combined']

    def judge(sid, value):
        target = slo[sid]['target']
        if value is None:
            return 'NO_VALUE'
        return 'PASS' if OPS[target['op']](value, target['value']) else 'FAIL'

    s1 = env['summary']['detection_rate']
    s2 = result['S2_S3']['envelope_only']['rate_upper_per_hour']
    s4 = env['summary']['t_detect_p95_ms']
    return {
        'S1': {'value': s1, 'target': slo['S1']['target'], 'verdict': judge('S1', s1),
               'combined_descriptive': comb['summary']['detection_rate'],
               'by_rho': result['by_rho']},
        'S2': {'value': s2, 'target': slo['S2']['target'], 'verdict': judge('S2', s2),
               'combined_value': result['S2_S3']['combined']['rate_upper_per_hour'],
               'exposure_hours': result['S2_S3']['envelope_only'].get('exposure_hours')},
        'S4': {'value_ms': s4, 'target': slo['S4']['target'], 'verdict': judge('S4', s4),
               'combined_value_ms': comb['summary']['t_detect_p95_ms']},
        'S10': {'verdict': 'REPORT_ONLY', 'envelope_only': {
            rid: {'alarm_ticks': v['alarm_ticks'], 'fp_strict': v['col_a']['fp_ticks'],
                  'fp_sensitive': v['col_b']['fp_ticks'], 'fp_residual': v['col_c']['fp_ticks']}
            for rid, v in result['S10']['envelope_only'].items()}},
    }


def check_6r(v: dict) -> list:
    """So với phase6r_verdicts.json (bản 1.0.0 trên 25 run 6R): phải khớp tuyệt đối."""
    pub = _content(REPORT / 'phase6r_verdicts.json')['slo']
    pairs = [
        ('S1', v['S1']['value'], pub['S1']['value']),
        ('S1 combined', v['S1']['combined_descriptive'], pub['S1']['combined_descriptive']),
        ('S1 by rho env', v['S1']['by_rho']['envelope_only'],
         pub['S1']['posthoc_stratified_by_rho']['envelope_only']),
        ('S1 by rho comb', v['S1']['by_rho']['combined'],
         pub['S1']['posthoc_stratified_by_rho']['combined']),
        ('S2', v['S2']['value'], pub['S2']['value']),
        ('S2 combined', v['S2']['combined_value'], pub['S2']['combined_value']),
        ('S2 exposure', v['S2']['exposure_hours'], pub['S2']['exposure_hours']),
        ('S4', v['S4']['value_ms'], pub['S4']['value_ms']),
        ('S4 combined', v['S4']['combined_value_ms'], pub['S4']['combined_value_ms']),
        ('S10', v['S10']['envelope_only'], pub['S10']['envelope_only']),
    ]
    return ['%s: %r != công bố %r' % (name, mine, theirs)
            for name, mine, theirs in pairs if mine != theirs]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', required=True)
    ap.add_argument('--set', choices=sorted(SETS), required=True)
    ap.add_argument('--raw-dir')
    ap.add_argument('--out', required=True)
    ap.add_argument('--check-6r', action='store_true')
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % out)
    result = score(Path(args.release), args.set, args.raw_dir)
    content = {'verdicts': verdicts(result), 'result': result,
               'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    if args.check_6r:
        mismatches = check_6r(content['verdicts'])
        content['check_6r'] = {'match': not mismatches, 'mismatches': mismatches}
    C.atomic_json(out, {'content': content, 'content_sha256': C.sha256_bytes(
        C.canonical_json(content).encode('utf-8'))})
    v = content['verdicts']
    print('%s trên %s' % (result['process']['release'], args.set))
    print('S1 %s %s (combined %s) | theo rho env %s' % (
        v['S1']['value'], v['S1']['verdict'], v['S1']['combined_descriptive'],
        v['S1']['by_rho']['envelope_only']))
    print('S2 %s %s (combined %s, %s giờ)' % (
        v['S2']['value'], v['S2']['verdict'], v['S2']['combined_value'],
        v['S2']['exposure_hours']))
    print('S4 %s ms %s (combined %s ms)' % (
        v['S4']['value_ms'], v['S4']['verdict'], v['S4']['combined_value_ms']))
    for rid, x in v['S10']['envelope_only'].items():
        print('S10 %-26s alarm %3d  fp_strict %3d' % (rid, x['alarm_ticks'], x['fp_strict']))
    if args.check_6r:
        print('Tái lập 6R: %s' % ('✅ KHỚP' if content['check_6r']['match'] else '❌ LỆCH'))
        for m in content['check_6r']['mismatches']:
            print('  - ' + m)
        return 0 if content['check_6r']['match'] else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
