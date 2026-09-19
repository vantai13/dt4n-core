#!/usr/bin/env python3
"""Run S11 live, forced race, no-log control, lease, and residual analysis."""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402

from bridge.live_controller import LiveController  # noqa: E402
from measurements.stability import window_counts  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.intervention_log import MAX_OPEN_S  # noqa: E402

OUT_S11 = C.ROOT / "results/report/phase7_s11_live.json"
OUT_RESIDUAL = C.ROOT / "results/report/phase7_residual_intervention.json"
COOLDOWN_S = 8.0
TAIL_S = 10.0
HOLD_S, SETTLE_S = 20.0, 5.0


def seal(path, content):
    C.atomic_json(
        path,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )


def one(live, controller, mode, link, rng):
    started_normal = live.wait_published("normal")
    time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))
    pair = controller.new_pair(mode)
    inject = controller.act("inject", link, pair, mode)
    time.sleep(HOLD_S)
    revert_mode = "no_log" if mode == "no_log" else "log_first"
    revert = controller.act("revert", link, pair, revert_mode)
    time.sleep(COOLDOWN_S + TAIL_S + 1.0)
    t0 = inject["t_decide_wall"]
    t1 = revert["t_decide_wall"] + COOLDOWN_S + TAIL_S
    return {
        "mode": mode,
        "link": link,
        "pair": pair,
        "started_from_normal": started_normal,
        "inject": inject,
        "revert": revert,
        "window_wall": [t0, t1],
        "counts": window_counts(list(live.runner.timeline), t0, t1),
    }


def run_lease(live, controller):
    live.wait_published("normal")
    pair = controller.new_pair("lease")
    inject = controller.act("inject", "s1-s2", pair, "log_first")
    time.sleep(MAX_OPEN_S + 8.0)
    timeline = [
        entry
        for entry in live.runner.timeline
        if entry["t_source"] >= inject["t_decide_wall"]
    ]
    expiry = inject["t_decide_wall"] + MAX_OPEN_S
    before = [entry for entry in timeline if entry["t_source"] < expiry]
    after = [entry for entry in timeline if entry["t_source"] >= expiry]
    first_stale = next(
        (entry for entry in after if entry["cause"] == "stale_intervention"), None
    )
    revert = controller.act("revert", "s1-s2", pair, "log_first")
    delay = first_stale["t_source"] - expiry if first_stale else None
    return {
        "pair": pair,
        "t_expiry_wall": expiry,
        "suppressed_before_expiry": sum(
            entry["cause"] == "suppressed_intervention" for entry in before
        ),
        "suppressed_after_expiry": sum(
            entry["cause"] == "suppressed_intervention" for entry in after
        ),
        "stale_ticks_after_expiry": sum(
            entry["cause"] == "stale_intervention" for entry in after
        ),
        "first_stale_delay_s": delay,
        "published_after_expiry": sorted({entry["published"] for entry in after}),
        "pass": delay is not None
        and delay <= 2.0
        and not any(entry["cause"] == "suppressed_intervention" for entry in after),
        "revert": revert,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7006)
    parser.add_argument("--lease", action="store_true")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    rows, lease_row = [], None
    budget_s = args.reps * 3 * 60 + (200 if args.lease else 0)
    with Live(budget_s) as live:
        runner = live.start_detector()
        controller = LiveController(
            runner.intervention_log, live.env.send_command, runner
        )
        live.wait_published("normal", timeout_s=120)
        for rep in range(args.reps):
            arms = ["log_first", "log_late", "no_log"]
            rng.shuffle(arms)
            for mode in arms:
                link = rng.choice(["s1-s2", "s1-s3"])
                row = one(live, controller, mode, link, rng)
                row["rep"] = rep
                rows.append(row)
                print(
                    "[7.6] rep %d %-9s %s %s"
                    % (
                        rep, mode, link,
                        {key: value for key, value in row["counts"].items() if value},
                    ),
                    flush=True,
                )
        if args.lease:
            lease_row = run_lease(live, controller)
            print("[7.6] lease", lease_row["pass"], flush=True)

    def arm(mode):
        selected = [row for row in rows if row["mode"] == mode]
        return {
            "n": len(selected),
            "act_entries": sum(row["counts"]["act_entries"] for row in selected),
            "alarm_entries": sum(row["counts"]["alarm_entries"] for row in selected),
            "env_alarm_ticks": sum(row["counts"].get("env_alarm", 0) for row in selected),
            "suppressed_ticks": sum(row["counts"].get("suppressed", 0) for row in selected),
            "all_started_from_normal": all(row["started_from_normal"] for row in selected),
        }

    arms = {mode: arm(mode) for mode in ("log_first", "log_late", "no_log")}
    verdict = {
        "S11_live_pass": arms["log_first"]["n"] >= 3
        and arms["log_first"]["act_entries"] == 0,
        "race_negative_shows_alarm": arms["log_late"]["alarm_entries"] > 0,
        "control_shows_act": arms["no_log"]["act_entries"] > 0,
        "lease_pass": lease_row["pass"] if lease_row else None,
        "error_records": counter.counts.get("ERROR", 0)
        + counter.counts.get("CRITICAL", 0),
    }
    seal(
        OUT_S11,
        {
            "lesson": "7.6", "seed": args.seed, "cooldown_s": COOLDOWN_S,
            "tail_s": TAIL_S, "arms": arms, "verdict": verdict,
            "lease": lease_row, "rows": rows, "log_counts": counter.counts,
            "first_errors": counter.first_errors,
        },
    )
    residual = [
        row["counts"].get("residual_only", 0)
        for row in rows
        if row["mode"] == "log_first"
    ]
    held = [
        row["counts"].get("held", 0)
        for row in rows
        if row["mode"] == "log_first"
    ]
    seal(
        OUT_RESIDUAL,
        {
            "lesson": "7.6", "per_intervention_residual_only_ticks": residual,
            "p50": sorted(residual)[len(residual) // 2] if residual else None,
            "max": max(residual) if residual else None,
            "per_intervention_held_ticks": held,
            "act_entries_from_residual": 0
            if arms["log_first"]["act_entries"] == 0
            else "inspect rows",
            "note": "residual is not suppressed by InterventionLog; it may only reach suspect",
        },
    )
    print(arms, verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
