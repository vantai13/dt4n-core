#!/usr/bin/env python3
"""Pure tests for bridge.ditto_reader."""

import json
import io
import logging
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.ditto_reader import (  # noqa: E402
    SnapshotCache,
    aoi_summary,
    compute_aoi,
    expected_thing_ids,
    extract_t_source,
)


FAKE = {
    'org.dt4n:link-s2-s3': {
        'features': {
            'meta': {'properties': {'tSource': 1000.0}},
            'traffic': {'properties': {'rxRate': 500.0}},
        },
    },
    'org.dt4n:host-h1': {
        'features': {
            'meta': {'properties': {'tSource': 999.5}},
        },
    },
}


def test_extract_t_source():
    assert extract_t_source(FAKE['org.dt4n:link-s2-s3']) == 1000.0
    assert extract_t_source({'features': {}}) is None


def test_compute_aoi_is_pure():
    aoi = compute_aoi(FAKE, t_read=1000.7)
    assert abs(aoi['org.dt4n:link-s2-s3'] - 0.7) < 1e-9
    assert abs(aoi['org.dt4n:host-h1'] - 1.2) < 1e-9


def test_compute_aoi_uses_per_thing_read_times():
    aoi = compute_aoi(
        FAKE,
        t_read=1001.0,
        read_times={
            'org.dt4n:link-s2-s3': 1000.2,
            'org.dt4n:host-h1': 1000.4,
        },
    )
    assert abs(aoi['org.dt4n:link-s2-s3'] - 0.2) < 1e-9
    assert abs(aoi['org.dt4n:host-h1'] - 0.9) < 1e-9


def test_missing_tsource_is_omitted_not_zeroed():
    assert compute_aoi({'x': {'features': {}}}, t_read=100.0) == {}


def test_negative_aoi_is_returned_not_clipped():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger('ditto_reader')
    old_level = logger.level
    old_propagate = logger.propagate
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        aoi = compute_aoi(FAKE, t_read=999.0)
        assert aoi['org.dt4n:link-s2-s3'] < 0
        assert 'Negative AoI' in stream.getvalue()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate


def test_no_nan_ever():
    aoi = compute_aoi(FAKE, t_read=1000.7)
    assert all(not math.isnan(value) for value in aoi.values())


def test_aoi_summary():
    summary = aoi_summary({'a': 0.5, 'b': 1.0, 'c': -0.2})
    assert summary['n'] == 3
    assert abs(summary['mean'] - (1.3 / 3.0)) < 1e-9
    assert summary['max'] == 1.0
    assert summary['n_negative'] == 1


def test_cache_forward_fill():
    cache = SnapshotCache()
    merged, info = cache.get(FAKE, {'n_ok': 2, 'n_fail': 0})
    assert len(merged) == 2
    assert info['data_fresh'] == 1.0

    merged, info = cache.get({}, {'n_ok': 0, 'n_fail': 2})
    assert len(merged) == 2
    assert info['data_fresh'] == 0.0
    assert info['aborted'] is False
    assert info['consecutive_fails'] == 1


def test_cache_marks_partial_failure_not_fresh():
    cache = SnapshotCache()
    partial = {'org.dt4n:host-h1': FAKE['org.dt4n:host-h1']}
    _merged, info = cache.get(partial, {'n_ok': 1, 'n_fail': 1})
    assert info['data_fresh'] == 0.0
    assert info['aborted'] is False


def test_cache_aborts_after_three_fails():
    cache = SnapshotCache()
    cache.get(FAKE, {'n_ok': 2, 'n_fail': 0})
    for _ in range(3):
        _merged, info = cache.get({}, {'n_ok': 0, 'n_fail': 2})
    assert info['aborted'] is True


def test_expected_thing_ids_current_topology():
    spec = json.load(open(ROOT / 'ditto/topology_spec.json'))
    ids = expected_thing_ids(spec)
    assert len(ids) == 17
    assert 'org.dt4n:controller' not in ids
    assert 'org.dt4n:path-h1-srv1' in ids
    assert len(ids) == len(set(ids))


if __name__ == '__main__':
    tests = [
        test_extract_t_source,
        test_compute_aoi_is_pure,
        test_compute_aoi_uses_per_thing_read_times,
        test_missing_tsource_is_omitted_not_zeroed,
        test_negative_aoi_is_returned_not_clipped,
        test_no_nan_ever,
        test_aoi_summary,
        test_cache_forward_fill,
        test_cache_marks_partial_failure_not_fresh,
        test_cache_aborts_after_three_fails,
        test_expected_thing_ids_current_topology,
    ]
    for test in tests:
        test()
        print('PASS %s' % test.__name__)
    print('ditto_reader tests passed')
