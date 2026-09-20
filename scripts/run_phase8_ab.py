#!/usr/bin/env python3
"""A/B co ngau nhien hoa cho C5 (Lesson 8.6).

Thiet ke:  N khoi x 4 luot; moi khoi ABBA hoac BAAB do dong xu co seed.
           A = controller BAT; B = controller TAT (detector VAN chay).
Bien chinh: trung binh txRate h3 tren [t_flood + 2, t_flood + 122], bo tick
           rateValid == false (KHONG thay bang 0).
Phan tich:  hieu theo KHOI + bootstrap CI95 + randomization test.

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_ab.py --blocks 8
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
    FLOOD_S, PRIMARY_WINDOW, SECONDARY_WINDOW, SETTLE_S, TwinSampler,
    bind_send, block_order, run_trial,
)

from controller.twin_reader import TwinReader  # noqa: E402
from measurements import ab_stats  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_ab_c5.json"
SEED = 20260920            # ghi vao prereg, KHONG doi sau khi chay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=8)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--flood-s", type=float, default=FLOOD_S)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    out = OUT if not args.tag else OUT.with_name("phase8_ab_c5_%s.json" % args.tag)
    if out.exists():
        print("[8.6] da co receipt, khong ghi de:", out)
        return 1

    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ("logs/phase8_ab/%s"
                          % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    audit_dir.mkdir(parents=True, exist_ok=True)

    per_trial_s = SETTLE_S + args.flood_s + 45
    budget_s = int(args.blocks * 4 * per_trial_s + 300)
    trials = []
    orders = []
    with Live(budget_s) as live:
        detector = live.start_detector()
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,),
                         name="twin-sse", daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published("normal", timeout_s=120)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and "h1-s1" not in twin.observed_bw():
            time.sleep(0.2)
        sampler = TwinSampler(twin).start()
        try:
            for block in range(args.blocks):
                order = block_order(rng)
                orders.append(order)
                print("[8.6] khoi %d: %s" % (block, "".join(order)))
                for index, arm in enumerate(order):
                    row = run_trial(live, twin, sampler, arm, block, index, rng,
                                    detector, audit_dir, flood_s=args.flood_s)
                    trials.append(row)
                    print("   b%d i%d %s primary=%s ticks=%s/%s cmds=%s%s"
                          % (block, index, arm,
                             None if row["primary"] is None else round(row["primary"], 3),
                             row.get("n_ticks"), row.get("n_ticks_invalid"),
                             row["secondary"]["n_commands"] if not row["aborted"] else "-",
                             " ABORTED" if row["aborted"] else ""))
        finally:
            sampler.stop()
            stop_sse.set()

    valid = [t for t in trials if not t["aborted"] and t["primary"] is not None]
    n_aborted = sum(1 for t in trials if t["aborted"])
    primary = ab_stats.summarise(valid, key="primary")
    secondary = {}
    for name in ("h3_window30", "h2", "h1", "srv1_rx"):
        rows = [dict(t, value=t["secondary"][name]) for t in valid
                if t["secondary"][name] is not None]
        secondary[name] = ab_stats.summarise(rows, key="value")

    content = {
        "lesson": "8.6",
        "experiment": "A/B controller ON vs OFF",
        "seed": args.seed,
        "n_blocks_requested": args.blocks,
        "block_orders": ["".join(o) for o in orders],
        "primary_definition": {
            "quantity": "mean txRate cua org.dt4n:host-h3",
            "unit": "Mbps",
            "window_s": list(PRIMARY_WINDOW),
            "anchor": "t_flood (harness phat lenh flood) - KHONG dung t_act vi "
                      "t_act khac nhau giua hai nhanh",
            "invalid_ticks": "rateValid == false bi BO, khong thay bang 0",
        },
        "secondary_window_s": list(SECONDARY_WINDOW),
        "n_trials": len(trials),
        "n_aborted": n_aborted,
        "abort_fraction": round(n_aborted / len(trials), 4) if trials else None,
        "measurement_valid": bool(trials) and n_aborted / len(trials) <= 0.20,
        "primary": primary,
        "c5_pass": bool(primary["mean_diff"] is not None
                        and primary["ci95"][0] is not None
                        and primary["ci95"][0] > 0),
        "secondary": secondary,
        "negative_control_h2_ci_contains_zero": bool(
            secondary["h2"]["ci95"][0] is not None
            and secondary["h2"]["ci95"][0] <= 0 <= secondary["h2"]["ci95"][1]),
        "log_counts": counter.counts,
        "trials": trials,
    }
    C.atomic_json(out, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", out)
    print("primary:", json.dumps(primary, ensure_ascii=False))
    print("C5 =", "PASS" if content["c5_pass"] else "FAIL",
          "| doi chung am h2 chua 0:", content["negative_control_h2_ci_contains_zero"],
          "| huy:", n_aborted, "/", len(trials))
    print("h3 cua so 30 s:", secondary["h3_window30"]["mean_diff"],
          "| h1:", secondary["h1"]["mean_diff"],
          "| srv1_rx:", secondary["srv1_rx"]["mean_diff"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
