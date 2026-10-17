import json

from ml.detectors import iforest as F
from scripts import build_phase6_ablation_prereg as P


def test_ablation_prereg_hash_and_drift():
    document = json.loads(P.OUT.read_text())
    assert document[P.HASH_FIELD] == P.content_hash(document['content'])
    assert document['content'] == P.current_content()


def test_ablation_prereg_freezes_seeds_and_unseen_results():
    content = json.loads(P.OUT.read_text())['content']
    assert content['fixed_protocol']['seeds'] == list(F.SEEDS)
    assert content['knowledge_state']['A1_A2_A3_results_seen'] is False
    assert content['written_before_running_any_A1_A3_ablation'] is True
    assert set(content['ablations']) == {
        'A1_drop_delta', 'A2_rolling_window3', 'A3_raw_no_agg',
        'A4_mask_sensitivity'}


def test_script_refuses_overwrite():
    before = P.OUT.read_bytes()
    assert P.main() == 1
    assert P.OUT.read_bytes() == before
