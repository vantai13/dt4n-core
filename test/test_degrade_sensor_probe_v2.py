#!/usr/bin/env python3
"""Pre-registered probe-v2 rules on synthetic finite-queue data."""
from __future__ import annotations

from scripts import analyze_degrade_sensor_probe_v2 as V


INJECT = 20


def fluid_run(
    *,
    revert,
    excess=145_000,
    skb=1500,
    limit=1000,
    link="s2-s3",
    offload="on",
    n=None,
):
    """Fill a finite queue at ``excess`` bytes/s, then tail-drop."""
    n = n or revert + 20
    rows, ping = [], []
    t_in = t_out = sent_packets = drops = 0
    backlog = 0
    for tick in range(n):
        faulty = INJECT < tick <= revert
        t_in += 300_000
        if faulty:
            room = limit * skb - backlog
            added = min(excess, room)
            backlog += added
            drops += (excess - added) // skb
        t_out += 300_000 - (excess if faulty else 0)
        sent_packets += (300_000 - (excess if faulty else 0)) // skb
        phases = (
            ["pre_revert", "post_revert_immediate"]
            if tick == revert
            else ["pre"]
            if tick < INJECT
            else ["fault"]
            if tick < revert
            else ["post"]
        )
        for phase in phases:
            current_backlog = backlog if phase != "post_revert_immediate" else 0
            interface = {
                "tc_qdisc": [
                    {
                        "kind": "htb",
                        "handle": "5:",
                        "root": True,
                        "drops": drops,
                    },
                    {
                        "kind": "netem",
                        "handle": "10:",
                        "parent": "5:1",
                        "drops": drops,
                        "packets": sent_packets,
                        "bytes": sent_packets * skb,
                        "backlog": current_backlog,
                        "qlen": current_backlog // skb,
                    },
                ],
                "tc_class": [],
                "sysfs": {"tx_dropped": 0},
                "collector_leaf": {
                    "drops": drops,
                    "packets": sent_packets,
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
                        "link-a-s2": {
                            "node": "a",
                            "counters": {
                                "tx_bytes": t_in + tick % 3,
                                "rx_bytes": 0,
                            },
                        },
                        "link-s2-s3": {
                            "node": "s2",
                            "counters": {"tx_bytes": t_out, "rx_bytes": 0},
                        },
                    },
                    "ovs_dump_ports": (
                        "port 1: tx pkts=1, bytes=1, drop=0, errs=0"
                    ),
                }
            )
        ping.append(
            "[%.3f] 64 bytes from x: icmp_seq=%d ttl=64 time=12.1 ms"
            % (1000.5 + tick, tick)
        )
        if tick == revert:
            backlog = 0
    meta = {
        "args": {
            "inject": INJECT,
            "revert": revert,
            "link": link,
            "offload": offload,
        }
    }
    return rows, meta, "\n".join(ping)


def test_mixed_mechanism_is_classified_not_unexplained():
    rows, meta, ping = fluid_run(revert=40)
    summary = V.analyze_v2(rows, meta, ping, "s2")
    assert summary["klass"] == "QUEUE_THEN_DROP"
    assert abs(summary["closure"] - 1) < 0.05
    assert summary["qlen_at_first_drop"] >= V.QLEN_FULL_MIN
    assert V.condition_of(meta) == "C0_control_s2-s3"


def test_short_fault_with_big_skb_is_queue_only():
    rows, meta, ping = fluid_run(
        revert=40, excess=115_000, skb=2900, link="s1-s2"
    )
    summary = V.analyze_v2(rows, meta, ping, "s2")
    assert summary["klass"] == "QUEUE_ONLY"
    assert summary["first_leaf_drop_tick"] is None
    assert V.condition_of(meta) is None


def test_long_fault_predictions_pass_when_physics_holds():
    rows, meta, ping = fluid_run(
        revert=60, excess=115_000, skb=2900, link="s1-s2"
    )
    summary = V.analyze_v2(rows, meta, ping, "s2")
    condition = V.condition_of(meta)
    checks = V.check_predictions(summary, condition)
    assert condition == "C1_long_fault_s1-s2"
    assert summary["first_leaf_drop_tick"] == 46
    assert all(checks.values()), checks


def test_offload_manipulation_failure_invalidates_c2_not_refutes():
    rows, meta, ping = fluid_run(
        revert=40,
        excess=115_000,
        skb=2900,
        link="s1-s2",
        offload="off",
    )
    summary = V.analyze_v2(rows, meta, ping, "s2")
    checks = V.check_predictions(summary, "C2_offload_off_s1-s2")
    assert checks["manipulation_offload_off"] is False

    control_rows, control_meta, control_ping = fluid_run(revert=40)
    control = V.check_predictions(
        V.analyze_v2(control_rows, control_meta, control_ping, "s2"),
        "C0_control_s2-s3",
    )
    verdict = V.conclude(
        {
            "C0_control_s2-s3": [control],
            "C2_offload_off_s1-s2": [checks],
        }
    )
    assert any(
        conclusion.startswith("C2_INVALID")
        for conclusion in verdict["conclusions"]
    )


def test_failed_control_blocks_every_conclusion():
    rows, meta, ping = fluid_run(revert=40, excess=0)
    summary = V.analyze_v2(rows, meta, ping, "s2")
    bad = V.check_predictions(summary, "C0_control_s2-s3")
    assert V.conclude({"C0_control_s2-s3": [bad]})[
        "measurement_trusted"
    ] is False


def test_invalid_run_rule_does_not_look_at_mechanism():
    rows, _meta, _ping = fluid_run(revert=40)
    assert V.validity(rows, "")["valid"] is False
    names = V.validity.__code__.co_names
    assert "analyze_v2" not in names
    assert "classify" not in names


def test_fsum_is_python_version_independent():
    assert V.math.fsum([0.1] * 10) == 1.0
