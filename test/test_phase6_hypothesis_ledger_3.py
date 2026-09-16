import json
import pytest
from scripts import build_phase6_hypothesis_ledger_3 as L3
from scripts import diag_phase6_iforest_posthoc as D

def ledger(): return json.loads(L3.OUT.read_text())
def diag(): return json.loads(D.OUT.read_text())

def test_ledger_hash_and_drift():
    d=ledger();assert d[L3.HASH_FIELD]==L3.content_hash(d['content']);assert d['content']==L3.current_content()

def test_timing_is_after_test_before_exploration():
    t=ledger()['content']['timing_and_knowledge'];assert t['iforest_campaign_test_scores_seen'] is True;assert t['hybrid_or_exploratory_analysis_started'] is False

def test_all_five_hypotheses_are_refuted():
    s=ledger()['content']['summary'];assert s['all_five_refuted'] is True;assert s['refuted']==['H1','H2','H3','H4','H5']

def test_h1_refuted_by_registered_mean_and_note_preserves_mechanism():
    h=ledger()['content']['hypotheses']['H1'];assert h['status']=='refuted';assert h['evidence']['margin_in_ticks']==pytest.approx(.2);assert h['evidence']['seeds_with_any_detection']==['4'];assert 'threshold failure' in h['note'] and 'not a channel failure' in h['note']

def test_h2_if_clause_is_also_refuted():
    e=ledger()['content']['hypotheses']['H2']['evidence'];assert e['all_iforest_seeds_censored'] is True;assert e['loss_only_delay']==10

def test_h3_refuted_and_trivial_confirmation_did_not_occur():
    h=ledger()['content']['hypotheses']['H3'];assert h['status']=='refuted';assert h['evidence']['iforest_only_ticks_per_seed']=={'0':0,'1':0,'2':0,'3':0,'4':1};assert 'did not occur' in h['note']

def test_old_refuted_decisions_are_not_reopened():
    h=ledger()['content']['hypotheses'];assert all(h[x]['previous_status']=='refuted' and h[x]['status']=='refuted' for x in ('H2','H4','H5'))

def test_diag_hash_and_drift():
    d=diag();assert d[D.HASH_FIELD]==D.content_hash(d['content']);assert d['content']==D.current_content()

def test_tail_inversion_is_unique_to_if_on_common_rows():
    s=diag()['content']['common_comparison']['statistics'];assert [s[x]['fault_tail_exceeds_benign_tail'] for x in ('envelope_excess','envelope_count_k','iforest_neg_score')]==[True,True,False]

def test_registered_threshold_is_below_every_fault_score():
    r=diag()['content']['registered_if_threshold'];assert r['threshold_below_every_fault_score'] is True;assert r['gap']>0

def test_hybrid_adds_no_true_positive_and_five_false_positives():
    o=diag()['content']['operating_point_and_hybrid'];assert o['iforest_unique_true_positives']==0;assert o['added_false_positives']==5;assert o['excess_OR_iforest']['tp']==o['envelope_excess_only']['tp']

def test_diag_declares_exploratory_label_use_and_no_changes():
    c=diag()['content'];assert c['status'].startswith('EXPLORATORY');assert c['uses_test_labels'] is True;assert set(c['authorises_no_change_to'])=={'detector','threshold','hypothesis','column set'}

def test_scripts_refuse_overwrite():
    a=L3.OUT.read_bytes();b=D.OUT.read_bytes();assert L3.main()==1 and D.main()==1;assert L3.OUT.read_bytes()==a and D.OUT.read_bytes()==b
