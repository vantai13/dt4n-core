#!/usr/bin/env python3
"""Create immutable pre-CV amendment 2: freeze fold column identity."""
import json
from datetime import datetime, timezone

from ml.campaign import ROOT, canonical_json, sha256_bytes

OUT = ROOT / 'results/report/phase6_prereg_amendment_2.json'
A1 = ROOT / 'results/report/phase6_prereg_amendment_1.json'
HASH_FIELD = 'amendment_content_sha256'


def content_hash(value):
    return sha256_bytes(canonical_json(value).encode('utf-8'))


def current_content():
    amendment1 = json.loads(A1.read_text(encoding='utf-8'))
    if content_hash(amendment1['content']) != amendment1[HASH_FIELD]:
        raise ValueError('amendment 1 was modified')
    return {
        'amendment_id': 'DT4N-P6-PREREG-AMENDMENT-2',
        'amends': [amendment1['content']['amends_prereg_id'],
                   amendment1['content']['amendment_id']],
        'amends_prereg_content_sha256': amendment1['content']['amends_prereg_content_sha256'],
        'amendment_1_content_sha256': amendment1[HASH_FIELD],
        'timing_and_knowledge': {
            'campaign_cv_run': False,
            'campaign_detector_test_scores_seen': False,
        },
        'change_type': 'clarification of ambiguous wording; no detector, threshold rule or hypothesis changed',
        'clarifications': {
            'fold_column_identity': 'Column lists stay frozen (71 primary; 35/36 dual; 8 loss-only) in every fold. Fold refit = link_stats for agg.rate_absz_* and min/max bounds on fold-train. select_features is NOT re-run to change columns; a column constant on fold-train keeps bounds [c,c]. Per-fold count of such columns is reported as diagnostic.',
            'why': 'K must be comparable with the final 71-column detector; per-fold column sets would change the scale of k.',
            'h4_envelope_rate': 'share of JUDGEABLE held-out rows with primary k>0, per fold, uncalibrated.',
            'two_stage_execution': 'Stage cv writes phase6_envelope_cv.json from train only; it is committed before stage test may run; stage test refuses if CV file, detector code or registrations are uncommitted, modified, or if results exist.',
        },
        'known_risk_declared_before_cv': 'Under iid noise a new point falls outside the min/max of n fit points with probability 2/(n+1). Low-end folds may therefore show k>0 without extrapolation in load; H4 stays unchanged and may be refuted.',
    }


def main():
    if OUT.exists():
        print('[amendment2] exists; refusing overwrite')
        return 1
    content = current_content()
    document = {
        'written_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'content': content,
        HASH_FIELD: content_hash(content),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2)
        handle.write('\n')
    print('[amendment2] SHA:', document[HASH_FIELD])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
