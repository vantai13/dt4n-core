#!/usr/bin/env python3
"""Soak S6 v2 (Lesson 7.7 buoc 0): cau hinh PRODUCTION (timeline TAT), giao thuc da dang ky.

    Terminal 1: cd dashboard && npm run dev
    Terminal 2: sudo -E python3 scripts/soak_phase7_live_v2.py

Series:  [0 .. warmup) khong tinh | [warmup .. warmup+30 phut) = CUA SO VERDICT | tail 10 phut.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live, rss_kib, system_rss   # noqa: E402
from playwright.sync_api import sync_playwright                          # noqa: E402

from measurements.stability import rss_slope                             # noqa: E402
from ml import campaign as C                                             # noqa: E402

OUT = C.ROOT / "results/report/phase7_soak_live_v2.json"
PREREG = C.ROOT / "results/report/phase7_s6_v2_prereg.json"


def js_heap_mib(cdp) -> float:
    cdp.send("HeapProfiler.collectGarbage")                    # do SAU GC: loai rac chua don
    metrics = {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
    return metrics["JSHeapUsedSize"] / 2**20


def window(series, t0, t1):
    return [(t, r) for t, r in series if t0 <= t <= t1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warmup-s", type=float, default=300.0)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--tail-min", type=float, default=10.0)
    ap.add_argument("--sample-s", type=float, default=30.0)
    ap.add_argument("--url", default="http://127.0.0.1:5173/")
    args = ap.parse_args()
    prereg = json.loads(PREREG.read_text())                    # PHAI co prereg truoc khi do
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    total = args.warmup_s + (args.minutes + args.tail_min) * 60
    series, heap = [], []
    with Live(int(total) + 60) as live, sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        cdp = page.context.new_cdp_session(page)
        cdp.send("Performance.enable")
        runner = live.start_detector(timeline_samples=0)       # CAU HINH PRODUCTION
        t_ready = time.monotonic()
        while runner.published != "normal" and time.monotonic() - t_ready < 120:
            time.sleep(0.5)                                    # khong dung wait_published: timeline TAT
        sys_start = system_rss()
        t0 = time.monotonic()
        next_heap = 0.0
        while (now := time.monotonic() - t0) < total:
            series.append((round(now, 1), rss_kib()))
            if now >= next_heap:
                heap.append((round(now, 1), round(js_heap_mib(cdp), 3)))
                next_heap += 300.0
            time.sleep(args.sample_s)
        series.append((round(time.monotonic() - t0, 1), rss_kib()))
        heap.append((round(time.monotonic() - t0, 1), round(js_heap_mib(cdp), 3)))
        sys_end = system_rss()
        stats = runner.stats()
        ui = page.evaluate("document.querySelector('[data-detector-freshness]')?.dataset.detectorFreshness")
        browser.close()
    w0, w1 = args.warmup_s, args.warmup_s + args.minutes * 60
    verdict_win = window(series, w0, w1)
    v1_win = window(series, 0, args.minutes * 60)
    tail = window(series, w1, total + 1)
    s6 = rss_slope(verdict_win)
    errors = counter.counts.get("ERROR", 0) + counter.counts.get("CRITICAL", 0)
    content = {
        "lesson": "7.7-step0", "prereg_sha256": prereg["content_sha256"],
        "config": {"timeline_samples": stats["timeline_samples"], "warmup_s": w0, "window_min": args.minutes},
        "S6_v2": {**s6, "window_s": [w0, w1], "target_mib": 1.0,
                  "pass": s6["delta_mib"] is not None and s6["delta_mib"] <= 1.0},
        "v1_protocol_same_run": rss_slope(v1_win),
        "tail": rss_slope(tail) if len(tail) >= 4 else None,
        "series": series,
        "js_heap_mib_after_gc": heap,
        "system_rss_start": sys_start, "system_rss_end": sys_end,
        "errors": errors, "zero_error_pass": errors == 0, "log_counts": counter.counts,
        "first_errors": counter.first_errors, "runner_stats": stats, "ui_freshness_at_end": ui,
    }
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
                        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print({"S6_v2": content["S6_v2"]["delta_mib"], "pass": content["S6_v2"]["pass"],
           "v1_protocol": content["v1_protocol_same_run"].get("delta_mib"), "js_heap": heap[:1] + heap[-1:]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
