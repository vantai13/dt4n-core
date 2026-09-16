#!/usr/bin/env python3
"""Lesson 5.6 — manifest dataset: SHA-256, cột, base rate, quy tắc, đếm NaN.

Usage: python -m scripts.build_dataset_manifest [--root .] [--rolling]

VÌ SAO MANIFEST TÁCH KHỎI DATASET CARD:
    Manifest cho MÁY doc (test tu dong doi chieu). Card cho NGUOI doc (ban
    3 tuan sau, hoi dong). Gop lai thi mot ben luon bi viet do.
"""
import argparse
import json
from pathlib import Path

from ml import campaign as C
from ml import dataset as D
from ml import labels as L


def build(root: Path, use_rolling: bool):
    s = D.load_split(root, use_rolling=use_rolling)
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')

    per_run = {}
    for rid in s.meta['split']['train'] + s.meta['split']['test']:
        p = C.run_paths(rid, root)
        side = json.loads(p['meta'].read_text())
        per_run[rid] = {
            'sha256': side['sha256'],
            'metadata_sha256': C.sha256_file(p['meta']),
            'events_sha256': C.sha256_bytes(C.canonical_json(side['events']).encode()),
            'collection_provenance': side['collection_provenance'],
            'split': side['record']['split'],
            'group': side['record']['group'],
            'fault': side['record'].get('fault'),
            'config_id': D.config_id(side['record']),
            'n_snapshots': side['checks']['n_snapshots'],
            'max_separation': side['checks'].get('max_separation'),
        }

    mp = s.eval_primary.eq(L.EVAL)
    ms = s.eval_sensitivity.eq(L.EVAL)
    manifest = {
        'dataset_version': D.DATASET_VERSION,
        'label_convention_id': L.LABEL_CONVENTION_ID,
        'label_convention': L.LABEL_CONVENTION,
        'design_content_sha256': contract['design_content_sha256'],
        'contract_integrity': C.check_contract_integrity(contract),
        'collector_version': s.meta['collector_version'],
        'runs': per_run,
        'split': s.meta['split'],
        'groups': {'run_id_n': s.meta['groups_train_run_n'],
                   'config_id_n': s.meta['groups_train_config_n'],
                   'recommended_cv': 'GroupKFold(groups=config_id) — '
                                     'leave-one-load-out, kiem chung tong quat '
                                     'sang muc tai chua tung thay'},
        'shape': {'n_train_rows': s.meta['n_train_rows'],
                  'n_test_rows': s.meta['n_test_rows'],
                  'n_features': s.meta['n_features']},
        'feature_names': s.feature_names,       # THỨ TỰ CỐ ĐỊNH — IF phụ thuộc
        'feature_selection': s.meta['feature_selection'],
        'link_stats': s.meta['link_stats'],
        'feature_selection_dropped': s.meta['feature_selection_dropped'],
        'n_features_dropped': s.meta['n_features_dropped'],
        'rules': {
            'warmup': 'bo tick < warmup_ticks moi run (DT4N-M1 tang 1)',
            'missing_train': 'bo dong con NaN o feature, CO DEM (tang 3)',
            'missing_test': 'GIU dong NaN; detector tra "unknown"; tick y=1 '
                            'tinh la FALSE NEGATIVE',
            'no_fillna': 'tuyet doi khong fillna(0) cho lossPct o moi tang',
            'scaler': 'link_stats fit tren TRAIN, transform cho TEST',
            'feature_selection': 'chi luat cau truc + thong ke TRAIN; '
                                 'auc_dist (can nhan test) KHONG duoc dung',
            'time_features': 'delta/rolling luon groupby(run_id) + shift(1)',
        },
        'base_rate': {
            'primary': {'usable': int(mp.sum()),
                        'anomalous': int(s.y_test[mp].sum()),
                        'rate': round(float(s.y_test[mp].mean()), 4),
                        'dumb_always_normal_accuracy':
                            round(1 - float(s.y_test[mp].mean()), 4)},
            'sensitivity': {'usable': int(ms.sum()),
                            'anomalous': int(s.y_test[ms].sum()),
                            'rate': round(float(s.y_test[ms].mean()), 4)},
        },
        'unjudgeable_rows': s.meta['unjudgeable_rows'],
        'unjudgeable_test_ticks': {
            'total': s.meta['n_test_rows_with_nan_feature'],
            'with_fault': s.meta['n_test_rows_with_nan_and_fault'],
            'with_normal': s.meta['n_test_rows_with_nan_and_normal'],
            'accounting': 'tinh la false negative khi y=1; bao cao rieng',
        },
        'missing_policy_train': s.meta['missing_policy_train'],
        'missing_policy_test': s.meta['missing_policy_test'],
        'use_rolling': s.meta['use_rolling'],
        'build_provenance': C.collection_provenance(root),
        'source_sha256': {str(path.relative_to(root)): C.sha256_file(path) for path in [root/'ml/features.py',root/'ml/dataset.py',root/'ml/labels.py',root/'ml/missing.py',root/'ml/flatten.py',root/'ml/schema.py']},
    }
    filename = 'ml_dataset_split_manifest_rolling.json' if use_rolling else 'ml_dataset_split_manifest.json'
    out = root / 'results/report' / filename
    C.atomic_json(out, manifest)
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ('runs', 'feature_names',
                                   'missing_policy_train',
                                   'missing_policy_test')},
                     ensure_ascii=False, indent=2))
    print('-> %s  (%d feature)' % (out, len(s.feature_names)))
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=C.ROOT)
    p.add_argument('--rolling', action='store_true')
    a = p.parse_args()
    return build(a.root.resolve(), a.rolling)


if __name__ == '__main__':
    raise SystemExit(main())
