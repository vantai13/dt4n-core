#!/usr/bin/env python3
"""Thiết kế R-campaign và gate nghiệm thu không phụ thuộc kết cục."""
from __future__ import annotations

import json

import pytest

from ml import campaign as C
from ml import rcampaign as R

REPORT = C.ROOT / 'results/report'


@pytest.fixture(scope='module')
def a1():
    return json.loads((REPORT / 'phase6r_amendment_1.json').read_text())


@pytest.fixture(scope='module')
def subset(a1):
    return R.contract_subset(a1)


def test_design_is_deterministic(a1, subset):
    assert R.design_hash(subset) == R.design_hash(R.contract_subset(a1))


def test_counts_match_sealed_slo_and_r_o_split(subset):
    validation = R.validate(subset, json.loads((REPORT / 'phase6r_slo.json').read_text()))
    assert validation['counts'] == {'RC': 4, 'RD': 10, 'RN': 6, 'RO': 2, 'RS': 3}


def test_rd_uses_amendment_1_corrected_factors(a1, subset):
    corrected = a1['content']['r_d_design_correction']['corrected_factors']
    got = {link: [r['fault_parameters']['factor'] for r in subset['runs']
                  if r['group'] == 'RD' and r['fault_target'] == link]
           for link in corrected}
    assert got == corrected


def test_records_are_phase5_schema_compatible(subset):
    phase5 = json.loads((REPORT / 'experiment_matrix.json').read_text())['runs'][0]
    for record in subset['runs']:
        assert set(phase5) <= set(record)
        C.traffic_plan(record, subset['constants'])


def test_scenarios_build_from_records(subset):
    pytest.importorskip('mininet.topology_meta')
    for record in subset['runs']:
        if record['fault']:
            assert C.scenario_from_record(record) is not None


def test_only_controller_runs_log_inject(subset):
    for record in subset['runs']:
        if record['intervention']['log_inject']:
            assert record['group'] == 'RO'
            assert record['intervention']['actor'] == 'controller'


def test_paths_are_separate_from_phase5():
    paths = R.run_paths('RD-degrade-s1-s2-rho200-s4101-r1')
    assert 'phase6r' in str(paths['final']) and 'phase5' not in str(paths['final'])


def _fake_checks(monkeypatch, checks):
    monkeypatch.setattr(C, 'verify_run', lambda *args, **kwargs: dict(checks))


def test_rd_low_dose_without_signal_is_not_quarantined(monkeypatch):
    _fake_checks(monkeypatch, {'tick_count_ok': True, 'signal_present': False,
                               'event_ticks_ok': True, 'passed': False,
                               'failed_gates': ['signal_present']})
    out = R.verify_rrun({'group': 'RD'}, {}, [], [])
    assert out['passed'] is True
    assert out['covariate_signal_present'] is False
    assert 'signal_present' not in out


def test_rd_instrument_failure_still_quarantines(monkeypatch):
    _fake_checks(monkeypatch, {'tick_count_ok': False, 'signal_present': True,
                               'passed': False, 'failed_gates': ['tick_count_ok']})
    assert R.verify_rrun({'group': 'RD'}, {}, [], [])['passed'] is False


def test_rc_keeps_signal_gate(monkeypatch):
    _fake_checks(monkeypatch, {'tick_count_ok': True, 'signal_present': False,
                               'passed': False, 'failed_gates': ['signal_present']})
    assert R.verify_rrun({'group': 'RC'}, {}, [], [])['passed'] is False
