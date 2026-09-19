#!/usr/bin/env python3
"""Measure live S5 and detector overhead using an ON/OFF/OFF/ON ABBA design."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live, cpu_s  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from measurements.stability import summarize_ms, tick_health  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase7_contention.json"


class OffRecorder:
    def __init__(self):
        self.timeline, self.stop = [], threading.Event()

    def on_tick(self, _n, snapshot, _t_rel):
        if self.stop.is_set():
            raise StopIteration
        self.timeline.append(
            {
                "t_in": time.monotonic(),
                "cycle_scan_ms": snapshot.get("cycle_scan_ms"),
            }
        )


def _safe_run(collector, recorder):
    try:
        collector.run(duration=float("inf"), on_tick=recorder.on_tick)
    except StopIteration:
        pass


def run_block(live, condition, seconds, counter):
    overran0, cpu0, started = counter.overran, cpu_s(), time.monotonic()
    if condition == "ON":
        runner = live.start_detector()
        time.sleep(seconds)
        live.stop_detector()
        timeline = list(runner.timeline)
        extra = {
            "S5_score": summarize_ms(
                [entry["score_ms"] for entry in timeline if entry["published"] != "warming_up"]
            ),
            "on_tick_to_mailbox": summarize_ms(
                [(entry["t2"] - entry["t_in"]) * 1000 for entry in timeline]
            ),
            "runner_stats": runner.stats(),
        }
    else:
        recorder = OffRecorder()
        collector = live.collector("off")
        thread = threading.Thread(
            target=_safe_run, args=(collector, recorder), daemon=True
        )
        thread.start()
        time.sleep(seconds)
        recorder.stop.set()
        thread.join(5)
        timeline, extra = recorder.timeline, {}
    wall = time.monotonic() - started
    return {
        "cond": condition,
        "seconds": round(wall, 1),
        "tick_health": tick_health(timeline),
        "cycle_scan_ms": summarize_ms(
            [entry["cycle_scan_ms"] for entry in timeline if entry.get("cycle_scan_ms")]
        ),
        "process_cpu_pct": 100.0 * (cpu_s() - cpu0) / wall,
        "sync_agent_overran": counter.overran - overran0,
        **extra,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", type=int, default=300)
    parser.add_argument("--url", default="http://127.0.0.1:5173/")
    args = parser.parse_args()
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    blocks = []
    with Live(args.block * 4 + 60) as live, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        for condition in ("ON", "OFF", "OFF", "ON"):
            block = run_block(live, condition, args.block, counter)
            blocks.append(block)
            print(
                "[7.6] %s cycle_scan p95=%s overruns=%s cpu=%.1f%%"
                % (
                    condition,
                    block["cycle_scan_ms"] and round(block["cycle_scan_ms"]["p95_ms"], 1),
                    block["tick_health"]["overruns_gt_1050ms"],
                    block["process_cpu_pct"],
                ),
                flush=True,
            )
        browser.close()

    def pool(condition, key):
        return [
            block[key]["p95_ms"]
            for block in blocks
            if block["cond"] == condition and block.get(key)
        ]

    on, off = pool("ON", "cycle_scan_ms"), pool("OFF", "cycle_scan_ms")
    s5 = [
        block["S5_score"]["p95_ms"]
        for block in blocks
        if block["cond"] == "ON" and block.get("S5_score")
    ]
    content = {
        "lesson": "7.6", "design": "ABBA", "block_s": args.block, "blocks": blocks,
        "S5_live_p95_ms_worst_block": max(s5) if s5 else None,
        "S5_target_ms": 50, "S5_6R_detector_only_p95_ms": 0.943,
        "S5_live_pass": bool(s5) and max(s5) <= 50,
        "cycle_scan_p95_ms_mean": {
            "ON": sum(on) / len(on) if on else None,
            "OFF": sum(off) / len(off) if off else None,
        },
        "overruns": {
            condition: sum(
                block["tick_health"]["overruns_gt_1050ms"]
                for block in blocks if block["cond"] == condition
            )
            for condition in ("ON", "OFF")
        },
        "gaps_gt_1500ms": {
            condition: sum(
                block["tick_health"]["gaps_gt_1500ms"]
                for block in blocks if block["cond"] == condition
            )
            for condition in ("ON", "OFF")
        },
        "cpu_pct_mean": {
            condition: sum(
                block["process_cpu_pct"] for block in blocks if block["cond"] == condition
            ) / 2
            for condition in ("ON", "OFF")
        },
        "log_counts": counter.counts,
        "first_errors": counter.first_errors,
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print({
        key: content[key]
        for key in (
            "S5_live_p95_ms_worst_block", "S5_live_pass", "cycle_scan_p95_ms_mean",
            "overruns", "cpu_pct_mean",
        )
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
