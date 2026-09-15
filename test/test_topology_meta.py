#!/usr/bin/env python3
"""Pure tests for RL topology metadata."""

import copy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mininet.topology_meta import (  # noqa: E402
    baseline_bw,
    canonical,
    find_bridges,
    toggleable_links,
)


def _load_current_spec():
    return json.load(open(ROOT / 'ditto/topology_spec.json', encoding='utf-8'))


def test_current_topology_bridges_and_toggleable_links():
    spec = _load_current_spec()
    assert find_bridges(spec) == {
        'h1-s1',
        'h2-s1',
        'h3-s1',
        's2-srv1',
        's3-srv2',
    }
    assert toggleable_links(spec) == ['s1-s2', 's1-s3', 's2-s3']


def test_baseline_bw_current_topology():
    spec = _load_current_spec()
    bw = baseline_bw(spec)
    assert bw['s2-s3'] == 5.0
    assert bw['s1-s2'] == 20.0
    assert bw['s1-s3'] == 20.0
    assert bw['s2-srv1'] == 20.0


def test_added_s1_srv1_link_removes_srv1_bridge():
    spec = copy.deepcopy(_load_current_spec())
    spec['links'].append(['s1', 'srv1'])
    bridges = find_bridges(spec)
    assert 's2-srv1' not in bridges
    assert 's1-srv1' not in bridges
    assert 'h1-s1' in bridges
    assert 's1-srv1' in toggleable_links(spec)


def test_canonical_is_stable():
    assert canonical('srv1', 's2') == 's2-srv1'
    assert canonical('s2', 'srv1') == 's2-srv1'


if __name__ == '__main__':
    tests = [
        test_current_topology_bridges_and_toggleable_links,
        test_baseline_bw_current_topology,
        test_added_s1_srv1_link_removes_srv1_bridge,
        test_canonical_is_stable,
    ]
    for test in tests:
        test()
        print('PASS %s' % test.__name__)
    print('topology_meta tests passed')
