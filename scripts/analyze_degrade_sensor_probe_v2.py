#!/usr/bin/env python3
"""Probe round 2: mixed mechanisms and pre-registered drop timing.

This v2 was written after v1 results. It never re-scores v1 runs. Floating
totals use math.fsum so Python interpreter changes do not alter the result.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.collector import qdisc_interval  # noqa: E402
from scripts.analyze_degrade_sensor_probe import (  # noqa: E402
    balance_step,
    delta,
    leaf_and_other,
    ovs_tx_drops,
)


RULES_VERSION = "probe-rules-2"
LOW, HIGH = 0.10, 0.85
CLOSURE_TOL = 0.15
NOISE_MULT = 5.0
QLEN_FULL_MIN = 995
MTU_SKB_MAX = 1600

PREDICTIONS = {
    "C0_control_s2-s3": {
        "first_drop_tick": [29, 33],
        "klass": "QUEUE_THEN_DROP",
        "collector_sees": True,
    },
    "C1_long_fault_s1-s2": {
        "first_drop_tick": [40, 55],
        "collector_sees": True,
    },
    "C2_offload_off_s1-s2": {
        "first_drop_tick": [21, 40],
        "collector_sees": True,
        "median_bytes_per_skb_max": MTU_SKB_MAX,
    },
}


def condition_of(meta):
    args = meta["args"]
    offload = args.get("offload", "on")
    fault_ticks = args["revert"] - args["inject"]
    if args["link"] == "s2-s3" and offload == "on" and fault_ticks == 20:
        return "C0_control_s2-s3"
    if args["link"] == "s1-s2" and offload == "on" and fault_ticks >= 40:
        return "C1_long_fault_s1-s2"
    if args["link"] == "s1-s2" and offload == "off" and fault_ticks == 20:
        return "C2_offload_off_s1-s2"
    return None


def leaf_state(interface):
    leaf, parents = leaf_and_other(interface.get("tc_qdisc"))

    def total(rows, key):
        values = [row.get(key) for row in rows]
        return (
            None
            if not rows or any(value is None for value in values)
            else sum(int(value) for value in values)
        )

    return {
        "drops": total(leaf, "drops"),
        "packets": total(leaf, "packets"),
        "bytes": total(leaf, "bytes"),
        "backlog": total(leaf, "backlog"),
        "qlen": total(leaf, "qlen"),
        "parent_drops": total(parents, "drops") if parents else 0,
        "sys_tx_dropped": (interface.get("sysfs") or {}).get("tx_dropped"),
    }


def validity(rows, ping_text):
    """Pre-registered exclusion rule; it never inspects mechanism outcomes."""
    pre = [row for row in rows if row["phase"] == "pre"]
    replies = ping_text.count("icmp_seq") if ping_text else 0
    reasons = []
    if replies == 0:
        reasons.append("ping khong co reply: controller khong cai route")
    if len(pre) >= 3:
        states = [
            leaf_state(row["interfaces"]["upstream_egress"])
            for row in (pre[1], pre[-1])
        ]
        sent = delta(states[1]["packets"], states[0]["packets"])
        if not sent:
            reasons.append("link khong co luu luong o pha pre")
    return {"valid": not reasons, "reasons": reasons}


def analyze_v2(rows, meta, ping_text, switch):
    inject, revert = meta["args"]["inject"], meta["args"]["revert"]
    upstream = [
        leaf_state(row["interfaces"]["upstream_egress"]) for row in rows
    ]
    per_tick = []
    for index in range(1, len(rows)):
        now, old = rows[index], rows[index - 1]
        balance = balance_step(now, old, switch)
        collector = qdisc_interval(
            {
                key: now["interfaces"][key]["collector_leaf"]
                for key in ("upstream_egress", "downstream_egress")
            },
            {
                key: old["interfaces"][key]["collector_leaf"]
                for key in ("upstream_egress", "downstream_egress")
            },
        )
        per_tick.append(
            {
                "i": index,
                "tick": now["tick"],
                "phase": now["phase"],
                "bal": None if balance is None else balance[0] - balance[1],
                "leaf_drop": delta(
                    upstream[index]["drops"], upstream[index - 1]["drops"]
                ),
                "sys_drop": delta(
                    upstream[index]["sys_tx_dropped"],
                    upstream[index - 1]["sys_tx_dropped"],
                ),
                "ovs_drop": delta(
                    ovs_tx_drops(now["ovs_dump_ports"]),
                    ovs_tx_drops(old["ovs_dump_ports"]),
                ),
                "collector": collector,
            }
        )

    pre = [
        item
        for item in per_tick
        if item["phase"] == "pre"
        and item["bal"] is not None
        and item["tick"] >= 2
    ]
    bias = (
        math.fsum(item["bal"] for item in pre) / len(pre) if pre else 0.0
    )
    noise = max(
        (abs(item["bal"] - bias) for item in pre), default=0.0
    )
    window = [
        item
        for item in per_tick
        if inject < item["tick"] <= revert
        and item["phase"] in ("fault", "pre_revert")
    ]
    missing = math.fsum(
        item["bal"] - bias for item in window if item["bal"] is not None
    )

    pre_indices = [
        index for index, row in enumerate(rows) if row["phase"] == "pre"
    ]
    mean_packet_bytes = None
    if len(pre_indices) >= 2:
        packets = delta(
            upstream[pre_indices[-1]]["packets"],
            upstream[pre_indices[0]]["packets"],
        )
        byte_count = delta(
            upstream[pre_indices[-1]]["bytes"],
            upstream[pre_indices[0]]["bytes"],
        )
        mean_packet_bytes = (
            byte_count / packets
            if packets and byte_count is not None
            else None
        )

    def window_total(key):
        values = [item[key] for item in window]
        return None if any(value is None for value in values) else sum(values)

    leaf_packets = window_total("leaf_drop")
    sys_packets = window_total("sys_drop")
    ovs_packets = window_total("ovs_drop")
    pre_revert_index = next(
        (index for index, row in enumerate(rows) if row["phase"] == "pre_revert"),
        None,
    )
    post_revert_index = next(
        (
            index
            for index, row in enumerate(rows)
            if row["phase"] == "post_revert_immediate"
        ),
        None,
    )
    backlog = (
        upstream[pre_revert_index]["backlog"]
        if pre_revert_index is not None
        else None
    )
    backlog_after = (
        upstream[post_revert_index]["backlog"]
        if post_revert_index is not None
        else None
    )

    first_drop = next(
        (item for item in window if (item["leaf_drop"] or 0) > 0), None
    )
    first_drop_tick = first_drop["tick"] if first_drop else None
    qlen_at_first = upstream[first_drop["i"]]["qlen"] if first_drop else None
    skb_sizes = [
        upstream[item["i"]]["backlog"] / upstream[item["i"]]["qlen"]
        for item in window
        if upstream[item["i"]]["qlen"]
        and upstream[item["i"]]["qlen"] >= 10
        and upstream[item["i"]]["backlog"] is not None
    ]
    skb_median = sorted(skb_sizes)[len(skb_sizes) // 2] if skb_sizes else None
    collector_drops = sum(
        item["collector"]["qdiscDropDelta"]
        for item in window
        if item["collector"].get("qdiscValid")
    )
    parent_mirror = all(
        state["parent_drops"] in (state["drops"], 0)
        for state in upstream
        if state["drops"] is not None
    )

    def share_packets(count):
        if count is None or mean_packet_bytes is None or missing <= 0:
            return None
        return count * mean_packet_bytes / missing

    summary = {
        "rules_version": RULES_VERSION,
        "missing_bytes": missing,
        "baseline_noise_per_tick": noise,
        "n_window_ticks": len(window),
        "mean_packet_bytes_pre": mean_packet_bytes,
        "leaf_drop_packets": leaf_packets,
        "kernel_or_ovs_drop_packets": (sys_packets or 0) + (ovs_packets or 0),
        "parent_qdisc_mirrors_leaf": parent_mirror,
        "backlog_bytes_pre_revert": backlog,
        "backlog_bytes_post_revert": backlog_after,
        "first_leaf_drop_tick": first_drop_tick,
        "qlen_at_first_drop": qlen_at_first,
        "median_bytes_per_skb_in_queue": skb_median,
        "collector_drop_packets": collector_drops,
        "share_leaf": share_packets(leaf_packets),
        "share_other": share_packets((sys_packets or 0) + (ovs_packets or 0)),
        "share_backlog": (
            backlog / missing if backlog is not None and missing > 0 else None
        ),
    }
    summary["closure"] = (
        None
        if None
        in (
            summary["share_leaf"],
            summary["share_backlog"],
            summary["share_other"],
        )
        else math.fsum(
            [
                summary["share_leaf"],
                summary["share_backlog"],
                summary["share_other"],
            ]
        )
    )
    summary["klass"] = classify(summary)
    return summary


def classify(summary):
    noise_limit = (
        NOISE_MULT
        * summary["baseline_noise_per_tick"]
        * math.sqrt(max(1, summary["n_window_ticks"]))
    )
    if summary["missing_bytes"] <= noise_limit:
        return "NO_MISSING"
    if (
        summary["closure"] is None
        or abs(summary["closure"] - 1.0) > CLOSURE_TOL
    ):
        return "UNEXPLAINED"
    leaf = summary["share_leaf"]
    backlog = summary["share_backlog"]
    other = summary["share_other"]
    if other >= 0.5:
        return "OUTSIDE_TC"
    if leaf < LOW and backlog >= HIGH:
        return "QUEUE_ONLY"
    if leaf >= HIGH:
        return "DROP_DOMINANT"
    if leaf >= LOW and backlog >= LOW:
        return "QUEUE_THEN_DROP"
    return "UNEXPLAINED"


def check_predictions(summary, condition):
    prediction = PREDICTIONS[condition]
    low, high = prediction["first_drop_tick"]
    checks = {
        "first_drop_in_window": summary["first_leaf_drop_tick"] is not None
        and low <= summary["first_leaf_drop_tick"] <= high,
        "queue_full_at_first_drop": (summary["qlen_at_first_drop"] or 0)
        >= QLEN_FULL_MIN,
        "collector_sees": (summary["collector_drop_packets"] > 0)
        == prediction["collector_sees"],
    }
    if "klass" in prediction:
        checks["klass"] = summary["klass"] == prediction["klass"]
    if "median_bytes_per_skb_max" in prediction:
        checks["manipulation_offload_off"] = (
            summary["median_bytes_per_skb_in_queue"] or 1e9
        ) <= prediction["median_bytes_per_skb_max"]
    checks["teardown_destroys_backlog"] = (
        summary["backlog_bytes_post_revert"] is not None
        and summary["backlog_bytes_pre_revert"]
        and summary["backlog_bytes_post_revert"]
        < 0.05 * summary["backlog_bytes_pre_revert"]
    )
    return checks


def conclude(results):
    """All repetitions for a conclusion must pass the named checks."""

    def all_ok(condition, keys):
        runs = results.get(condition, [])
        return bool(runs) and all(
            all(run[key] for key in keys if key in run) for run in runs
        )

    control_ok = all_ok(
        "C0_control_s2-s3",
        ["first_drop_in_window", "collector_sees", "klass"],
    )
    if not control_ok:
        return {
            "measurement_trusted": False,
            "conclusions": ["KHONG KET LUAN: doi chung C0 khong dat"],
        }

    conclusions = []
    if all_ok(
        "C1_long_fault_s1-s2",
        ["first_drop_in_window", "queue_full_at_first_drop", "collector_sees"],
    ):
        conclusions.append(
            "SENSOR_CORRECT_ON_S1S2: drop xuat hien khi be day va collector thay"
        )
    manipulation_ok = all_ok(
        "C2_offload_off_s1-s2", ["manipulation_offload_off"]
    )
    if not manipulation_ok:
        conclusions.append(
            "C2_INVALID: manipulation offload khong dat, khong kiem duoc GSO"
        )
    elif all_ok(
        "C2_offload_off_s1-s2", ["first_drop_in_window", "collector_sees"]
    ):
        conclusions.append("GSO_EXPLAINS_DELAYED_DROP: tat offload -> drop trong 20 s")
    else:
        conclusions.append("GSO_EXPLANATION_REFUTED")
    return {"measurement_trusted": True, "conclusions": conclusions}


def main(paths):
    from twin.link_direction import UPSTREAM_OF_CORE

    results, table = {}, []
    for path in paths:
        stem = str(path)[: -len(".jsonl")]
        rows = [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        meta = json.loads(Path(stem + ".meta.json").read_text(encoding="utf-8"))
        ping = (
            Path(stem + ".ping.log").read_text(encoding="utf-8")
            if Path(stem + ".ping.log").exists()
            else ""
        )
        condition = condition_of(meta)
        valid = validity(rows, ping)
        if condition is None or not valid["valid"]:
            table.append(
                {
                    "run": Path(stem).name,
                    "condition": condition,
                    "excluded": valid["reasons"]
                    or ["khong thuoc dieu kien v2"],
                }
            )
            continue
        summary = analyze_v2(
            rows, meta, ping, UPSTREAM_OF_CORE[meta["args"]["link"]][0]
        )
        checks = check_predictions(summary, condition)
        results.setdefault(condition, []).append(checks)
        table.append(
            {
                "run": Path(stem).name,
                "condition": condition,
                "summary": summary,
                "checks": checks,
            }
        )
        Path(stem + ".analysis_v2.json").write_text(
            json.dumps({"summary": summary, "checks": checks}, indent=2) + "\n",
            encoding="utf-8",
        )
    report = {
        "rules_version": RULES_VERSION,
        "python": sys.version.split()[0],
        "runs": table,
        "verdict": conclude(results),
    }
    print(json.dumps(report["verdict"], indent=2, ensure_ascii=False))
    for row in table:
        print(
            row["run"],
            row["condition"],
            row.get("checks", row.get("excluded")),
        )
    return report


if __name__ == "__main__":
    output = main(sys.argv[1:])
    (ROOT / "results/probe/v2_report.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
