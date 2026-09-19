#!/usr/bin/env python3
"""Đo S12 live bằng Chromium, Ditto thật, Mininet và hai kiểu dừng runner."""
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
from bridge.detector_runner import DetectorRunner, DittoTransport  # noqa: E402
from measurements.stats import summarize  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.design import git_provenance  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from mininet.env_runner import EnvRunner  # noqa: E402

OUT = C.ROOT / "results/report/phase7_s12_live.json"
SEL = "[data-detector-freshness]"
FRESH = f"() => document.querySelector('{SEL}')?.dataset.detectorFreshness === 'fresh'"
STALE = f"() => document.querySelector('{SEL}')?.dataset.detectorFreshness === 'stale'"
NORMAL = f"() => document.querySelector('{SEL}')?.dataset.detectorState === 'normal'"


class Hangable:
    def __init__(self, inner):
        self.inner = inner
        self.gate = threading.Event()
        self.released = threading.Event()
        self.gate.set()

    def hang(self):
        self.gate.clear()

    def release(self):
        self.released.set()
        self.gate.set()

    def __call__(self, thing_id, body):
        if not self.gate.is_set():
            self.released.wait()
            return False, "hung"
        return self.inner(thing_id, body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
    prereg = json.loads((C.ROOT / "results/report/phase7_prereg.json").read_text())
    git_hash = git_provenance()["git_hash"]
    env = EnvRunner(sync_period=1.0, clients=3, do_pingall=True, hard_every=0)
    rows = []
    first_load = {}
    try:
        env.start()
        env.start_profile_background(
            scenario="normal",
            normal_rate="2M",
            server_bg_rate=2.0,
            duration=args.trials * 40 + 120,
        )
        time.sleep(5)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(args.url, wait_until="domcontentloaded")
            page.wait_for_selector(SEL, timeout=20000)
            for index in range(args.trials):
                mode = "crash" if index % 2 == 0 else "hang"
                transport = Hangable(DittoTransport())
                runner = DetectorRunner(release, prereg, transport)
                collector = Collector(
                    env.net,
                    interval=1.0,
                    net_lock=env.net_lock,
                    log_path=os.devnull,
                    pretty_log_path=None,
                    overwrite=True,
                    run_meta=D.live_run_meta(runner.boot_id, git_hash),
                )
                thread = threading.Thread(
                    target=runner.run_forever,
                    args=(collector,),
                    daemon=True,
                )
                started_at = time.monotonic()
                thread.start()
                row = {"trial": index + 1, "mode": mode, "bootId": runner.boot_id}
                try:
                    page.wait_for_function(FRESH, timeout=20000, polling=20)
                    row["start_to_fresh_ms"] = round((time.monotonic() - started_at) * 1000)
                    page.wait_for_function(NORMAL, timeout=20000, polling=50)
                    time.sleep(random.uniform(3.0, 6.0))
                    killed_at = time.monotonic()
                    if mode == "crash":
                        runner.stop_event.set()
                    else:
                        transport.hang()
                    page.wait_for_function(STALE, timeout=15000, polling=20)
                    row["kill_to_stale_ms"] = round((time.monotonic() - killed_at) * 1000)
                    row["all_clear_shown_while_stale"] = (
                        "All systems normal" in page.inner_text("body")
                    )
                    row["ok"] = True
                except Exception as exc:
                    row.update(ok=False, error=str(exc)[:300])
                finally:
                    runner.stop_event.set()
                    transport.release()
                    thread.join(5)
                    row["stats"] = runner.stats()
                rows.append(row)
                print(json.dumps({
                    key: row.get(key)
                    for key in (
                        "trial", "mode", "start_to_fresh_ms", "kill_to_stale_ms", "ok"
                    )
                }))
                time.sleep(1.0)
            fresh_page = browser.new_page()
            fresh_page.goto(args.url, wait_until="domcontentloaded")
            fresh_page.wait_for_selector(SEL, timeout=20000)
            observations = []
            for _ in range(8):
                observations.append((
                    fresh_page.evaluate(STALE),
                    "All systems normal" in fresh_page.inner_text("body"),
                ))
                fresh_page.wait_for_timeout(250)
            first_load = {
                "always_stale": all(stale for stale, _ in observations),
                "all_clear_ever": any(clear for _, clear in observations),
            }
            browser.close()
    finally:
        env.close(cleanup_mn=True)

    successful = [row for row in rows if row.get("ok")]
    by_mode = {
        mode: summarize([
            row["kill_to_stale_ms"] / 1000
            for row in successful
            if row["mode"] == mode
        ])
        for mode in ("crash", "hang")
    }
    all_values = [row["kill_to_stale_ms"] for row in successful]
    content = {
        "trials": len(rows),
        "ok": len(successful),
        "git_hash": git_hash,
        "kill_to_stale": summarize([value / 1000 for value in all_values]),
        "by_mode": by_mode,
        "start_to_fresh": summarize([
            row["start_to_fresh_ms"] / 1000 for row in successful
        ]),
        "all_clear_while_stale": sum(
            bool(row.get("all_clear_shown_while_stale")) for row in successful
        ),
        "first_load_dead_detector": first_load,
        "S12_pass": bool(all_values)
        and max(all_values) <= 5000
        and len(successful) == len(rows),
        "samples": rows,
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print(json.dumps({
        key: content[key]
        for key in ("kill_to_stale", "S12_pass", "first_load_dead_detector")
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
