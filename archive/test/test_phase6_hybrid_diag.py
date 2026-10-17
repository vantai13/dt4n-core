import json

import numpy as np
import pytest

from scripts import diag_phase6_hybrid as H


def test_combine_flags_implements_registered_or_unknown_rule():
    combined = H.combine_flags(
        [False, True, False, False], [False, False, True, False],
        [True, True, False, False], [False, True, True, False])
    assert combined['excess_or_iforest']['alarm'].tolist() == [False, True, True, False]
    assert combined['excess_or_iforest']['judgeable'].tolist() == [True, True, True, False]
    assert combined['excess_and_iforest']['alarm'].tolist() == [False] * 4
    assert combined['common_judgeable'].tolist() == [False, True, False, False]


def test_combine_flags_rejects_alarm_on_unknown_member():
    with pytest.raises(ValueError, match='unjudgeable'):
        H.combine_flags([True], [False], [False], [True])


def test_combine_flags_rejects_bad_shapes():
    with pytest.raises(ValueError, match='equal-length'):
        H.combine_flags([False], [False, True], [True], [True])


def test_live_hybrid_artifact_hash_and_drift():
    document = json.loads(H.OUT.read_text())
    assert document[H.HASH_FIELD] == H.content_hash(document['content'])
    assert document['content'] == H.current_content()


def test_all_five_seeds_reproduce_signed_tp_fp_exactly():
    content = json.loads(H.OUT.read_text())['content']
    assert content['all_five_seeds_reproduced_exactly'] is True
    assert len(content['per_seed']) == 5
    assert all(row['reconstruction_check']['tp_fp_bit_exact']
               for row in content['per_seed'].values())


def test_iforest_adds_no_tp_and_adds_four_or_five_fp_each_seed():
    per_seed = json.loads(H.OUT.read_text())['content']['per_seed']
    assert [per_seed[str(seed)]['iforest_unique_true_positives']
            for seed in range(5)] == [0, 0, 0, 0, 0]
    assert [per_seed[str(seed)]['added_false_positives']
            for seed in range(5)] == [5, 4, 4, 5, 5]


def test_or_recall_equals_excess_recall_for_every_seed():
    per_seed = json.loads(H.OUT.read_text())['content']['per_seed']
    for row in per_seed.values():
        variants = row['primary_all_rows']
        assert (variants['excess_or_iforest']['scores']['recall'] ==
                variants['excess']['scores']['recall'])
        assert (variants['excess_or_iforest']['scores']['fpr'] >
                variants['excess']['scores']['fpr'])


def test_hybrid_follows_frozen_ledger_3():
    content = json.loads(H.OUT.read_text())['content']
    ledger = json.loads(H.LEDGER_3.read_text())
    assert content['follows_ledger_3_sha256'] == ledger['ledger_content_sha256']
    assert content['n_rows'] == 590
    assert content['n_common_judgeable_rows'] == 564


def test_script_refuses_overwrite():
    before = H.OUT.read_bytes()
    assert H.main() == 1
    assert H.OUT.read_bytes() == before
