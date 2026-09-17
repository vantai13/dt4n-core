#!/usr/bin/env python3
"""Lesson 6R.5 — thiết kế R-campaign tất định, cùng schema record Phase 5.

Ma trận Phase 5 đã được khóa bằng hash nên R-campaign dùng module, hợp đồng,
thư mục và manifest riêng. Record vẫn giữ đúng schema Phase 5 để tái sử dụng
runner và các phép kiểm hiện có.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from ml import campaign as C
from ml import design as D

CAMPAIGN_ID = 'DT4N-P6R-RCAMPAIGN'
EXEC_ORDER_SEED = 20260918
DATA_DIR = 'data/phase6r'
CONTRACT_PATH = C.ROOT / 'results/report/phase6r_rcampaign_matrix.json'
CONTRACT_KEYS = ('constants', 'runs', 'execution_order', 'groups',
                 'routing_table_sha256', 'topology_spec_sha256', 'amendment_1_sha256')

CONSTANTS = {
    'campaign_id': CAMPAIGN_ID, 'duration_sec': 60, 'pre_roll_sec': D.PRE_ROLL_SEC,
    'warmup_ticks': D.WARMUP_TICKS, 'period_sec': D.PERIOD_SEC,
    't_inject': D.T_INJECT, 't_revert': D.T_REVERT,
    'collector_version': D.COLLECTOR_VERSION, 'exec_order_seed': EXEC_ORDER_SEED,
    'soak_duration_sec': 3600,
}
ROLE = {'RS': 'nghiem thu', 'RN': 'nghiem thu', 'RD': 'nghiem thu',
        'RC': 'HIEU CHINH', 'RO': 'nghiem thu'}


def _record(run_id, group, *, load, fault=None, target=None, seed, params=None,
            duration=60, actor=None, log_inject=False, log_revert=False):
    has_fault = fault is not None
    return {
        'run_id': run_id, 'group': group, 'split': 'r_set', 'role': ROLE[group],
        'profile': 'normal', 'load_mbps_per_client': float(load), 'load_schedule': None,
        'fault': fault, 'fault_target': target, 'seed': seed,
        't_inject': D.T_INJECT if has_fault else None,
        't_revert': D.T_REVERT if has_fault else None,
        'duration_sec': duration,
        'expected_links': D.expected_affected_links(fault, target) if has_fault else [],
        'fault_parameters': params or {},
        'intervention': {'actor': actor, 'log_inject': log_inject,
                         'log_revert': log_revert},
    }


def _severity(fault, target, seed):
    """R-C dùng đúng phân phối mức độ Phase 5 với seed mới."""
    spec = D.RunSpec(run_id='tmp', group='F', split='test', profile='normal',
                     load_mbps_per_client=2.0, load_schedule=None, fault=fault,
                     fault_target=target, seed=seed, t_inject=D.T_INJECT,
                     t_revert=D.T_REVERT)
    return D.fault_parameters(spec)


def build_runs(amendment_1: dict) -> list[dict]:
    runs = []
    for k, seed in enumerate((4001, 4002, 4003), start=1):
        runs.append(_record('RS-soak2M-s%d-r%d' % (seed, k), 'RS', load=2.0,
                            seed=seed, duration=3600))
    seed = 4011
    for load in (6.0, 8.0, 10.0):
        for k in (1, 2):
            runs.append(_record('RN-load%gM-s%d-r%d' % (load, seed, k), 'RN',
                                load=load, seed=seed))
            seed += 1
    corr = amendment_1['content']['r_d_design_correction']['corrected_factors']
    rho = amendment_1['content']['r_d_design_correction']['target_rho']
    base = {row['link']: row['baseline_mbps']
            for row in amendment_1['content']['prediction']['illustrative_table_using_prior']}
    seed = 4101
    for link in ('s1-s2', 's2-s3'):
        for factor, r in zip(corr[link], rho):
            params = {'link_key': link, 'factor': factor, 'delay': '2ms',
                      'baseline': base[link]}
            runs.append(_record(
                'RD-degrade-%s-rho%03d-s%d-r1' % (link, round(r * 100), seed),
                'RD', load=2.0, fault='degrade', target=link, seed=seed,
                params=params, actor='harness', log_revert=True))
            seed += 1
    for fault, target, seed in (
            ('flood', 'h1->srv1', 4201), ('flood', 'h2->srv2', 4202),
            ('shift', 's1-s2', 4203), ('shift', 's1-s3', 4204)):
        runs.append(_record(
            'RC-%s-%s-s%d-r1' % (fault, target.replace('->', '_to_'), seed),
            'RC', load=2.0, fault=fault, target=target, seed=seed,
            params=_severity(fault, target, seed), actor='harness', log_revert=True))
    for k, seed in enumerate((4301, 4302), start=1):
        runs.append(_record(
            'RO-ctl_admin_down-s1-s2-s%d-r%d' % (seed, k), 'RO', load=2.0,
            fault='admin_down', target='s1-s2', seed=seed,
            params={'link_key': 's1-s2'}, actor='controller',
            log_inject=True, log_revert=True))
    return runs


def execution_order(runs, seed=EXEC_ORDER_SEED) -> list[str]:
    ids = [r['run_id'] for r in runs]
    return random.Random(seed).sample(ids, len(ids))


def contract_subset(amendment_1: dict, root: Path | None = None) -> dict:
    root = Path(root or C.ROOT)
    runs = build_runs(amendment_1)
    order = execution_order(runs)
    pos = {run_id: i for i, run_id in enumerate(order)}
    for record in runs:
        record['exec_index'] = pos[record['run_id']]
    groups = {}
    for record in runs:
        groups.setdefault(record['group'], []).append(record['run_id'])
    return {
        'constants': dict(CONSTANTS), 'runs': runs, 'execution_order': order,
        'groups': {g: sorted(v) for g, v in sorted(groups.items())},
        'routing_table_sha256': C.sha256_file(root / 'ditto/routing_table.json'),
        'topology_spec_sha256': C.sha256_file(root / 'ditto/topology_spec.json'),
        'amendment_1_sha256': amendment_1['content_sha256'],
    }


def design_hash(subset: dict) -> str:
    protected = {key: subset[key] for key in CONTRACT_KEYS}
    return C.sha256_bytes(C.canonical_json(protected).encode('utf-8'))


def validate(subset: dict, slo: dict) -> dict:
    runs = subset['runs']
    ids = [r['run_id'] for r in runs]
    seeds = [r['seed'] for r in runs]
    sealed = {g['group']: g['n_runs'] for g in slo['content']['r_campaign']}
    counts = {g: len(v) for g, v in subset['groups'].items()}
    checks = {
        'run_ids_unique': len(set(ids)) == len(ids),
        'seeds_unique': len(set(seeds)) == len(seeds),
        'run_id_filename_safe': all(__import__('re').fullmatch(r'[A-Za-z0-9_-]+', i)
                                    for i in ids),
        'RS_matches_slo': counts.get('RS') == sealed['R-S'],
        'RN_matches_slo': counts.get('RN') == sealed['R-N'],
        'RD_matches_slo': counts.get('RD') == sealed['R-D'],
        'RC_matches_slo': counts.get('RC') == sealed['R-C'],
        'RO_collected_is_offline_subset': counts.get('RO') == 2 and sealed['R-O'] == 4,
        'RD_no_duplicate_dose': len({
            (r['fault_target'], round(r['fault_parameters']['baseline'] *
                                      (1 - r['fault_parameters']['factor']), 6))
            for r in runs if r['group'] == 'RD'}) == 10,
        'RD_above_bw_floor': all(
            r['fault_parameters']['baseline'] * (1 - r['fault_parameters']['factor']) > 1.0
            for r in runs if r['group'] == 'RD'),
        'inject_never_logged_except_controller': all(
            not r['intervention']['log_inject'] or
            r['intervention']['actor'] == 'controller' for r in runs),
        'faults_have_expected_links': all(r['expected_links'] for r in runs if r['fault']),
        'execution_order_is_permutation': sorted(subset['execution_order']) == sorted(ids),
    }
    if not all(checks.values()):
        raise ValueError('thiet ke R-campaign khong hop le: %s' %
                         [k for k, value in checks.items() if not value])
    return {'checks': checks, 'counts': counts,
            'collection_seconds_estimate': sum(
                r['duration_sec'] + D.PRE_ROLL_SEC + 30 for r in runs)}


def load_contract(path=CONTRACT_PATH) -> dict:
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('campaign_id') != CAMPAIGN_ID or not doc.get('design_locked'):
        raise RuntimeError('khong phai hop dong R-campaign da khoa')
    if doc['design_content_sha256'] != design_hash(doc):
        raise RuntimeError('noi dung hop dong R-campaign da bi sua')
    return doc


def check_integrity(doc: dict, amendment_1: dict, root: Path | None = None) -> dict:
    """Dựng lại từ module hiện tại và amendment 1; lệch thì dừng."""
    recomputed = design_hash(contract_subset(amendment_1, root))
    ok = doc['design_content_sha256'] == design_hash(doc) == recomputed
    if not ok:
        raise RuntimeError('HOP DONG R-CAMPAIGN TROI LECH: stored=%s recomputed=%s' %
                           (doc['design_content_sha256'], recomputed))
    return {'stored': doc['design_content_sha256'], 'recomputed': recomputed,
            'match': ok}


def run_paths(run_id: str, root: Path | None = None) -> dict:
    """Quy ước commit-point Phase 5, dưới data/phase6r riêng biệt."""
    root = Path(root or C.ROOT)
    phase5_paths = C.run_paths(run_id, root)
    raw, quarantine = root / DATA_DIR / 'raw', root / DATA_DIR / 'quarantine'
    return {
        'partial': raw / phase5_paths['partial'].name,
        'final': raw / phase5_paths['final'].name,
        'meta': raw / phase5_paths['meta'].name,
        'quarantine': quarantine / phase5_paths['quarantine'].name,
        'quarantine_meta': quarantine / phase5_paths['quarantine_meta'].name,
        'log': root / ('logs/rcampaign_%s.log' % run_id),
    }


OUTCOME_GATES_AS_COVARIATE = {'RD': ('signal_present',)}


def verify_rrun(record, constants, snapshots, events) -> dict:
    """Hạ signal_present của R-D thành covariate để tránh survivorship bias."""
    checks = C.verify_run(record, constants, snapshots, events)
    demoted = OUTCOME_GATES_AS_COVARIATE.get(record['group'], ())
    for gate in demoted:
        if gate in checks:
            checks['covariate_' + gate] = checks.pop(gate)
    if demoted:
        gates = [g for g in checks.get('failed_gates', []) if g not in demoted]
        checks['failed_gates'] = gates
        checks['passed'] = not gates and checks.get('tick_count_ok', True) is True
        checks['demoted_to_covariate'] = list(demoted)
    return checks
