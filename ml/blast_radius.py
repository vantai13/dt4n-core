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


def fraction_of_local_columns(columns, entities: frozenset[str]) -> float:
    local = [column for column in columns if entity_of(column) is not None]
    return sum(entity_of(column) in entities for column in local) / len(local)
