#!/usr/bin/env python3
"""Probe where degraded-link traffic goes; this is not a dataset or R-set."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.collector import (  # noqa: E402
    canonical_link_key,
    link_side_a_intf,
    read_intf_counters_full,
    read_qdisc_drops,
)
from mininet.topology import build_net, start_net  # noqa: E402
from mininet.traffic import (  # noqa: E402
    run_host_shell,
    start_background_load,
    stop_all_iperf,
)
from rl.scenarios import DEFAULT_DELAY, LinkDegrade  # noqa: E402
from twin.link_direction import UPSTREAM_OF_CORE  # noqa: E402


PING_PAIR = {"s1-s2": ("h1", "srv1"), "s2-s3": ("srv1", "srv2")}


def ns_argv(node, argv):
    if getattr(node, "inNamespace", False) and getattr(node, "pid", None):
        return ["mnexec", "-a", str(node.pid)] + argv
    return argv


def run_json(node, argv):
    try:
        process = subprocess.run(
            ns_argv(node, argv), capture_output=True, text=True, timeout=2
        )
        if process.returncode == 0 and process.stdout.strip():
            return json.loads(process.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def sysfs(intf):
    base = "/sys/class/net/%s/statistics/" % intf.name
    names = (
        "tx_bytes",
        "tx_packets",
        "tx_dropped",
        "rx_bytes",
        "rx_packets",
        "rx_dropped",
    )
    output = {}
    for name in names:
        try:
            process = subprocess.run(
                ns_argv(intf.node, ["cat", base + name]),
                capture_output=True,
                text=True,
                timeout=2,
            )
            output[name] = (
                int(process.stdout.strip()) if process.returncode == 0 else None
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            output[name] = None
    return output


def ovs_ports(switch_name):
    process = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", switch_name],
        capture_output=True,
        text=True,
        timeout=2,
    )
    return process.stdout if process.returncode == 0 else None


def find_link(net, key):
    for link in net.links:
        if (
            canonical_link_key(link.intf1.node.name, link.intf2.node.name)
            == "link-" + key
        ):
            return link
    raise SystemExit("khong tim thay link " + key)


def _sha(path):
    import hashlib

    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None
    except OSError:
        return None


OFFLOAD_FEATURES = ("gso", "tso", "gro")


def set_offload(net, state):
    """Set GSO/TSO/GRO on every non-loopback interface and return errors."""
    errors = []
    for node in list(net.hosts) + list(net.switches):
        for intf in node.intfList():
            if intf.name == "lo":
                continue
            argv = ["ethtool", "-K", intf.name]
            for feature in OFFLOAD_FEATURES:
                argv += [feature, state]
            process = subprocess.run(
                ns_argv(node, argv), capture_output=True, text=True, timeout=3
            )
            if process.returncode != 0:
                errors.append(
                    {"intf": intf.name, "stderr": process.stderr.strip()[:200]}
                )
    return errors


def offload_state(net, names):
    """Record actual ethtool state as a manipulation check."""
    output = {}
    for node_name, intf_name in names:
        node = net.get(node_name)
        process = subprocess.run(
            ns_argv(node, ["ethtool", "-k", intf_name]),
            capture_output=True,
            text=True,
            timeout=3,
        )
        output[intf_name] = sorted(
            line.strip()
            for line in process.stdout.splitlines()
            if line.strip().startswith(
                (
                    "generic-segmentation-offload",
                    "tcp-segmentation-offload",
                    "generic-receive-offload",
                )
            )
        )
    return output


def sample(net, key, link, tick, phase, started_monotonic):
    upstream_name = UPSTREAM_OF_CORE[key][0]
    upstream_intf = (
        link.intf1 if link.intf1.node.name == upstream_name else link.intf2
    )
    downstream_intf = link.intf2 if upstream_intf is link.intf1 else link.intf1
    row = {
        "tick": tick,
        "phase": phase,
        "t_rel": round(time.monotonic() - started_monotonic, 6),
        "t_wall": time.time(),
        "interfaces": {},
    }
    for role, intf in (
        ("upstream_egress", upstream_intf),
        ("downstream_egress", downstream_intf),
    ):
        row["interfaces"][role] = {
            "name": intf.name,
            "node": intf.node.name,
            "tc_qdisc": run_json(
                intf.node,
                ["tc", "-j", "-s", "qdisc", "show", "dev", intf.name],
            ),
            "tc_class": run_json(
                intf.node,
                ["tc", "-j", "-s", "class", "show", "dev", intf.name],
            ),
            "sysfs": sysfs(intf),
            "collector_leaf": read_qdisc_drops(intf),
        }

    balance = {}
    for other in net.links:
        node_a, node_b = other.intf1.node.name, other.intf2.node.name
        if upstream_name not in (node_a, node_b):
            continue
        key_other = canonical_link_key(node_a, node_b)
        side = link_side_a_intf(other)
        balance[key_other] = {
            "intf": side.name,
            "node": side.node.name,
            "counters": read_intf_counters_full(side),
        }
    row["balance_links"] = balance
    row["ovs_dump_ports"] = ovs_ports(upstream_name)
    return row


def git_hash():
    try:
        return subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", choices=sorted(PING_PAIR), required=True)
    parser.add_argument("--factor", type=float, required=True)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--inject", type=int, default=20)
    parser.add_argument("--revert", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=15)
    parser.add_argument("--out", default="results/probe")
    parser.add_argument(
        "--offload",
        choices=("on", "off"),
        default="on",
        help="off: tat GSO/TSO/GRO tren moi interface (dieu kien C2)",
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("can root (Mininet)")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = ROOT / args.out
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / (
        "degrade_sensor_%s_f%.4f_off%s_rev%d_%s"
        % (args.link, args.factor, args.offload, args.revert, stamp)
    )
    ping_log = "/tmp/probe_ping_%s.log" % stamp

    net = build_net()
    rows, events = [], []
    offload_errors, offload_observed = None, None
    try:
        start_net(net, do_pingall=False, dump_ports=False)
        offload_errors = set_offload(net, "off") if args.offload == "off" else []
        link0 = find_link(net, args.link)
        probe_names = [
            ("h1", "h1-eth0"),
            (link0.intf1.node.name, link0.intf1.name),
            (link0.intf2.node.name, link0.intf2.name),
        ]
        offload_observed = offload_state(net, probe_names)
        start_background_load(
            net,
            "normal",
            normal_rate="2M",
            server_bg_rate=2.0,
            duration=args.warmup + args.duration + 15,
        )
        source, destination = (net.get(name) for name in PING_PAIR[args.link])
        run_host_shell(
            source,
            "ping -D -i 0.2 -W 2 %s > %s 2>&1 &"
            % (destination.IP(), ping_log),
        )
        link = find_link(net, args.link)
        scenario = LinkDegrade(
            args.link,
            args.factor,
            getattr(link, "dt4n_delay", DEFAULT_DELAY),
            float(link.dt4n_bw),
        )
        time.sleep(args.warmup)

        started_monotonic = time.monotonic()
        for tick in range(args.duration):
            time.sleep(max(0.0, started_monotonic + tick - time.monotonic()))
            if tick == args.inject:
                scenario.apply(net)
                events.append(
                    {
                        "kind": "inject",
                        "tick": tick,
                        "t_rel": time.monotonic() - started_monotonic,
                        "new_bw_mbps": link.dt4n_bw,
                    }
                )
            if tick == args.revert:
                rows.append(
                    sample(
                        net,
                        args.link,
                        link,
                        tick,
                        "pre_revert",
                        started_monotonic,
                    )
                )
                scenario.revert(net)
                events.append(
                    {
                        "kind": "revert",
                        "tick": tick,
                        "t_rel": time.monotonic() - started_monotonic,
                    }
                )
                rows.append(
                    sample(
                        net,
                        args.link,
                        link,
                        tick,
                        "post_revert_immediate",
                        started_monotonic,
                    )
                )
                continue
            phase = (
                "pre"
                if tick < args.inject
                else "fault"
                if tick < args.revert
                else "post"
            )
            rows.append(
                sample(
                    net, args.link, link, tick, phase, started_monotonic
                )
            )
    finally:
        try:
            run_host_shell(
                net.get(PING_PAIR[args.link][0]), 'pkill -f "[p]ing -D"'
            )
            stop_all_iperf(
                *[net.get(name) for name in ("h1", "h2", "h3", "srv1", "srv2")]
            )
        except Exception:
            pass
        net.stop()

    with open(str(base) + ".jsonl", "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    ping_text = (
        Path(ping_log).read_text(encoding="utf-8")
        if Path(ping_log).exists()
        else ""
    )
    Path(str(base) + ".ping.log").write_text(ping_text, encoding="utf-8")
    meta = {
        "kind": "sensor_probe_not_dataset",
        "args": vars(args),
        "events": events,
        "n_samples": len(rows),
        "git_hash": git_hash(),
        "kernel": platform.release(),
        "tc_version": subprocess.run(
            ["tc", "-V"], capture_output=True, text=True
        ).stdout.strip(),
        "python": sys.version.split()[0],
        "collector_unchanged": True,
        "python_executable": sys.executable,
        "env_DT4N_PORT_MAP": os.environ.get("DT4N_PORT_MAP"),
        "port_map_sha256": _sha(os.environ.get("DT4N_PORT_MAP")),
        "offload_requested": args.offload,
        "offload_errors": offload_errors,
        "offload_observed": offload_observed,
        "traffic": "normal 2M/client TCP + srv1->srv2 UDP 2M, giong Phase 5",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(str(base) + ".meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print("[probe] ghi", base.name, "(%d mau)" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
