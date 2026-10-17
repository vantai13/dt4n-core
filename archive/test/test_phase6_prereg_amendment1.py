import json
from scripts import build_phase6_prereg_amendment1 as A

def doc(): return json.loads(A.OUT.read_text())
def test_amendment_hash_and_drift():
    d=doc();assert d[A.HASH_FIELD]==A.content_hash(d['content']);assert d['content']==A.current_content()
def test_amendment_pre_result_and_secondary_only():
    c=doc()['content'];assert c['timing_and_knowledge']['campaign_cv_run'] is False;assert c['timing_and_knowledge']['campaign_detector_test_scores_seen'] is False
    assert c['change_type'].startswith('add secondary');assert c['secondary_detector']['alarm'].startswith('strict')
def test_partition_is_complete_disjoint_and_frozen():
    c=doc()['content']['secondary_detector'];a,b=c['indicator_columns'],c['rate_shared_columns'];assert (len(a),len(b))==(35,36);assert not(set(a)&set(b));assert len(set(a)|set(b))==71
def test_amendment_refuses_overwrite():
    before=A.OUT.read_bytes();assert A.main()==1;assert A.OUT.read_bytes()==before
