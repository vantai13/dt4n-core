#!/usr/bin/env python3
"""Run the 30-minute Phase 7.6 live RSS/error soak."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live, rss_kib, system_rss  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from measurements.stability import rss_slope, summarize_ms, tick_health  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase7_soak_live.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--sample-s", type=float, default=30.0)
    parser.add_argument("--tracemalloc", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:5173/")
    parser.add_argument("--tag", default="", help="hau to file output (chay chan doan, khong de artifact chinh)")
    args = parser.parse_args()
    out = OUT.with_name("phase7_soak_live_%s.json" % args.tag) if args.tag else OUT
    if args.tracemalloc:
        import tracemalloc
        tracemalloc.start(10)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    seconds = args.minutes * 60
    series, top = [], None
    with Live(int(seconds) + 60) as live, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        runner = live.start_detector()
        live.wait_published("normal", timeout_s=120)
        system_start = system_rss()
        if args.tracemalloc:
            snapshot0 = tracemalloc.take_snapshot()
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            series.append((round(time.monotonic() - started, 1), rss_kib()))
            time.sleep(args.sample_s)
        series.append((round(time.monotonic() - started, 1), rss_kib()))
        system_end = system_rss()
        if args.tracemalloc:
            diff = tracemalloc.take_snapshot().compare_to(snapshot0, "filename")
            top = [str(item) for item in diff[:15]]
        stats = runner.stats()
        timeline = list(runner.timeline)[-int(seconds):]
        ui_state = page.evaluate(
            "document.querySelector('[data-detector-freshness]')?.dataset.detectorFreshness"
        )
        browser.close()
    slope = rss_slope(series)
    errors = counter.counts.get("ERROR", 0) + counter.counts.get("CRITICAL", 0)
    content = {
        "lesson": "7.6", "minutes": args.minutes, "tag": args.tag,
        "rss_source": "/proc/self/statm[1] x PAGE (current RSS)",
        "process_rss": {
            **slope, "start_kib": series[0][1], "end_kib": series[-1][1],
            "series": series,
        },
        "S6_target_mib": 1.0,
        "S6_pass": slope["delta_mib"] is not None and slope["delta_mib"] <= 1.0,
        "system_rss_start": system_start, "system_rss_end": system_end,
        "system_rss_note": "deployment condition, not a preregistered SLO",
        "errors": errors, "zero_error_pass": errors == 0,
        "log_counts": counter.counts, "first_errors": counter.first_errors,
        "runner_stats": stats,
        "S5_over_soak": summarize_ms([entry["score_ms"] for entry in timeline]),
        "tick_health": tick_health(timeline),
        "ui_freshness_at_end": ui_state,
        "tracemalloc_top": top,
    }
    C.atomic_json(
        out,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print({key: content[key] for key in ("S6_pass", "zero_error_pass")}, slope)
    return 0


if __name__ == "__main__":
    sys.exit(main())
