#!/usr/bin/env python3
"""Measure the live Phase 7.5 end-to-end latency budget."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright  # noqa: E402

from bridge import detector_contract as D  # noqa: E402
from bridge.collector import Collector  # noqa: E402
from bridge.detector_runner import (  # noqa: E402
    TIMELINE_SAMPLES,
    DetectorRunner,
    DittoTransport,
)
from measurements.clock_bridge import estimate_offset, to_mono  # noqa: E402
from measurements.e2e_budget import aggregate, decompose, plot  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.design import git_provenance  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from mininet.env_runner import EnvRunner  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase7_e2e_latency.json"
PNG = C.ROOT / "results/report/phase7_e2e_latency.png"
SEL = "[data-detector-freshness]"


def js_state(states):
    condition = " || ".join("s === '%s'" % state for state in states)
    return (
        "() => { const e = document.querySelector('%s'); if (!e) return false;"
        " const s = e.dataset.detectorState;"
        " return e.dataset.detectorFreshness === 'fresh' && (%s) }"
        % (SEL, condition)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--hold", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=7005)
    parser.add_argument("--url", default="http://127.0.0.1:5173/?perf=1")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
    prereg = json.loads((C.ROOT / "results/report/phase7_prereg.json").read_text())
    git_hash = git_provenance()["git_hash"]
    env = EnvRunner(sync_period=1.0, clients=3, do_pingall=True, hard_every=0)
    trials, perf, bridges = [], [], {}
    runner = None
    runner_thread = None
    try:
        env.start()
        env.start_profile_background(
            scenario="normal",
            normal_rate="2M",
            server_bg_rate=2.0,
            duration=(args.trials + args.warmup) * 40 + 120,
        )
        time.sleep(5)
        runner = DetectorRunner(
            release, prereg, DittoTransport(), timeline_samples=TIMELINE_SAMPLES
        )
        collector = Collector(
            env.net,
            interval=1.0,
            net_lock=env.net_lock,
            log_path=os.devnull,
            pretty_log_path=None,
            overwrite=True,
            run_meta=D.live_run_meta(runner.boot_id, git_hash),
        )
        runner_thread = threading.Thread(
            target=runner.run_forever, args=(collector,), daemon=True
        )
        runner_thread.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, wait_until="domcontentloaded")
            page.wait_for_function(js_state(["normal"]), timeout=60000)
            bridges["start"] = estimate_offset(lambda: page.evaluate("performance.now()"))
            for index in range(args.trials + args.warmup):
                page.wait_for_function(js_state(["normal"]), timeout=60000)
                time.sleep(3.0 + rng.uniform(0.0, 1.0))
                scenario = TrafficFlood("h1", "srv1", 47)
                t_a = time.monotonic()
                env.injection.apply(scenario)
                t_b = time.monotonic()
                row = {
                    "i": index,
                    "warmup": index < args.warmup,
                    "tA": t_a,
                    "tB": t_b,
                }
                try:
                    page.wait_for_function(
                        js_state(["suspect", "act"]), timeout=15000, polling=20
                    )
                    row["ui_seen"] = True
                except Exception as exc:
                    row.update(ui_seen=False, error=str(exc)[:200])
                time.sleep(args.hold)
                row["tR"] = time.monotonic()
                env.injection.revert_all()
                trials.append(row)
                print(
                    "[7.5] trial %2d warmup=%s ui_seen=%s"
                    % (index, row["warmup"], row["ui_seen"]),
                    flush=True,
                )
            time.sleep(2.0)
            perf = page.evaluate("window.__dt4nPerf || []")
            bridges["end"] = estimate_offset(lambda: page.evaluate("performance.now()"))
            browser.close()
    finally:
        if runner is not None:
            runner.stop()
        if runner_thread is not None:
            runner_thread.join(timeout=3.0)
        try:
            env.injection.revert_all()
        except Exception:
            pass
        env.close(cleanup_mn=True)

    bridge = min(bridges.values(), key=lambda item: item["error_bound_ms"])
    perf_mono = [
        dict(
            row,
            t4=to_mono(row["t4"], bridge),
            tDom=to_mono(row["tDom"], bridge),
            t5=to_mono(row["t5"], bridge),
        )
        for row in perf
    ]
    rows = [
        decompose(trial, list(runner.timeline), list(runner.writes), perf_mono)
        for trial in trials
    ]
    summary = aggregate(rows)
    content = {
        "lesson": "7.5",
        "git_hash": git_hash,
        "seed": args.seed,
        "event": "flood h1->srv1 47M",
        "clock_bridge": {
            "start": bridges.get("start"),
            "end": bridges.get("end"),
            "drift_ms": abs(
                bridges["end"]["offset_s"] - bridges["start"]["offset_s"]
            ) * 1000,
        },
        **summary,
        "rows": rows,
        "figure": str(PNG.relative_to(C.ROOT)) if plot(rows, PNG) else None,
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    for key, stats in summary["budgets"].items():
        if stats:
            print(
                "%-18s p50=%7.1f p95=%7.1f max=%7.1f"
                % (key, stats["p50_ms"], stats["p95_ms"], stats["max_ms"])
            )
    print("verdict:", summary["verdict_p95"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
