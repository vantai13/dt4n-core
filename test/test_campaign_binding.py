#!/usr/bin/env python3
"""Runner/launcher đa chiến dịch và runtime R-campaign."""
from __future__ import annotations

import inspect
import json

import pytest

from ml import campaign as C
from ml import campaign_binding as B
from ml import rcampaign as R
from ml import rcampaign_runtime as RT
from scripts import generate_ml_dataset as runner
from scripts import launch_ml_dataset as launcher


@pytest.fixture(scope='module')
def contract():
    return R.load_contract()


def rec(contract, group, fault=None):
    return next(record for record in contract['runs']
                if record['group'] == group and
                (fault is None or record['fault'] == fault))


def test_phase5_binding_is_lazy_so_monkeypatch_still_works(monkeypatch,
                                                           tmp_path):
    fake = C.run_paths('x', tmp_path)
    monkeypatch.setattr(C, 'run_paths', lambda rid: fake)
    assert B.get('phase5').run_paths('anything') is fake


def test_phase6r_binding_uses_separate_paths_verify_and_manifest():
    binding = B.get('phase6r')
    assert 'phase6r' in str(binding.run_paths(
        'RD-degrade-s1-s2-rho200-s4101-r1')['final'])
    assert 'phase6r' in str(binding.manifest_path)
    assert binding.manifest_path != C.MANIFEST_PATH
    assert binding.supports_interventions
    assert not B.get('phase5').supports_interventions


def test_integrity_env_must_match_contract(contract):
    binding = B.get('phase6r')
    sha = contract['design_content_sha256']
    good = json.dumps({'stored': sha, 'recomputed': sha, 'match': True})
    assert B.integrity_ok(binding, contract, good)
    assert not B.integrity_ok(binding, contract, json.dumps(
        {'stored': sha, 'recomputed': 'x' * 64, 'match': True}))
    assert not B.integrity_ok(binding, contract, '{}')


def test_runner_and_launcher_have_no_hardcoded_phase5_calls():
    for module in (runner, launcher):
        source = inspect.getsource(module)
        for forbidden in ('C.run_paths(', 'C.verify_run(', 'C.MANIFEST_PATH',
                          'C.build_manifest(', 'C.load_contract('):
            assert forbidden not in source, (module.__name__, forbidden)


def test_intervention_is_recorded_before_apply_in_runner_source():
    source = inspect.getsource(runner.execute_run)
    assert source.index("record_before_apply('inject'") < source.index(
        'env.injection.apply(scenario)')
    assert source.index("record_before_apply('revert'") < source.index(
        'env.injection.revert_all()')


def test_rd_logs_revert_only(contract):
    recorder = RT.InterventionRecorder(rec(contract, 'RD'))
    assert recorder.record_before_apply('inject', 100.0, 20) is None
    item = recorder.record_before_apply('revert', 120.5, 40)
    assert item['actor'] == 'harness'
    assert item['t_start'] == 120.5
    assert item['blast_radius']
    assert len(item['routing_sha256']) == 64


def test_controller_run_logs_inject_and_revert(contract):
    recorder = RT.InterventionRecorder(rec(contract, 'RO'))
    assert recorder.record_before_apply('inject', 1.0, 20)['actor'] == 'controller'
    assert recorder.record_before_apply('revert', 21.0, 40) is not None
    assert len(recorder.items) == 2


def test_normal_run_records_nothing(contract):
    recorder = RT.InterventionRecorder(rec(contract, 'RS'))
    assert recorder.record_before_apply('inject', 1.0, 20) is None
    assert recorder.items == []


def test_harness_can_never_log_inject(contract):
    bad = dict(rec(contract, 'RD'),
               intervention={'actor': 'harness', 'log_inject': True,
                             'log_revert': True})
    with pytest.raises(ValueError):
        RT.InterventionRecorder(bad)


def test_duplicate_intervention_id_rejected(contract):
    recorder = RT.InterventionRecorder(rec(contract, 'RC'))
    recorder.record_before_apply('revert', 1.0, 40)
    with pytest.raises(ValueError):
        recorder.record_before_apply('revert', 2.0, 40)


def test_targets_match_amendment_2_replay_rule(contract):
    from scripts.build_phase6r_amendment2 import revert_targets
    for record in contract['runs']:
        if record['fault']:
            assert RT.targets_for(record) == revert_targets(record)


def _quarantine(paths, failed_gates):
    paths['quarantine_meta'].parent.mkdir(parents=True, exist_ok=True)
    C.atomic_json(paths['quarantine_meta'],
                  {'checks': {'failed_gates': failed_gates}})


def test_rerun_allowed_after_instrument_failure(tmp_path):
    paths = R.run_paths('RS-soak2M-s4001-r1', tmp_path)
    assert RT.rerun_allowed(paths)[0]
    _quarantine(paths, ['tick_count_ok'])
    assert RT.rerun_allowed(paths)[0]


def test_rerun_blocked_after_outcome_gate_failure(tmp_path):
    paths = R.run_paths('RC-flood-h1_to_srv1-s4201-r1', tmp_path)
    _quarantine(paths, ['signal_present'])
    allowed, why = RT.rerun_allowed(paths)
    assert not allowed and 'KET CUC' in why


def test_rerun_blocked_after_max_attempts(tmp_path):
    paths = R.run_paths('RN-load6M-s4011-r1', tmp_path)
    _quarantine(paths, ['tick_count_ok'])
    runner.archive_attempt(paths)
    _quarantine(paths, ['tick_count_ok'])
    allowed, why = RT.rerun_allowed(paths)
    assert not allowed and RT.attempts_so_far(paths) == 2


def test_manifest_counts_by_group_and_never_opens_labels(contract):
    run_id = rec(contract, 'RS')['run_id']
    manifest = RT.build_manifest(
        contract, {run_id: {'status': 'ok', 'checks': {'passed': True}}},
        {}, {'match': True}, 's', 'f')
    assert manifest['by_group']['RS'] == {'expected': 3, 'ok': 1}
    assert manifest['complete'] is False
    assert manifest['labels_opened'] is False
    with pytest.raises(ValueError):
        RT.build_manifest(contract, {'khong-co': {}}, {}, {'match': True},
                          's', 'f')
