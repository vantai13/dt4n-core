import json

from scripts import run_phase6_ablations as A


def test_column_sets_are_frozen_and_distinct():
    columns = A.ablation_columns(A.IR.frozen_columns_from_manifest())
    assert len(columns['A1_drop_delta']) == 36
    assert len(columns['A3_raw_no_agg']) == 34
    assert not any(column.startswith('d1.') for column in columns['A1_drop_delta'])
    assert not any(column.startswith('agg.') for column in columns['A3_raw_no_agg'])


def test_ablation_artifact_hash_and_drift():
    document = json.loads(A.OUT.read_text())
    assert document[A.HASH_FIELD] == A.content_hash(document['content'])
    assert document['content'] == A.current_content()


def test_all_seeds_and_registered_decisions_are_present():
    content = json.loads(A.OUT.read_text())['content']
    for key in ('A1_drop_delta', 'A3_raw_no_agg'):
        assert sorted(content[key]['per_seed']) == ['0', '1', '2', '3', '4']
    assert sorted(content['A2_rolling_window3']['iforest']['per_seed']) == ['0','1','2','3','4']
    assert set(content['decisions']) == {'A1', 'A2', 'A3', 'A4'}


def test_script_refuses_overwrite():
    before = A.OUT.read_bytes()
    assert A.main() == 1
    assert A.OUT.read_bytes() == before
