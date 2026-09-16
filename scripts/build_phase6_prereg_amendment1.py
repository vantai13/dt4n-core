#!/usr/bin/env python3
"""Create immutable pre-result amendment 1: secondary dual-count envelope."""
import json
from datetime import datetime, timezone
from pathlib import Path
from ml.campaign import ROOT, atomic_json, canonical_json, sha256_bytes, sha256_file

OUT=ROOT/'results/report/phase6_prereg_amendment_1.json'
PREREG=ROOT/'results/report/phase6_prereg.json'
MANIFEST=ROOT/'results/report/ml_dataset_split_manifest.json'
HASH_FIELD='amendment_content_sha256'

def content_hash(x): return sha256_bytes(canonical_json(x).encode())
def current_content(root=ROOT):
    prereg=json.loads((root/'results/report/phase6_prereg.json').read_text())
    manifest=json.loads((root/'results/report/ml_dataset_split_manifest.json').read_text())
    env=set(manifest['envelope_feature_names']); if_raw=set(manifest['feature_names']) & env
    indicator=sorted(env-if_raw); shared=sorted(if_raw)
    if len(indicator)!=35 or len(shared)!=36 or set(indicator)&set(shared) or set(indicator)|set(shared)!=env:
        raise ValueError('envelope partition drift')
    return {'amendment_id':'DT4N-P6-PREREG-AMENDMENT-1',
      'amends_prereg_id':prereg['content']['prereg_id'],
      'amends_prereg_content_sha256':prereg['prereg_content_sha256'],
      'bound_to':{'original_tag':'phase6-prereg','original_sealed_commit':'003947410c8de52dd8771f802c55a3b54bde07d9',
                  'split_manifest_sha256':sha256_file(root/'results/report/ml_dataset_split_manifest.json')},
      'timing_and_knowledge':{'campaign_cv_run':False,'campaign_detector_test_scores_seen':False,
        'known':'Phase5 envelope bounds and registered metadata only; design review identified common K may be dominated by rate extrapolation.'},
      'reason':'One common count threshold mixes 35 normally-silent indicators with 36 load-sensitive shared rate/count columns; held-out load extrapolation can raise K and suppress small indicator violations.',
      'change_type':'add secondary analysis; original primary envelope and H1-H5 remain unchanged',
      'secondary_detector':{
        'name':'envelope_dual_count_secondary','indicator_columns':indicator,'rate_shared_columns':shared,
        'partition_rule':'indicator=envelope minus raw IF/envelope overlap; rate_shared=the 36 raw columns in both envelope and IF; lists frozen here',
        'folds':'same GroupKFold(config_id,n_splits=4,shuffle=False); refit preprocessing and bounds on fold-train only',
        'calibration':'For each judgeable held-out row compute strict counts k_ind and k_rate. K_ind=max k_ind and K_rate=max k_rate pooled across four held-out folds. Stop if a fold has no judgeable row; no fallback.',
        'final_fit':'refit bounds on all 472 normal rows; keep held-out K_ind/K_rate in Phase6 model artifact',
        'judgeable':'true only when all 71 selected values are finite; otherwise unknown under original policy',
        'alarm':'strict (k_ind > K_ind) OR (k_rate > K_rate); equality is no alarm',
        'metrics':'same prereg masks, unknown accounting, FPR breakdown, delay and bootstrap; report beside primary, never select by test result'},
      'interpretation':'If primary misses admin_down and this secondary catches it, report a calibration-family interaction; do not replace primary or rewrite H1.',
      'deviation_policy':'This artifact is immutable after commit. Further change requires a numbered amendment.'}

def main():
    if OUT.exists(): print('[amendment1] exists; refusing overwrite');return 1
    content=current_content();doc={'written_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'content':content,HASH_FIELD:content_hash(content)}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open('x') as f: json.dump(doc,f,indent=2);f.write('\n')
    print('[amendment1] SHA:',doc[HASH_FIELD]);return 0
if __name__=='__main__': raise SystemExit(main())
