#!/usr/bin/env python3
"""Test pre-registered probe verdict rules on synthetic data."""
from __future__ import annotations

import pytest

from scripts import analyze_degrade_sensor_probe as A


INJECT, REVERT, N = 20, 40, 60
PACKET_BYTES = 1500
META = {"args": {"inject": INJECT, "revert": REVERT, "link": "s1-s2"}}


def make_run(mode):
    rows = []
    total_in = total_out = leaf_packets = leaf_drop = class_drop = backlog = 0
    ping = []
    for tick in range(N):
        faulty = INJECT < tick <= REVERT and mode != "healthy"
        total_in += 150_000
        lost = 30_000 if faulty else 0
        total_out += 150_000 - lost
        leaf_packets += (150_000 - lost) // PACKET_BYTES
        if faulty and mode == "queue":
            backlog += lost
        if faulty and mode == "class_drop":
            class_drop += lost // PACKET_BYTES
        if faulty and mode == "leaf_drop":
            leaf_drop += lost // PACKET_BYTES
        phases = (
            ["pre_revert"]
            if tick == REVERT
            else ["pre"]
            if tick < INJECT
            else ["fault"]
            if tick < REVERT
            else ["post"]
        )
        for phase in phases:
            interface = {
                "tc_qdisc": [
                    {
                        "kind": "htb",
                        "handle": "5:",
                        "root": True,
                        "drops": 0,
                    },
                    {
                        "kind": "netem",
                        "handle": "10:",
                        "parent": "5:1",
                        "drops": leaf_drop,
                        "packets": leaf_packets,
                        "bytes": leaf_packets * PACKET_BYTES,
                        "backlog": backlog,
                    },
                ],
                "tc_class": [
                    {"class": "htb", "handle": "5:1", "drops": class_drop}
                ],
                "sysfs": {"tx_dropped": 0},
                "collector_leaf": {
                    "drops": leaf_drop,
                    "packets": leaf_packets,
                    "signature": [["netem", "10:", "5:1"]],
                },
            }
            quiet = dict(
                interface,
                collector_leaf={
                    "drops": 0,
                    "packets": tick,
                    "signature": [["netem", "10:", "5:1"]],
                },
            )
            rows.append(
                {
                    "tick": tick,
                    "phase": phase,
                    "t_wall": 1000.0 + tick,
                    "interfaces": {
                        "upstream_egress": interface,
                        "downstream_egress": quiet,
                    },
                    "balance_links": {
                        "link-h1-s1": {
                            "node": "h1",
                            "counters": {
                                "tx_bytes": total_in + tick % 3,
                                "rx_bytes": 0,
                            },
                        },
                        "link-s1-s2": {
                            "node": "s1",
                            "counters": {"tx_bytes": total_out, "rx_bytes": 0},
                        },
                    },
                    "ovs_dump_ports": "port 1: tx pkts=1, bytes=1, drop=0, errs=0",
                }
            )
        rtt = 4.0 + (backlog / 20_000 if mode == "queue" else 0.0)
        ping.append(
            "[%.3f] 64 bytes from 10.0.0.4: icmp_seq=%d ttl=64 time=%.1f ms"
            % (1000.0 + tick + 0.5, tick, rtt)
        )
    return rows, "\n".join(ping)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("queue", "H1_QUEUE_THEN_TEARDOWN"),
        ("class_drop", "H2_DROPS_OUTSIDE_LEAF"),
        ("leaf_drop", "H0_SENSOR_SEES_LOSS"),
        ("healthy", "NO_MISSING_TRAFFIC"),
    ],
)
def test_verdict_identifies_mechanism(mode, expected):
    rows, ping = make_run(mode)
    summary, _ = A.analyze(rows, META, ping, "s1")
    assert any(
        flag.startswith(expected) for flag in summary["verdict"]
    ), summary


def test_missing_bytes_accounting_is_exact_for_queue():
    rows, ping = make_run("queue")
    summary, _ = A.analyze(rows, META, ping, "s1")
    assert summary["backlog_bytes_pre_revert"] == pytest.approx(
        summary["missing_bytes"], rel=0.02
    )
    assert summary["leaf_drop_packets"] == 0


def test_collector_bug_is_flagged_when_leaf_drops_but_collector_invalid():
    rows, ping = make_run("leaf_drop")
    for row in rows:
        row["interfaces"]["upstream_egress"]["collector_leaf"] = {
            "drops": 0,
            "packets": 0,
            "signature": [["netem", str(row["tick"]), "5:1"]],
        }
    summary, _ = A.analyze(rows, META, ping, "s1")
    assert any(
        flag.startswith("H3_COLLECTOR_BUG") for flag in summary["verdict"]
    )


def test_counter_reset_is_none_not_zero():
    assert A.delta(5, 10) is None
    assert A.delta(None, 1) is None
    assert A.delta(10, 5) == 5
