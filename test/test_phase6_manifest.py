import json

from scripts import build_phase6_manifest as M


def test_manifest_hash_and_all_inputs_are_bound():
    document = json.loads(M.OUT.read_text())
    assert document[M.HASH_FIELD] == M.content_hash(document['content'])
    assert document['content'] == M.current_content()
    assert set(document['content']['files']) == set(M.FILES)
    assert all(row['valid'] for row in
               document['content']['internal_json_hash_checks'].values())


def test_reproduction_receipt_is_bit_exact_and_deterministic_twice():
    first = M.reproduction_receipt()
    second = M.reproduction_receipt()
    assert M.content_hash(first) == M.content_hash(second)
    assert first['hybrid_five_seed_exact'] is True
    assert first['noise_five_seed_exact'] is True


def test_registration_commit_order_ends_with_ablation_prereg():
    rows = json.loads(M.OUT.read_text())['content']['registration_commit_order']
    assert [row['path'] for row in rows] == M.REGISTRATION_FILES
    assert rows[-1]['path'].endswith('phase6_ablation_prereg.json')
    assert len({row['commit'] for row in rows}) == len(rows)


def test_script_refuses_overwrite():
    before = M.OUT.read_bytes()
    assert M.main() == 1
    assert M.OUT.read_bytes() == before
