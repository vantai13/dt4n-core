#!/usr/bin/env python3
"""
gd4_retrain.py — GĐ4: học lại MỌI tham số lấy từ dữ liệu train, train thu trên một máy.

THAY ĐỔI DUY NHẤT so với 1.0.0: tập train bỏ N-vary-s1008-r2 (h1, h3 không gửi) và thêm
N-vary-s1008-r4 (cùng record, thu lại trên máy GCP, qua cổng client_traffic). Tám run train
vì vậy cùng một máy với tập test Phase 5 và đợt nghiệm thu.

HỌC LẠI (cùng code, cùng luật như lúc dựng 1.0.0):
  - envelope: biên min/max, link_stats, K và E theo kiểm chéo bỏ một cấu hình
    (đường code ml.gd2_envelope.fit_and_evaluate, chỉ thay nguồn train);
  - residual R = max r_max trên mọi dòng train (scripts/build_phase6r_amendment1.calibrate);
  - kiểm lại ngưỡng vùng vận hành T = max g (ml.operating_range.g) và trần tải hợp lệ
    của máy khách mà mức giới hạn 7 Mbps phải vượt.
KHÔNG ĐỔI: cột, thuật toán, FSM (n_act 2, release 3, cooldown 8 s), luật ức chế, bảng
định tuyến, collector_version.

Phiên bản ghi ra (write-once):
  models/envelope-2.1.0.json, results/report/gd4_conservation.json (conservation-2.1.0),
  models/detector-release-2.1.0.json, results/report/gd4_retrain.json

LƯU Ý TRUNG THỰC: tập test Phase 5 đã mở từ Phase 6; số trên tập đó chỉ mô tả. Bằng chứng
của bản 2.1 là đợt nghiệm thu gd4r thu SAU khi bản này được khóa.

    python3 -m ml.gd4_retrain build
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ml import campaign as C
from ml import gd2_envelope as GE
from ml import gd4campaign as G4
from ml import operating_range as OR
from ml.missing import apply_policy

VERSION = '2.1.0'
ENVELOPE_OUT = 'models/envelope-%s.json' % VERSION
CONSERVATION_OUT = 'results/report/gd4_conservation.json'
RELEASE_OUT = 'models/detector-release-%s.json' % VERSION
SUMMARY_OUT = 'results/report/gd4_retrain.json'
CLAMP_LIMIT_MBPS = 7.0           # controller/policy.py: mức giới hạn của vòng kín


# ---------------------------------------------------------------- nguồn train
def gd4_source(root: Path):
    contract = G4.load_contract(root / G4.CONTRACT_REL)
    G4.check_integrity(contract, root)
    return contract, (lambda rid: G4.run_paths(rid, root)), root / G4.MANIFEST_REL


def load_raw(variant: str, root: Path):
    """(train_raw, test_raw, warmup, train_ids): 7 run Phase 5 + r4 (gd4)."""
    if variant != 'v21':
        return GE.load_variant_raw(variant, root)
    p5, p5_paths, p5_manifest = GE.phase5_source(root)
    g4, g4_paths, g4_manifest = gd4_source(root)
    if g4['constants'] != p5['constants']:
        raise RuntimeError('hằng số gd4 khác Phase 5')
    warmup = int(p5['constants']['warmup_ticks'])
    keep = [r for r in p5['split']['train'] if r != GE.BAD_RUN]
    train_raw = pd.concat([GE.load_frames(p5, keep, p5_paths, p5_manifest),
                           GE.load_frames(g4, [G4.NEW_RUN], g4_paths, g4_manifest)],
                          ignore_index=True, sort=False)
    test_raw = GE.load_frames(p5, list(p5['split']['test']), p5_paths, p5_manifest)
    versions = set(train_raw.collector_version) | set(test_raw.collector_version)
    if versions != {p5['constants']['collector_version']}:
        raise RuntimeError('trộn collector_version: %s' % versions)
    return train_raw, test_raw, warmup, keep + [G4.NEW_RUN]


def train_paths(root: Path) -> list[Path]:
    p5 = C.load_contract(root / GE.P5_CONTRACT)
    keep = [r for r in p5['split']['train'] if r != GE.BAD_RUN]
    return [C.run_paths(r, root)['final'] for r in keep] + \
        [G4.run_paths(G4.NEW_RUN, root)['final']]


# ---------------------------------------------------------------- residual R
def conservation_calibration(train_raw: pd.DataFrame, warmup: int) -> dict:
    """Đúng luật amendment 1: R = max r_max trên dòng train, kèm owner."""
    from scripts.build_phase6r_amendment1 import calibrate
    train, _ = apply_policy(train_raw, warmup_ticks=warmup)
    train = train.sort_values(['run_id', 'tick']).reset_index(drop=True)
    return calibrate(train)


def conservation_document(calibration: dict, root: Path) -> dict:
    """Cùng hình dạng amendment 1 ở những khóa ConservationLayer.load đọc."""
    a1 = json.loads((root / 'results/report/phase6r_amendment_1.json').read_text())
    content = {
        'version': 'conservation-%s' % VERSION,
        'replaces': {'name': 'conservation-1.0.0',
                     'document': 'results/report/phase6r_amendment_1.json',
                     'content_sha256': a1['content_sha256'],
                     'R': a1['content']['calibration']['R'],
                     'owner': a1['content']['calibration']['owner']},
        'detector': a1['content']['detector'],
        'calibration': calibration,
        'train_run_ids': None,
        'built_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    return content


# ---------------------------------------------------------------- vùng vận hành
def operating_numbers(paths) -> dict:
    """T = max g (sàn tải máy khách) và trần txRate hợp lệ của máy khách trên train."""
    best_g, g_owner, ceiling, c_owner, per_run = -1.0, None, -1.0, None, {}
    for path in paths:
        run_id = Path(path).name[:-len('.jsonl')]
        run_g = run_c = None
        for index, snapshot in enumerate(OR.read_run(path)):
            value = OR.g(snapshot)
            if value is not None:
                run_g = value if run_g is None else max(run_g, value)
                if value > best_g:
                    best_g, g_owner = value, {'run_id': run_id, 'tick': snapshot.get('tick')}
            for name, thing in (snapshot.get('things') or {}).items():
                attrs = thing.get('attributes') or {}
                traffic = (thing.get('features') or {}).get('traffic') or {}
                if attrs.get('role') != 'client' or traffic.get('rateValid') is not True:
                    continue
                mbps = float(traffic.get('txRate')) * 8.0 / 1e6
                run_c = mbps if run_c is None else max(run_c, mbps)
                if mbps > ceiling:
                    ceiling, c_owner = mbps, {'run_id': run_id, 'tick': index,
                                              'host': name.split(':')[-1]}
        per_run[run_id] = {'max_g_mbps': None if run_g is None else round(run_g, 6),
                           'max_client_tx_mbps': None if run_c is None else round(run_c, 6)}
    return {'operating_range_T_mbps': best_g, 'T_owner': g_owner,
            'client_tx_ceiling_mbps': round(ceiling, 6), 'ceiling_owner': c_owner,
            'clamp_limit_mbps': CLAMP_LIMIT_MBPS,
            'clamp_above_ceiling': CLAMP_LIMIT_MBPS > ceiling, 'per_run': per_run}


# ---------------------------------------------------------------- phát hành
def release_document(envelope_sha: str, conservation_sha: str, root: Path) -> dict:
    v1 = json.loads((root / 'models/detector-release-1.0.0.json').read_text())['content']
    content = dict(v1)
    content['version'] = 'detector-release-%s' % VERSION
    content['components'] = {
        'envelope': {'name': 'envelope-%s' % VERSION, 'path': ENVELOPE_OUT,
                     'content_sha256': envelope_sha},
        'conservation': {'name': 'conservation-%s' % VERSION, 'path': CONSERVATION_OUT,
                         'content_sha256': conservation_sha},
    }
    content['decided_by'] = {'gd4': 'chỉ đổi dữ liệu train (ml/gd4_retrain.py); FSM, luật '
                                    'ức chế, định tuyến, collector giữ như 1.0.0'}
    content['channels'] = {
        'envelope': {'drives': ['suspect', 'act']},
        'conservation': {'drives': ['suspect'], 'note': 'không bao giờ dẫn tới act'},
    }
    return content


def _write_once(path: Path, doc) -> None:
    if path.exists():
        raise SystemExit('Đã tồn tại, không ghi đè: %s' % path)
    C.atomic_json(path, doc)


def _sealed(content: dict) -> dict:
    return {'content': content,
            'content_sha256': C.sha256_bytes(C.canonical_json(content).encode('utf-8'))}


def build(root: Path) -> dict:
    from ml.release import DetectorRelease
    for rel in (ENVELOPE_OUT, CONSERVATION_OUT, RELEASE_OUT, SUMMARY_OUT):
        if (root / rel).exists():
            raise SystemExit('Đã tồn tại, không ghi đè: %s' % rel)
    rep = GE.reproduce_check(root)
    if not rep['match']:
        raise SystemExit('Không tái lập được v1 -> dừng: %s' % rep['mismatches'])

    results = [GE.fit_and_evaluate(v, root, loader=load_raw) for v in ('v1', 'v2', 'v21')]
    v21 = results[2]
    content, model = GE.build_artifact(v21, root)
    content['version'] = 'envelope-%s' % VERSION
    content['provenance'].update({
        'replaces': 'envelope-1.0.0',
        'change': ('train: bỏ %s (h1, h3 txRate = 0), thêm %s (thu lại trên máy GCP, qua '
                   'cổng client_traffic)' % (GE.BAD_RUN, G4.NEW_RUN)),
        'gd4_code_sha256': C.sha256_file(root / 'ml/gd4_retrain.py'),
        'scope_note': ('Bản cho nghiệm thu gd4r. Vòng kín Phase 8 KHÔNG chạy lại, vẫn gắn '
                       'với 1.0.0.'),
    })
    model = type(model)(content)
    model._check_content(content)

    train_raw, _, warmup, used = load_raw('v21', root)
    calibration = conservation_calibration(train_raw, warmup)
    cons = conservation_document(calibration, root)
    cons['train_run_ids'] = used
    cons_doc = _sealed(cons)

    rel = release_document(model.content_sha256, cons_doc['content_sha256'], root)
    rel_doc = _sealed(rel)

    numbers = operating_numbers(train_paths(root))
    v1_numbers = operating_numbers(
        [C.run_paths(r, root)['final'] for r in
         C.load_contract(root / GE.P5_CONTRACT)['split']['train']])

    cmp = GE.compare(results)
    summary = {
        'version': VERSION,
        'train_run_ids': used,
        'envelope': {
            'thresholds_v1': results[0]['thresholds'],
            'thresholds_v21': v21['thresholds'],
            'owners_v21': v21['owners'],
            'content_sha256': model.content_sha256,
        },
        'conservation': {
            'R_v1': cons['replaces']['R'], 'owner_v1': cons['replaces']['owner'],
            'R_v21': calibration['R'], 'owner_v21': calibration['owner'],
            'r_max_by_config_v21': calibration['r_max_by_config'],
            'content_sha256': cons_doc['content_sha256'],
        },
        'operating_range': {'v1_train': v1_numbers, 'v21_train': numbers},
        'release_content_sha256': rel_doc['content_sha256'],
        'compare_on_phase5_test_descriptive': cmp,
        'note': ('Tập test Phase 5 đã mở từ Phase 6: các số so sánh chỉ là MÔ TẢ. Bản 2.1 '
                 'được nghiệm thu trên đợt gd4r thu sau khi bản này khóa.'),
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }

    _write_once(root / ENVELOPE_OUT, {'content': content,
                                      'content_sha256': model.content_sha256})
    _write_once(root / CONSERVATION_OUT, cons_doc)
    _write_once(root / RELEASE_OUT, rel_doc)
    DetectorRelease.load(root / RELEASE_OUT)          # kiểm chéo mọi thành phần
    _write_once(root / SUMMARY_OUT, _sealed(summary))
    return summary


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ['build']:
        print(__doc__)
        return 2
    s = build(C.ROOT)
    e1, e2 = s['envelope']['thresholds_v1'], s['envelope']['thresholds_v21']
    print('K (rate_shared): %d -> %d   E (primary): %.4f -> %.4f' % (
        e1['rate_shared']['K'], e2['rate_shared']['K'], e1['primary']['E'], e2['primary']['E']))
    print('R: %.6f (%s) -> %.6f (%s)' % (
        s['conservation']['R_v1'], s['conservation']['owner_v1']['run_id'],
        s['conservation']['R_v21'], s['conservation']['owner_v21']['run_id']))
    o1, o2 = s['operating_range']['v1_train'], s['operating_range']['v21_train']
    print('T vùng vận hành: %.4f -> %.4f Mbps; trần máy khách: %.4f -> %.4f Mbps '
          '(giới hạn 7 Mbps vẫn cao hơn: %s)' % (
              o1['operating_range_T_mbps'], o2['operating_range_T_mbps'],
              o1['client_tx_ceiling_mbps'], o2['client_tx_ceiling_mbps'],
              o2['clamp_above_ceiling']))
    GE.print_compare(s['compare_on_phase5_test_descriptive'])
    print('\nrelease 2.1.0 sha %s…' % s['release_content_sha256'][:12])
    return 0


if __name__ == '__main__':
    sys.exit(main())
