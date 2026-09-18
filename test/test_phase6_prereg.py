"""Lesson 6.1 — test ghim tính toàn vẹn của bản đăng ký trước."""
import json
import subprocess

import pytest

from scripts import build_phase6_prereg as P

pytestmark = pytest.mark.skipif(not P.OUT.exists(), reason='chua sinh phase6_prereg.json')


@pytest.fixture(scope='module')
def doc():
    return json.loads(P.OUT.read_text(encoding='utf-8'))


def test_stored_hash_matches_file_content(doc):
    """Ai sua 1 ky tu trong 'content' ma khong cap nhat hash -> do."""
    assert doc[P.HASH_FIELD] == P.content_hash(doc['content'])


def test_no_drift_between_code_data_and_registered_content(doc):
    """Sua script HOAC sua manifest sau khi dang ky -> do (giong check_contract_integrity)."""
    assert P.current_content() == doc['content']


def test_facts_pin_known_numbers(doc):
    f = doc['content']['facts']
    assert (f['n_positive'], f['n_negative'], f['n_negative_control_runs']) == (160, 430, 118)
    assert f['always_normal_accuracy'] == 0.7288
    assert f['unknown']['iforest']['recall_ceiling'] == 0.95
    assert f['unknown']['envelope']['recall_ceiling'] == 0.975
    assert f['n_envelope_if_overlap'] == 36            # KHONG phai tap roi nhau


def test_no_open_decision(doc):
    """Khong con cho de ngo: khong None, khong 'TBD', khong chuoi rong."""
    def walk(x, path='content'):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from walk(v, f'{path}.{k}')
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from walk(v, f'{path}[{i}]')
        else:
            yield path, x
    bad = [p for p, v in walk(doc['content'])
           if v is None or (isinstance(v, str) and (not v.strip() or 'TBD' in v.upper()))]
    assert bad == []


def test_every_hypothesis_is_falsifiable(doc):
    for h in doc['content']['hypotheses']:
        assert h['claim'] and h['mechanism'] and h['refuted_if'], h['id']


def test_contamination_never_from_test_base_rate(doc):
    assert doc['content']['detectors']['iforest']['contamination'] == 'auto'
    assert 'accuracy' in doc['content']['metrics']['forbidden']


def test_thresholds_are_train_quantiles_and_fixed(doc):
    r = doc['content']['decision_rules']['iforest']
    assert r['primary_q'] in r['quantiles'] and 'train' in r['alarm']


def test_prereg_committed_before_any_detector_code():
    """Bang chung THU TU: commit dau tien cua prereg phai som hon ml/detectors."""
    shallow = subprocess.run(
        ['git', 'rev-parse', '--is-shallow-repository'], cwd=P.ROOT,
        check=True, capture_output=True, text=True).stdout.strip()
    if shallow == 'true':
        pytest.skip('git-history ordering requires a full clone')

    def first_addition(path):
        commits = subprocess.run(['git','log','--reverse','--diff-filter=A','--format=%H','--',path], cwd=P.ROOT,check=True,capture_output=True,text=True).stdout.split()
        return commits[0] if commits else None
    prereg = first_addition('results/report/phase6_prereg.json')
    detector = first_addition('ml/detectors')
    if prereg is None:
        pytest.skip('prereg not committed yet')
    if detector is not None:
        assert prereg != detector
        assert subprocess.run(['git','merge-base','--is-ancestor',prereg,detector],cwd=P.ROOT).returncode == 0


def test_tampering_is_detected_without_touching_original(doc):
    import copy
    altered = copy.deepcopy(doc['content'])
    altered['decision_rules']['iforest']['primary_q'] = .02
    assert P.content_hash(altered) != doc[P.HASH_FIELD]


def test_root_parameter_and_manifest_drift_are_real(tmp_path, doc):
    import shutil
    target = tmp_path/'results/report'
    target.mkdir(parents=True)
    for name in ('ml_dataset_split_manifest.json','ground_truth.json','campaign_missing_analysis.json'):
        shutil.copyfile(P.ROOT/'results/report'/name,target/name)
    assert P.current_content(tmp_path) == doc['content']
    path = target/'ml_dataset_split_manifest.json'
    m = json.loads(path.read_text())
    m['build_provenance']['git_hash'] = 'changed-provenance'
    path.write_text(json.dumps(m))
    assert P.current_content(tmp_path) != doc['content']
