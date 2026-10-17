#!/usr/bin/env python3
"""C9-a - do THUC TE tren Chromium: controller chet -> UI STALE <= 5 s (8.8).

Kich ban da co tu 8.5 (test/test_phase8_ui_e2e.py); o day no duoc chay de SINH
MOT RECEIPT, vi mot test pass khong phai mot phep do: nghiem thu can con so.

Ba dieu duoc do trong cung mot phien trinh duyet:
  1. tre tu luc controller ngung nhip den luc UI doi sang STALE   (<= 5000 ms)
  2. detector KHONG bi lay stale  (chong masking nguoc: controller chet khong
     duoc lam UI noi doi ve detector)
  3. IDLE + reason=idle_stale_intervention hien "KHONG THE HANH DONG", khong
     phai "RANH"  (lo hong trung thuc cua UI 8.5, chaos 8.7 lo ra)

Chay: .venv/bin/python scripts/measure_phase8_ui_stale.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_ui_stale.json"
DET = "[data-detector-freshness]"
CTL = "[data-control-freshness]"
CTL_FRESH = ("() => document.querySelector('%s')?.dataset.controlFreshness "
             "=== 'fresh'" % CTL)
CTL_STALE = ("() => document.querySelector('%s')?.dataset.controlFreshness "
             "=== 'stale'" % CTL)
BUDGET_MS = 5000.0
N_TRIALS = 5


def main() -> int:
    if OUT.exists():
        print("[8.8/C9-a] da co receipt, khong ghi de:", OUT)
        return 1
    if not (C.ROOT / "dashboard/dist/index.html").exists():
        print("chua build dashboard/dist")
        return 2
    from playwright.sync_api import sync_playwright

    from phase7_fake_ditto import FakeDitto

    samples, blocked_rows = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        for trial in range(N_TRIALS):
            fake = FakeDitto()
            try:
                fake.beating.set()
                fake.control_beating.set()
                fake.set_control(mode="IDLE", reason="idle_quiet")
                page = browser.new_page()
                page.goto(fake.url, wait_until="domcontentloaded")
                page.wait_for_selector(CTL, timeout=10000)
                page.wait_for_function(CTL_FRESH, timeout=10000)
                page.wait_for_function(
                    "() => document.querySelector('%s')?.dataset.detectorState "
                    "=== 'normal'" % DET, timeout=10000)
                all_clear_before = "All systems normal" in page.inner_text("body")

                fake.stop_control_heartbeat()          # CHI controller chet
                killed_at = time.monotonic()
                page.wait_for_function(CTL_STALE, timeout=15000, polling=20)
                elapsed_ms = (time.monotonic() - killed_at) * 1000.0
                body = page.inner_text("body")
                samples.append({
                    "trial": trial,
                    "stale_after_ms": round(elapsed_ms, 1),
                    "all_clear_before": all_clear_before,
                    "all_clear_after": "All systems normal" in body,
                    "label": "KHÔNG XÁC NHẬN ĐƯỢC" in body,
                    "detector_freshness": page.evaluate(
                        "() => document.querySelector('%s')?.dataset"
                        ".detectorFreshness" % DET),
                })
                page.close()
            finally:
                fake.close()

        # --- muc 3: IDLE bi troi tay khong duoc hien la RANH ---
        for reason, expect in (("idle_quiet", "RẢNH"),
                               ("idle_stale_intervention", "KHÔNG THỂ HÀNH ĐỘNG"),
                               ("idle_out_of_range", "KHÔNG THỂ HÀNH ĐỘNG")):
            fake = FakeDitto()
            try:
                fake.beating.set()
                fake.control_beating.set()
                fake.set_control(mode="IDLE", reason=reason)
                page = browser.new_page()
                page.goto(fake.url, wait_until="domcontentloaded")
                page.wait_for_selector(CTL, timeout=10000)
                page.wait_for_function(CTL_FRESH, timeout=10000)
                page.wait_for_timeout(1500)
                body = page.inner_text("body")
                blocked_rows.append({
                    "reason": reason, "expect_label": expect,
                    "label_present": expect in body,
                    "all_clear": "All systems normal" in body,
                })
                page.close()
            finally:
                fake.close()
        browser.close()

    values = [row["stale_after_ms"] for row in samples]
    values_sorted = sorted(values)
    p95 = values_sorted[min(len(values_sorted) - 1,
                            int(0.95 * (len(values_sorted) - 1) + 0.5))]
    detector_not_infected = all(row["detector_freshness"] == "fresh"
                                for row in samples)
    blocked_ok = all(row["label_present"] for row in blocked_rows) and all(
        (not row["all_clear"]) or row["reason"] == "idle_quiet"
        for row in blocked_rows)
    content = {
        "lesson": "8.8",
        "metric": "C9-a",
        "definition": ("controller ngung nhip tim -> data-control-freshness "
                       "doi sang 'stale' tren trang that (Chromium headless)"),
        "budget_ms": BUDGET_MS,
        "n": len(samples),
        "stale_after_ms": round(p95, 1),
        "max_ms": round(max(values), 1),
        "min_ms": round(min(values), 1),
        "samples": samples,
        "detector_not_infected": detector_not_infected,
        "all_clear_suppressed_after_death": all(not row["all_clear_after"]
                                                for row in samples),
        "blocked_idle_rows": blocked_rows,
        "blocked_idle_pass": blocked_ok,
        "c9a_pass": bool(max(values) <= BUDGET_MS and detector_not_infected
                         and blocked_ok),
        "dashboard_note": ("dashboard/dist duoc build lai o 8.8 sau khi sua "
                           "controlView.js (IDLE bi troi tay). Day la mot thay "
                           "doi cua LOP TRINH BAY, khong dong cham vong dieu khien."),
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[8.8/C9-a] p95 = %.0f ms (max %.0f, n = %d) | detector khong bi lay: %s "
          "| IDLE bi troi tay: %s | PASS = %s"
          % (p95, max(values), len(values), detector_not_infected, blocked_ok,
             content["c9a_pass"]))
    print("wrote", OUT)
    return 0 if content["c9a_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
