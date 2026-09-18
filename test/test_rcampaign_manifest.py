#!/usr/bin/env python3
"""Ghim toàn vẹn receipt thu thập R-campaign, không đọc nhãn hay chấm R-set."""
from __future__ import annotations

import json
import re

import pytest

from ml import campaign as C

MANIFEST = C.ROOT / 'results/report/phase6r_rcampaign_manifest.json'
MATRIX = C.ROOT / 'results/report/phase6r_rcampaign_matrix.json'
AMENDMENT_6 = C.ROOT / 'results/report/phase6r_amendment_6.json'
RAW = C.ROOT / 'data/phase6r/raw'


@pytest.fixture(scope='module')
def manifest():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def test_manifest_is_pinned_by_amendment_6_before_replay():
    amendment = json.loads(AMENDMENT_6.read_text(encoding='utf-8'))
    content = amendment['content']
    assert amendment['content_sha256'] == C.sha256_bytes(
        C.canonical_json(content).encode('utf-8'))
    assert content['pinned_receipt_sha256'][str(MANIFEST.relative_to(C.ROOT))] == \
        C.sha256_file(MANIFEST)
    assert content['timing_and_knowledge']['raw_snapshot_lines_read_for_this_decision'] is False


def test_complete_25_runs(manifest):
    assert manifest['n_runs_expected'] == manifest['n_runs_ok'] == 25
    assert manifest['n_runs_failed'] == 0
    assert manifest['complete'] is True
    assert manifest['runs_not_attempted'] == []


def test_labels_still_sealed(manifest):
    """Test này phải được sửa có ý thức đúng lúc R-set mở ở Lesson 6R.7."""
    assert manifest['labels_opened'] is False


def test_contract_not_drifted(manifest):
    integrity = manifest['contract_integrity']
    assert integrity['stored'] == integrity['recomputed']
    assert integrity['match'] is True


def test_sha_chain_manifest_meta_lfs(manifest):
    """Hỗ trợ cả file LFS thật và pointer khi CI chưa tải LFS object."""
    for run_id, record in manifest['runs'].items():
        meta = json.loads((RAW / ('%s.meta.json' % run_id)).read_text())
        raw_path = RAW / ('%s.jsonl' % run_id)
        pointer = raw_path.read_text(errors='ignore')
        match = re.search(r'oid sha256:([0-9a-f]{64})', pointer)
        digest = match.group(1) if match else C.sha256_file(raw_path)
        assert record['sha256'] == meta['sha256'] == digest, run_id


def test_every_run_passed_instrument_gates(manifest):
    for run_id, record in manifest['runs'].items():
        assert record['status'] == 'ok', run_id
        assert record['checks']['failed_gates'] == [], run_id
        assert record['checks']['qdisc_invalid_fraction_baseline'] == 0.0, run_id
        assert record['checks']['rate_invalid_fraction_baseline'] == 0.0, run_id


def test_execution_followed_sealed_random_order(manifest):
    """Chống temporal confound: thời gian phải theo exec_index đã khóa."""
    matrix = json.loads(MATRIX.read_text(encoding='utf-8'))
    indices = {record['run_id']: record['exec_index'] for record in matrix['runs']}
    sequence = sorted(
        (indices[run_id], record['started_utc'])
        for run_id, record in manifest['runs'].items())
    timestamps = [timestamp for _, timestamp in sequence]
    assert timestamps == sorted(timestamps), 'thu tu chay lech thu tu da khoa'
