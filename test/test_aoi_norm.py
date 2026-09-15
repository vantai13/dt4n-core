#!/usr/bin/env python3

from bridge.ditto_common import make_thing_id_host, make_thing_id_link
from mininet.aoi_norm import (
    AOI_NORM_DIVISOR,
    AOI_PERCENTILE,
    dynamic_thing_ids,
)


def test_aoi_constants_match_frozen_env_contract():
    assert AOI_NORM_DIVISOR == 5.0
    assert AOI_PERCENTILE == 0.95


def test_dynamic_thing_ids_include_hosts_and_links_only():
    spec = {
        'hosts': [
            {'name': 'h1'},
            {'name': 'srv1'},
        ],
        'switches': [
            {'name': 's1'},
        ],
        'links': [
            ['h1', 's1'],
            {'endpoints': ['srv1', 's1']},
            {'a': 's1', 'b': 's2'},
        ],
    }

    assert dynamic_thing_ids(spec) == {
        make_thing_id_host('h1'),
        make_thing_id_host('srv1'),
        make_thing_id_link('h1', 's1'),
        make_thing_id_link('srv1', 's1'),
        make_thing_id_link('s1', 's2'),
    }
