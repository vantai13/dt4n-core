#!/usr/bin/env python3
"""Analyze byte accounting for the pre-registered degrade sensor probe."""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.collector import qdisc_interval  # noqa: E402


MIN_SHARE = 0.5
MAX_LEAF_SHARE_H1 = 0.1
RTT_RATIO_H1 = 5.0
NOISE_MULT = 5.0


def leaf_and_other(qdisc_rows):
    rows = [row for row in (qdisc_rows or []) if isinstance(row, dict)]
    parents = {
        row["parent"].split(":")[0] + ":"
        for row in rows
        if isinstance(row.get("parent"), str)
    }
    leaf = [row for row in rows if row.get("handle") not in parents]
    other = [row for row in rows if row.get("handle") in parents]
    return leaf, other


def total(rows, key):
    values = [row.get(key) for row in rows]
    return (
        None
        if not rows or any(value is None for value in values)
        else sum(int(value) for value in values)
    )


def delta(now, old):
    if now is None or old is None or now < old:
        return None
    return now - old


def interface_view(interface):
    leaf, other = leaf_and_other(interface.get("tc_qdisc"))
    classes = [
        row
        for row in (interface.get("tc_class") or [])
        if isinstance(row, dict)
    ]
    return {
        "leaf_drops": total(leaf, "drops"),
        "leaf_packets": total(leaf, "packets"),
        "leaf_bytes": total(leaf, "bytes"),
        "leaf_backlog": total(leaf, "backlog"),
        "other_drops": total(other, "drops") if other else 0,
        "class_drops": total(classes, "drops") if classes else 0,
        "sys_tx_dropped": (interface.get("sysfs") or {}).get("tx_dropped"),
    }


def ovs_tx_drops(text):
    if not text:
        return None
    values = re.findall(r"tx pkts=\S+, bytes=\S+, drop=(\d+)", text)
    return sum(int(value) for value in values) if values else None


def balance_step(now, old, switch):
    delta_in = delta_out = 0
    for key, current in now["balance_links"].items():
        previous = old["balance_links"].get(key)
        if (
            not previous
            or not current["counters"]
            or not previous["counters"]
        ):
            return None
        tx = delta(
            current["counters"]["tx_bytes"], previous["counters"]["tx_bytes"]
        )
        rx = delta(
            current["counters"]["rx_bytes"], previous["counters"]["rx_bytes"]
        )
        if tx is None or rx is None:
            return None
        if current["node"] == switch:
            delta_out += tx
            delta_in += rx
        else:
            delta_in += tx
            delta_out += rx
    return delta_in, delta_out


def parse_ping(text):
    return [
        (float(match.group(1)), float(match.group(2)))
        for match in re.finditer(
            r"\[(\d+\.\d+)\].*time=([\d.]+) ms", text or ""
        )
    ]


