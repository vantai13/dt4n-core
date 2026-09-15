#!/usr/bin/env python3
"""Generate deterministic static forwarding routes from topology_spec.json.

The controller needs a table of:

    switch -> destination IP -> next hop node name

The table is generated instead of hand-written so the route logic stays tied to
the topology spec and can be verified for forwarding loops before Mininet runs.
"""

import argparse
import heapq
import json
import os
from collections import defaultdict


BOTTLENECK_EDGE = frozenset(("s2", "s3"))
W_NORMAL = 1

# Keep the bottleneck at normal hop cost for this topology. Hop-count already
# sends h* -> srv1 via s2 and h* -> srv2 via s3, while srv1 <-> srv2 uses s2-s3.
# Raising this weight would make server-to-server traffic avoid the bottleneck,
# which defeats the Phase 4.5 goal.
W_BOTTLENECK = 1


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def edge_weight(a, b):
    return W_BOTTLENECK if frozenset((a, b)) == BOTTLENECK_EDGE else W_NORMAL


def link_endpoints(link):
    """Return the two endpoint names from a legacy list or metadata dict link."""
    if isinstance(link, dict):
        return link["endpoints"][0], link["endpoints"][1]
    return link[0], link[1]


def build_graph(spec, excluded_edges=()):
    """Return an undirected weighted graph from the topology spec."""
    graph = defaultdict(dict)
    excluded = {frozenset(edge) for edge in excluded_edges}

    for link in spec.get("links", []):
        a, b = link_endpoints(link)
        edge = frozenset((a, b))
        if edge in excluded:
            continue
        weight = edge_weight(a, b)
        graph[a][b] = weight
        graph[b][a] = weight

    return graph


def dijkstra(graph, src):
    """Return (dist, prev) for shortest paths from src."""
    dist = {src: 0}
    prev = {}
    pq = [(0, src)]
    seen = set()

    while pq:
        cur_dist, node = heapq.heappop(pq)
        if node in seen:
            continue
        seen.add(node)

        for neighbor in sorted(graph.get(node, {})):
            new_dist = cur_dist + graph[node][neighbor]
            if new_dist < dist.get(neighbor, float("inf")):
                dist[neighbor] = new_dist
                prev[neighbor] = node
                heapq.heappush(pq, (new_dist, neighbor))

    return dist, prev


def switch_names(spec):
    return [item["name"] if isinstance(item, dict) else item
            for item in spec.get("switches", [])]


def host_items(spec):
    return [item for item in spec.get("hosts", []) if isinstance(item, dict)]


def next_hop_table(spec, excluded_edges=()):
    """Build switch -> host IP -> next hop.

    For each destination host H, run Dijkstra from H. Because the graph is
    undirected, prev[S] is exactly the next hop for S when forwarding toward H.
    """
    graph = build_graph(spec, excluded_edges=excluded_edges)
    switches = switch_names(spec)
    table = {sw: {} for sw in switches}

    for host in host_items(spec):
        host_name = host["name"]
        host_ip = host["ip"]
        _dist, prev = dijkstra(graph, host_name)

        for sw in switches:
            if sw not in prev:
                continue
            table[sw][host_ip] = prev[sw]

    return table


def host_attachment(spec):
    """Return IP -> {name, attached_to} using links from the spec."""
    switches = set(switch_names(spec))
    out = {}

    for host in host_items(spec):
        attached_to = None
        for link in spec.get("links", []):
            a, b = link_endpoints(link)
            if a == host["name"] and b in switches:
                attached_to = b
                break
            if b == host["name"] and a in switches:
                attached_to = a
                break

        out[host["ip"]] = {
            "name": host["name"],
            "attached_to": attached_to,
        }

    return out


def verify_no_loop(table, spec):
    """Raise AssertionError if any destination forwarding graph has a loop."""
    switches = set(switch_names(spec))

    for host in host_items(spec):
        host_name = host["name"]
        host_ip = host["ip"]

        for start in sorted(switches):
            cur = start
            seen = set()

            while cur != host_name:
                if cur in seen:
                    raise AssertionError(
                        "forwarding loop to %s from %s at %s" %
                        (host_ip, start, cur)
                    )
                seen.add(cur)

                if cur not in switches:
                    raise AssertionError(
                        "route to %s from %s stopped at non-switch %s" %
                        (host_ip, start, cur)
                    )

                next_hop = table.get(cur, {}).get(host_ip)
                if next_hop is None:
                    raise AssertionError(
                        "missing route to %s from %s at %s" %
                        (host_ip, start, cur)
                    )
                cur = next_hop

    return True


def generate(spec):
    routes = next_hop_table(spec)
    verify_no_loop(routes, spec)
    return {
        "_comment": "Generated by mininet/gen_routes.py. Do not edit by hand.",
        "_weights": {
            "normal": W_NORMAL,
            "bottleneck": W_BOTTLENECK,
            "bottleneck_edge": sorted(BOTTLENECK_EDGE),
        },
        "next_hop": routes,
        "hosts": host_attachment(spec),
    }


def write_json(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="ditto/topology_spec.json")
    parser.add_argument("--out", default="ditto/routing_table.json")
    args = parser.parse_args()

    spec = load_spec(args.spec)
    result = generate(spec)
    write_json(args.out, result)

    print("[gen_routes] OK: no forwarding loops. Wrote %s" % args.out)
    for sw in sorted(result["next_hop"]):
        print("  %s:" % sw)
        for ip in sorted(result["next_hop"][sw]):
            print("    %-12s -> %s" % (ip, result["next_hop"][sw][ip]))


if __name__ == "__main__":
    main()
