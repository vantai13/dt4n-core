#!/usr/bin/env python3
"""AoI freshness helpers shared by Mininet/A2 infrastructure.

EnvRunner needs only these constants and Thing-id selection logic. Keeping them
here avoids importing the legacy RL state builder from infrastructure code.
"""

from bridge.ditto_common import make_thing_id_host, make_thing_id_link


AOI_NORM_DIVISOR = 5.0
AOI_PERCENTILE = 0.95


def _host_names(spec):
    names = []
    for host in spec.get('hosts', []):
        names.append(host.get('name') if isinstance(host, dict) else host)
    return [name for name in names if name]


def _link_endpoints(link):
    if isinstance(link, dict):
        if 'endpoints' in link:
            return link['endpoints'][0], link['endpoints'][1]
        return link['a'], link['b']
    return link[0], link[1]


def dynamic_thing_ids(spec):
    """Return Thing ids whose freshness affects live environment state."""
    ids = set()
    for name in _host_names(spec):
        ids.add(make_thing_id_host(name))
    for link in spec.get('links', []):
        ids.add(make_thing_id_link(*_link_endpoints(link)))
    return ids
