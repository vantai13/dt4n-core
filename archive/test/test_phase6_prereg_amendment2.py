import json

from scripts import build_phase6_prereg_amendment2 as A


def document():
    return json.loads(A.OUT.read_text(encoding='utf-8'))


def test_amendment_hash_and_drift():
    doc = document()
    assert doc[A.HASH_FIELD] == A.content_hash(doc['content'])
    assert doc['content'] == A.current_content()


def test_amendment_is_pre_cv_and_pre_test():
    timing = document()['content']['timing_and_knowledge']
    assert timing == {'campaign_cv_run': False,
                      'campaign_detector_test_scores_seen': False}


def test_amendment_freezes_fold_columns_without_changing_hypotheses():
    content = document()['content']
    assert content['change_type'].startswith('clarification')
    assert '71 primary; 35/36 dual; 8 loss-only' in content['clarifications']['fold_column_identity']
    assert 'H4 stays unchanged' in content['known_risk_declared_before_cv']


def test_amendment_refuses_overwrite():
    before = A.OUT.read_bytes()
    assert A.main() == 1
    assert A.OUT.read_bytes() == before
