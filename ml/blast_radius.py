#!/usr/bin/env python3
"""Derive an intervention blast radius from the frozen routing table."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from twin.link_direction import canonical_key


@dataclass(frozen=True)
class Routing:
    next_hop: dict
    hosts: dict
    sha256: str

    @classmethod
    def load(cls, path) -> "Routing":
        raw = Path(path).read_bytes()
        document = json.loads(raw)
        return cls(
            next_hop=document["next_hop"],
            hosts=document["hosts"],
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def host_names(self) -> list[str]:
        return sorted(host["name"] for host in self.hosts.values())

    def _ip(self, name):
        for ip_address, host in self.hosts.items():
            if host["name"] == name:
                return ip_address, host["attached_to"]
        raise KeyError("host khong co trong routing: %s" % name)

    def path(self, source: str, destination: str):
        """Return ordered nodes and canonical link keys; reject routing loops."""
        _, switch = self._ip(source)
        destination_ip, _ = self._ip(destination)
        nodes, node = [source, switch], switch
        for _ in range(64):
            next_node = self.next_hop[node][destination_ip]
            nodes.append(next_node)
            if next_node == destination:
                links = [
                    canonical_key(left, right)[len("link-") :]
                    for left, right in zip(nodes, nodes[1:])
                ]
                return nodes, links
            node = next_node
        raise ValueError("vong lap routing %s -> %s" % (source, destination))


def entity_of(column: str) -> str | None:
    head = column.split(".", 1)[0]
    return None if head == "agg" else head


def radius(routing: Routing, targets: dict) -> frozenset[str]:
    """Second-order radius: all paths sharing a directly touched path/link."""
    touched = set(targets.get("links", ()))
    for source, destination in targets.get("flows", ()):
        touched.update(routing.path(source, destination)[1])
    entities: set[str] = set()
    names = routing.host_names()
    for source in names:
        for destination in names:
            if source == destination:
                continue
            nodes, links = routing.path(source, destination)
            if touched & set(links):
                entities.update("link-" + key for key in links)
                entities.update(
                    ("host-" if node in names else "switch-") + node
                    for node in nodes
                )
    return frozenset(entities)


def _switch_graph(routing: Routing) -> dict[str, set[str]]:
    """Infer the physical switch graph represented by frozen next hops."""
    switches = set(routing.next_hop)
    graph = {switch: set() for switch in switches}
    for source, destinations in routing.next_hop.items():
        for next_node in destinations.values():
            if next_node in switches and next_node != source:
                graph[source].add(next_node)
                graph[next_node].add(source)
    return graph


def _alternate_switch_path(routing: Routing, link_key: str) -> list[str]:
    """Shortest deterministic switch path after removing ``link_key``."""
    left, right = link_key.split("-", 1)
    graph = _switch_graph(routing)
    if left not in graph or right not in graph:
        return []
    blocked = frozenset((left, right))
    queue = [[left]]
    seen = {left}
    while queue:
        path = queue.pop(0)
        node = path[-1]
        for neighbor in sorted(graph[node]):
            if frozenset((node, neighbor)) == blocked or neighbor in seen:
                continue
            candidate = path + [neighbor]
            if neighbor == right:
                return candidate
            seen.add(neighbor)
            queue.append(candidate)
    return []


def radius_with_detour(routing: Routing, targets: dict) -> frozenset[str]:
    """Add the alternate switch corridor for link-state interventions.

    The strict FSM subset rule remains unchanged.  This function expands only
    the causal corridor, rather than suppressing on any overlap or declaring
    the whole topology affected.
    """
    entities = set(radius(routing, targets))
    for link_key in targets.get("links", ()):
        path = _alternate_switch_path(routing, link_key)
        entities.update("switch-" + switch for switch in path)
        entities.update(
            canonical_key(left, right)
            for left, right in zip(path, path[1:])
        )
    return frozenset(entities)


def fraction_of_local_columns(columns, entities: frozenset[str]) -> float:
    local = [column for column in columns if entity_of(column) is not None]
    return sum(entity_of(column) in entities for column in local) / len(local)
