#!/usr/bin/env python3
"""Topology metadata for RL-safe DT4N actions.

This module is deliberately pure: it reads the topology spec and computes facts
that future Gym code needs, without importing or touching live Mininet objects.
"""

import json
from collections import defaultdict


DEFAULT_BW_BACKBONE = 20.0
DEFAULT_BW_BOTTLENECK = 5.0
BOTTLENECK_EDGE = frozenset(('s2', 's3'))


def load_spec(path='ditto/topology_spec.json'):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def canonical(a, b):
    """Return the canonical undirected link key used by Ditto link Thing ids."""
    lo, hi = sorted([a, b])
    return '%s-%s' % (lo, hi)


def _link_endpoints(link):
    if isinstance(link, dict):
        return link['endpoints'][0], link['endpoints'][1]
    return link[0], link[1]


def baseline_bw(spec, bw_backbone=DEFAULT_BW_BACKBONE,
                bw_bottleneck=DEFAULT_BW_BOTTLENECK):
    """Return {canonical_link_key: baseline_bandwidth_Mbps}.

    Defaults match mininet.topology.TriangleTopo, but callers can inject a
    different backbone/bottleneck scale for Phase 7 sweeps.
    """
    out = {}
    for link in spec.get('links', []):
        a, b = _link_endpoints(link)
        if isinstance(link, dict) and link.get('bwMbps') is not None:
            bw = float(link['bwMbps'])
        else:
            edge = frozenset((a, b))
            bw = bw_bottleneck if edge == BOTTLENECK_EDGE else bw_backbone
        out[canonical(a, b)] = float(bw)
    return out


def build_adj(spec):
    """Build an undirected adjacency list with edge indexes for multi-edge safety."""
    adj = defaultdict(list)
    for idx, link in enumerate(spec.get('links', [])):
        a, b = _link_endpoints(link)
        adj[a].append((b, idx))
        adj[b].append((a, idx))
    return adj


def _spec_nodes(spec):
    names = []
    for item in spec.get('hosts', []):
        names.append(item.get('name') if isinstance(item, dict) else item)
    for item in spec.get('switches', []):
        names.append(item.get('name') if isinstance(item, dict) else item)
    return [name for name in names if name]


def find_bridges(spec):
    """Return canonical link keys that are graph bridges using Tarjan DFS.

    In an undirected graph, the parent tree edge must be excluded by edge index,
    not by node name. That distinction matters if Phase 7 adds parallel links:
    the second edge between the same two nodes is a valid back-edge.
    """
    adj = build_adj(spec)
    disc = {}
    low = {}
    bridges = set()
    timer = [0]

    def dfs(u, parent_edge):
        disc[u] = low[u] = timer[0]
        timer[0] += 1

        for v, edge_idx in adj[u]:
            if edge_idx == parent_edge:
                continue
            if v not in disc:
                dfs(v, edge_idx)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    bridges.add(canonical(u, v))
            else:
                low[u] = min(low[u], disc[v])

    for node in _spec_nodes(spec):
        if node not in disc:
            dfs(node, -1)
    return bridges


def toggleable_links(spec):
    """Return links that an RL agent may safely toggle: all non-bridge links."""
    all_links = {
        canonical(*_link_endpoints(link))
        for link in spec.get('links', [])
    }
    return sorted(all_links - find_bridges(spec))


if __name__ == '__main__':
    spec = load_spec()
    print('Cau (KHONG duoc toggle):', sorted(find_bridges(spec)))
    print('Toggle duoc          :', toggleable_links(spec))
    print('Baseline bw          :', baseline_bw(spec))
