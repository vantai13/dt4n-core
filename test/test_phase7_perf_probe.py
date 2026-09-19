from __future__ import annotations

import sys

import pytest

from measurements.clock_bridge import estimate_offset, to_mono
from ml import campaign as C

sys.path.insert(0, str(C.ROOT / "scripts"))
pw = pytest.importorskip("playwright.sync_api")
if not (C.ROOT / "dashboard/dist/index.html").exists():
    pytest.skip("dashboard/dist is not built", allow_module_level=True)
from phase7_fake_ditto import FakeDitto  # noqa: E402

SEL = "[data-detector-freshness]"


def test_probe_marks_are_causal_after_clock_bridge():
    fake = FakeDitto()
    try:
        with pw.sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()
            page.goto(fake.url + "?perf=1", wait_until="domcontentloaded")
            page.wait_for_selector(SEL, timeout=10000)
            fake.beating.set()
            page.wait_for_function(
                f"() => document.querySelector('{SEL}').dataset.detectorState === 'normal'",
                timeout=8000,
            )
            bridge = estimate_offset(lambda: page.evaluate("performance.now()"))
            for state in ("act", "normal", "suspect", "normal", "act", "normal"):
                fake.state = state
                page.wait_for_function(
                    f"() => (window.__dt4nPerf || []).some(r => r.state === '{state}' "
                    f"&& r.t5 !== null && r.seq >= {fake.seq})",
                    timeout=8000,
                )
            perf = page.evaluate("window.__dt4nPerf")
            bridge_end = estimate_offset(lambda: page.evaluate("performance.now()"))
            browser.close()
    finally:
        fake.close()
    pushed = {seq: (state, t) for seq, state, t in fake.push_log}
    tolerance = (bridge["error_bound_ms"] + 1.0) / 1000.0
    checked = 0
    for row in perf:
        if row["source"] != "sse" or row["seq"] not in pushed:
            continue
        t_push = pushed[row["seq"]][1]
        t4, _t_dom, t5 = (to_mono(row[key], bridge) for key in ("t4", "tDom", "t5"))
        assert row["t4"] <= row["tDom"] <= row["t5"]
        assert t4 >= t_push - tolerance
        assert t5 - t_push < 0.5
        checked += 1
    assert checked >= 5
    drift_ms = abs(bridge_end["offset_s"] - bridge["offset_s"]) * 1000
    assert drift_ms < 2.0