def analyze(rows, meta, ping_text, switch):
    inject = meta["args"]["inject"]
    revert = meta["args"]["revert"]
    upstream = [
        interface_view(row["interfaces"]["upstream_egress"]) for row in rows
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
        other_now = (
            (upstream[index]["other_drops"] or 0)
            + (upstream[index]["class_drops"] or 0)
            + (upstream[index]["sys_tx_dropped"] or 0)
        )
        other_old = (
            (upstream[index - 1]["other_drops"] or 0)
            + (upstream[index - 1]["class_drops"] or 0)
            + (upstream[index - 1]["sys_tx_dropped"] or 0)
        )
        per_tick.append(
            {
                "tick": now["tick"],
                "phase": now["phase"],
                "bal": None if balance is None else balance[0] - balance[1],
                "leaf_drop": delta(
                    upstream[index]["leaf_drops"],
                    upstream[index - 1]["leaf_drops"],
                ),
                "other_drop": delta(other_now, other_old),
                "ovs_drop": delta(
                    ovs_tx_drops(now["ovs_dump_ports"]),
                    ovs_tx_drops(old["ovs_dump_ports"]),
                ),
                "leaf_backlog": upstream[index]["leaf_backlog"],
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
    bias = statistics.mean(item["bal"] for item in pre) if pre else 0.0
    noise = max(abs(item["bal"] - bias) for item in pre) if pre else 0.0
    window = [
        item
        for item in per_tick
        if inject < item["tick"] <= revert
        and item["phase"] in ("fault", "pre_revert")
    ]
    missing = sum(
        item["bal"] - bias for item in window if item["bal"] is not None
    )

    pre_indices = [
        index for index, row in enumerate(rows) if row["phase"] == "pre"
    ]
    mean_packet_bytes = None
    if len(pre_indices) >= 2:
        first, last = upstream[pre_indices[0]], upstream[pre_indices[-1]]
        packet_delta = delta(last["leaf_packets"], first["leaf_packets"])
        byte_delta = delta(last["leaf_bytes"], first["leaf_bytes"])
        mean_packet_bytes = (
            byte_delta / packet_delta
            if packet_delta and byte_delta is not None
            else None
        )

    def packet_sum(key):
        values = [item[key] for item in window]
        return None if any(value is None for value in values) else sum(values)

    leaf_packets = packet_sum("leaf_drop")
    other_packets = packet_sum("other_drop")
    ovs_packets = packet_sum("ovs_drop")
    pre_revert = next(
        (row for row in rows if row["phase"] == "pre_revert"), None
    )
    backlog = (
        interface_view(pre_revert["interfaces"]["upstream_egress"])[
            "leaf_backlog"
        ]
        if pre_revert
        else None
    )

    collector_valid = [
        item["collector"]
        for item in window
        if item["collector"].get("qdiscValid")
    ]
    collector_drops = sum(
        item["qdiscDropDelta"] for item in collector_valid
    )

    inject_wall = next(
        (row["t_wall"] for row in rows if row["tick"] == inject), None
    )
    revert_wall = pre_revert["t_wall"] if pre_revert else None
    pings = parse_ping(ping_text)
    rtt_pre = [value for timestamp, value in pings if inject_wall and timestamp < inject_wall]
    rtt_late = [
        value
        for timestamp, value in pings
        if revert_wall and revert_wall - 5 <= timestamp < revert_wall
    ]

    def share(packet_count):
        if packet_count is None or mean_packet_bytes is None or missing <= 0:
            return None
        return packet_count * mean_packet_bytes / missing

    summary = {
        "missing_bytes": missing,
        "baseline_bias_per_tick": bias,
        "baseline_noise_per_tick": noise,
        "n_window_ticks": len(window),
        "mean_packet_bytes": mean_packet_bytes,
        "leaf_drop_packets": leaf_packets,
        "other_drop_packets": other_packets,
        "ovs_tx_drop_packets": ovs_packets,
        "backlog_bytes_pre_revert": backlog,
        "collector_valid_ticks": len(collector_valid),
        "collector_drop_packets": collector_drops,
        "share_leaf": share(leaf_packets),
        "share_other": share(other_packets),
        "share_ovs": share(ovs_packets),
        "share_backlog": backlog / missing if backlog is not None and missing > 0 else None,
        "rtt_pre_median_ms": statistics.median(rtt_pre) if rtt_pre else None,
        "rtt_late_fault_median_ms": statistics.median(rtt_late) if rtt_late else None,
    }
    summary["verdict"] = verdict(summary)
    return summary, per_tick


def verdict(summary):
    noise_limit = (
        NOISE_MULT
        * summary["baseline_noise_per_tick"]
        * max(1, summary["n_window_ticks"]) ** 0.5
    )
    if summary["missing_bytes"] <= noise_limit:
        return ["NO_MISSING_TRAFFIC: run khong mat luu luong vuot nhieu"]
    flags = []
    if (
        (summary["leaf_drop_packets"] or 0) > 0
        and summary["collector_drop_packets"] == 0
    ):
        flags.append("H3_COLLECTOR_BUG: qdisc la co drop nhung collector tinh 0")
    if (
        (summary["share_leaf"] or 0) >= MIN_SHARE
        and summary["collector_drop_packets"] > 0
    ):
        flags.append("H0_SENSOR_SEES_LOSS")
    rtt_ok = (
        summary["rtt_pre_median_ms"]
        and summary["rtt_late_fault_median_ms"]
        and summary["rtt_late_fault_median_ms"]
        >= RTT_RATIO_H1 * summary["rtt_pre_median_ms"]
    )
    if (
        (summary["share_backlog"] or 0) >= MIN_SHARE
        and (summary["share_leaf"] or 0) < MAX_LEAF_SHARE_H1
        and rtt_ok
    ):
        flags.append("H1_QUEUE_THEN_TEARDOWN")
    if max(summary["share_other"] or 0, summary["share_ovs"] or 0) >= MIN_SHARE:
        flags.append("H2_DROPS_OUTSIDE_LEAF")
    return flags or ["UNEXPLAINED: xem bang ke toan"]


def main(path):
    base = Path(path)
    rows = [
        json.loads(line)
        for line in base.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stem = str(base)[: -len(".jsonl")]
    meta = json.loads(Path(stem + ".meta.json").read_text(encoding="utf-8"))
    ping = (
        Path(stem + ".ping.log").read_text(encoding="utf-8")
        if Path(stem + ".ping.log").exists()
        else ""
    )
    link = meta["args"]["link"]
    from twin.link_direction import UPSTREAM_OF_CORE

    summary, per_tick = analyze(
        rows, meta, ping, UPSTREAM_OF_CORE[link][0]
    )
    output = Path(stem + ".analysis.json")
    output.write_text(
        json.dumps({"summary": summary, "per_tick": per_tick}, indent=2, default=str)
        + "\n",
        encoding="utf-8",
    )
    for key, value in summary.items():
        print("%-28s %s" % (key, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
