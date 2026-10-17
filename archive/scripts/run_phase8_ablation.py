#!/usr/bin/env python3
"""Ablation 8.6: A (detector) vs C (luat nguong), cung giao thuc voi A/B.

Thay DUY NHAT nguon kich hoat; giu nguyen FSM circuit breaker, backoff,
actuator, lease, audit, reconcile. X lay tu 8 run TRAIN qua _assert_train_path
va KHONG duoc chinh.

HAI nhanh, khong ba: ABBA can bang cho HAI muc; ba muc can o vuong Latin va
kho giai thich hon nhieu.

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_ablation.py --blocks 8
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
    FLOOD_S, PRIMARY_WINDOW, SETTLE_S, TwinSampler, bind_send, run_trial,
)

from controller.policy import DetectorView  # noqa: E402
from controller.threshold_baseline import (  # noqa: E402
    N_ACT, ThresholdState, step, threshold_from_train,
)
from controller.twin_reader import TwinReader  # noqa: E402
from measurements import ab_stats  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml import operating_range as O  # noqa: E402

OUT = C.ROOT / "results/report/phase8_ablation.json"
SEED = 20260920


def threshold_view_provider(twin, threshold_mbps):
    """Dung DetectorView tu LUAT NGUONG thay vi tu detector.

    Doc rate tu CUNG mot twin ma controller dung -> chi khac nguon kich hoat.
    """
    state = {"s": ThresholdState()}

    def provider():
        with twin._lock:
            things = dict(twin.things)
        snapshot = {"things": {}}
        for thing_id, body in things.items():
            if ":host-" not in thing_id:
                continue
            name = thing_id.split(":host-", 1)[1]
            traffic = (((body.get("features") or {}).get("traffic")
                        or {}).get("properties") or {})
            snapshot["things"]["host-" + name] = {
                "attributes": body.get("attributes") or {},
                "features": {"traffic": traffic},
            }
        verdict = step(snapshot, state["s"], threshold_mbps, N_ACT)
        state["s"] = verdict.state
        roles = tuple(sorted(twin.roles().items()))
        affected = (("org.dt4n:host-" + verdict.target,) if verdict.target else ())
        fields = twin.detector_view_fields()      # chi lay freshness, khong lay state
        return DetectorView(
            state="act" if verdict.target else "normal",
            cause="",
            affected=affected,
            roles=roles,
            fresh=fields["fresh"],
            boot_id=fields["boot_id"],
            seq=fields["seq"],
        )

    return provider


def block_order_ac(rng):
    return ["A", "C", "C", "A"] if rng.random() < 0.5 else ["C", "A", "A", "C"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=8)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--flood-s", type=float, default=FLOOD_S)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    out = OUT if not args.tag else OUT.with_name("phase8_ablation_%s.json" % args.tag)
    if out.exists():
        print("[8.6-ablation] da co receipt, khong ghi de:", out)
        return 1

    train_paths = [C.ROOT / O.TRAIN_DIR / (r + ".jsonl") for r in O.TRAIN_RUN_IDS]
    calibration = threshold_from_train(train_paths)
    threshold = calibration["threshold_mbps"]
    print("[8.6-ablation] X = %.6f owner=%s" % (threshold, calibration["owner"]))

    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ("logs/phase8_ablation/%s"
                          % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    audit_dir.mkdir(parents=True, exist_ok=True)

    per_trial_s = SETTLE_S + args.flood_s + 45
    budget_s = int(args.blocks * 4 * per_trial_s + 300)
    trials, orders = [], []
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
        factory = lambda: threshold_view_provider(twin, threshold)  # noqa: E731
        try:
            for block in range(args.blocks):
                order = block_order_ac(rng)
                orders.append(order)
                print("[8.6-ablation] khoi %d: %s" % (block, "".join(order)))
                for index, arm in enumerate(order):
                    row = run_trial(live, twin, sampler, arm, block, index, rng,
                                    detector, audit_dir,
                                    view_provider_factory=factory,
                                    flood_s=args.flood_s)
                    trials.append(row)
                    print("   b%d i%d %s primary=%s cmds=%s%s"
                          % (block, index, arm,
                             None if row["primary"] is None else round(row["primary"], 3),
                             row["secondary"]["n_commands"] if not row["aborted"] else "-",
                             " ABORTED" if row["aborted"] else ""))
        finally:
            sampler.stop()
            stop_sse.set()

    valid = [t for t in trials if not t["aborted"] and t["primary"] is not None]
    n_aborted = sum(1 for t in trials if t["aborted"])
    primary = ab_stats.summarise(valid, key="primary", arm_a="A", arm_b="C")
    commands = ab_stats.summarise(
        [dict(t, value=t["secondary"]["n_commands"]) for t in valid
         if t["secondary"]["n_commands"] is not None],
        key="value", arm_a="A", arm_b="C")

    content = {
        "lesson": "8.6",
        "experiment": "ablation A (detector) vs C (threshold rule)",
        "threshold_mbps": threshold,
        "threshold_owner": calibration["owner"],
        "threshold_source": "8 run train qua ml/operating_range.py::_assert_train_path",
        "n_act_ticks": N_ACT,
        "seed": args.seed,
        "block_orders": ["".join(o) for o in orders],
        "primary_definition": {"quantity": "mean txRate h3", "unit": "Mbps",
                               "window_s": list(PRIMARY_WINDOW),
                               "anchor": "t_flood"},
        "n_trials": len(trials),
        "n_aborted": n_aborted,
        "measurement_valid": bool(trials) and n_aborted / len(trials) <= 0.20,
        "primary": primary,
        "n_commands": commands,
        "prediction_was": ("KHONG co khac biet dang ke tren kich ban flood; khac "
                           "biet nam o cac ca AM TINH (replay offline: luat nguong "
                           "ban vao nan nhan o F-shift-s1-s2 tick 42)"),
        "log_counts": counter.counts,
        "trials": trials,
    }
    C.atomic_json(out, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", out)
    print("primary A-C:", json.dumps(primary, ensure_ascii=False))
    print("so lenh A-C:", json.dumps(commands, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
