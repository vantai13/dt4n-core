#!/usr/bin/env python3
"""E1 (8.9): C1 co PHAN BIET duoc thu pham khong?

Thiet ke ghim o results/report/phase8_closure_prereg.json::E1_c1_control.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402
from phase8_ab_common import (  # noqa: E402
    SETTLE_S,
    TwinSampler,
    bind_send,
    make_controller,
    require_clean,
)
from phase8_infra_health import check as infra_check  # noqa: E402

from controller.audit import read_rows  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.intervention_log import MAX_OPEN_S  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_c1_control.json"
PREREG = "results/report/phase8_closure_prereg.json"
CLIENTS = ("h1", "h2", "h3")
SERVERS = ("srv1", "srv2")
FLOOD_RATE_MBPS = 47
DEFAULT_MBPS = 20.0


def scenarios():
    doc = json.loads((C.ROOT / PREREG).read_text(encoding="utf-8"))["content"]
    e1 = doc["E1_c1_control"]
    return e1["scenarios"], e1["reps_per_scenario"], e1["flood_s"]


def hard_cleanup(live, twin, tag):
    """Go moi flood va dua moi link client-s1 ve 20 Mbps."""
    with live.env.net_lock:
        for src in CLIENTS:
            for dst in SERVERS:
                TrafficFlood(src, dst, 1).revert(live.env.net)
    for host in CLIENTS:
        live.env.send_command(
            {
                "subject": "setBandwidth",
                "target": "org.dt4n:link-%s-s1" % host,
                "params": {"bw": DEFAULT_MBPS},
            },
            cid="c1ctl-cleanup-%s-%s-%d" % (tag, host, int(time.time() * 1000)),
        )
    deadline = time.monotonic() + MAX_OPEN_S + 30
    while time.monotonic() < deadline:
        if twin.detector_view_fields().get("cause") != "suppressed_intervention":
            break
        time.sleep(1.0)
    return require_clean(live, twin, timeout_s=180.0)


def classify_trial(audit_path: Path, culprit: str) -> dict:
    """Doc audit da ghi, khong phan loai tu bien trong bo nho."""
    rows = read_rows(audit_path) if audit_path.exists() else []
    injects = [
        a["link"]
        for r in rows
        if r.get("kind") == "inject"
        for a in r.get("actions") or []
    ]
    reasons = [
        (r.get("cstate_after") or {}).get("reason")
        for r in rows
        if r.get("kind") == "decision"
    ]
    first_act = next(
        (
            r["input"]["affected"]
            for r in rows
            if r.get("kind") == "decision" and r["input"]["state"] == "act"
        ),
        None,
    )
    wrong = [link for link in injects if link != "%s-s1" % culprit]
    outcome = "wrong_target" if wrong else ("correct_latch" if injects else "silent")
    return {
        "outcome": outcome,
        "inject_links": injects,
        "wrong_links": wrong,
        "first_act_affected": first_act,
        "n_probe_target_changed": reasons.count("probe_target_changed"),
        "n_idle_quarantine": reasons.count("idle_quarantine"),
        "idle_reasons": sorted({x for x in reasons if x and x.startswith("idle_")}),
        "audit_sha256": C.sha256_file(audit_path) if audit_path.exists() else None,
    }


def run_one(live, twin, detector, audit_dir, name, spec, flood_s, rng, index):
    ok, detail = hard_cleanup(live, twin, "%s%d" % (name, index))
    if not ok:
        return {"scenario": name, "index": index, "outcome": "aborted", "detail": detail}
    time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))
    audit_path = audit_dir / ("%02d_%s.jsonl" % (index, name))
    controller = make_controller(twin, detector, audit_path)
    controller.bootstrap_safe_state()
    thread = threading.Thread(target=controller.run_forever, name="control", daemon=True)
    thread.start()
    flood = TrafficFlood(spec["src"], spec["dst"], FLOOD_RATE_MBPS)
    t_flood = time.time()
    stop_offset = None
    with live.env.net_lock:
        flood.apply(live.env.net)
    if name == "stop_in_probe":
        deadline = time.monotonic() + flood_s + 60
        while time.monotonic() < deadline and controller.cstate.mode != "PROBING":
            time.sleep(0.05)
        stop_offset = rng.uniform(0.0, 3.0)
        time.sleep(stop_offset)
    else:
        time.sleep(flood_s)
    with live.env.net_lock:
        flood.revert(live.env.net)
    time.sleep(30.0)
    controller.shutdown()
    thread.join(10)
    row = classify_trial(audit_path, spec["culprit"])
    row.update(
        {
            "scenario": name,
            "index": index,
            "t_flood": t_flood,
            "src": spec["src"],
            "dst": spec["dst"],
            "culprit": spec["culprit"],
            "victim": spec.get("victim"),
            "stop_offset_s": stop_offset,
            "audit": str(audit_path.relative_to(C.ROOT)),
        }
    )
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260921)
    args = ap.parse_args()
    if OUT.exists():
        print("da co receipt, khong ghi de:", OUT)
        return 1
    specs, reps, flood_s = scenarios()
    rng = random.Random(args.seed)
    plan = []
    for _ in range(reps):
        block = list(specs)
        rng.shuffle(block)
        plan += block
    health_before = infra_check(raise_on_fail=True)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / (
        "logs/phase8_c1_control/%s"
        % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    audit_dir.mkdir(parents=True, exist_ok=True)
    trials = []
    with Live(int(len(plan) * (SETTLE_S + flood_s + 330) + 600)) as live:
        detector = live.start_detector()
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(
            target=twin.run_forever,
            args=(stop_sse,),
            name="twin-sse",
            daemon=True,
        ).start()
        bind_send(live.env.send_command)
        live.wait_published("normal", timeout_s=120)
        sampler = TwinSampler(twin, hosts=CLIENTS + SERVERS).start()
        try:
            for index, name in enumerate(plan):
                health = infra_check(raise_on_fail=False)
                if not health["healthy"]:
                    trials.append(
                        {
                            "scenario": name,
                            "index": index,
                            "outcome": "aborted",
                            "detail": {"infra": health},
                        }
                    )
                    continue
                row = run_one(
                    live,
                    twin,
                    detector,
                    audit_dir,
                    name,
                    specs[name],
                    flood_s,
                    rng,
                    index,
                )
                trials.append(row)
                print(
                    "[E1] %02d %-14s -> %s %s"
                    % (index, name, row["outcome"], row.get("inject_links"))
                )
        finally:
            hard_cleanup(live, twin, "final")
            sampler.stop()
            stop_sse.set()
    done = [t for t in trials if t["outcome"] != "aborted"]
    by = {
        name: {
            k: sum(
                1
                for t in done
                if t["scenario"] == name and t["outcome"] == k
            )
            for k in ("correct_latch", "wrong_target", "silent")
        }
        for name in specs
    }
    n_wrong = sum(v["wrong_target"] for v in by.values())
    n_nonh1_correct = sum(
        1
        for t in done
        if t["outcome"] == "correct_latch" and t["culprit"] != "h1"
    )
    kn = "KN3" if n_wrong else (
        "KN1" if all(v["silent"] == 0 for v in by.values()) else "KN2"
    )
    content = {
        "lesson": "8.9",
        "experiment": "E1 C1-control",
        "prereg_sha256": C.sha256_file(C.ROOT / PREREG),
        "contract_sha256": C.sha256_file(C.ROOT / "results/report/phase8_contract.json"),
        "policy_sha256": C.sha256_file(C.ROOT / "controller/policy.py"),
        "seed": args.seed,
        "plan": plan,
        "health_before": health_before,
        "n_trials": len(trials),
        "n_aborted": len(trials) - len(done),
        "by_scenario": by,
        "n_wrong_target": n_wrong,
        "n_correct_nonh1_culprit": n_nonh1_correct,
        "outcome": kn,
        "c1_control_pass": n_wrong == 0 and n_nonh1_correct >= 3,
        "log_counts": counter.counts,
        "trials": trials,
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(
        "wrote",
        OUT,
        "|",
        kn,
        "| wrong =",
        n_wrong,
        "| dung (thu pham != h1) =",
        n_nonh1_correct,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
