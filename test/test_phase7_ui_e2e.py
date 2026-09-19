#!/usr/bin/env python3
"""E2E dashboard đã build trong Chromium với Ditto giả."""
from __future__ import annotations

import random
import sys
import time

import pytest

from ml import campaign as C

sys.path.insert(0, str(C.ROOT / "scripts"))
pw = pytest.importorskip("playwright.sync_api")
if not (C.ROOT / "dashboard/dist/index.html").exists():
    pytest.skip("chưa build dashboard/dist", allow_module_level=True)
from phase7_fake_ditto import FakeDitto, detector_doc  # noqa: E402

SEL = "[data-detector-freshness]"
FRESH = f"() => document.querySelector('{SEL}')?.dataset.detectorFreshness === 'fresh'"
STALE = f"() => document.querySelector('{SEL}')?.dataset.detectorFreshness === 'stale'"


def state_is(state):
    return f"() => document.querySelector('{SEL}')?.dataset.detectorState === '{state}'"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:
            pytest.skip("không mở được chromium: %s" % exc)
        yield instance
        instance.close()


@pytest.fixture
def ditto():
    fake = FakeDitto()
    yield fake
    fake.close()


def open_page(browser, ditto):
    page = browser.new_page()
    page.goto(ditto.url, wait_until="domcontentloaded")
    page.wait_for_selector(SEL, timeout=10000)
    return page


def test_first_load_with_dead_detector_is_stale_never_all_clear(browser, ditto):
    ditto.search_detector = detector_doc("old", 4812, "normal")
    page = open_page(browser, ditto)
    for _ in range(8):
        assert page.evaluate(STALE)
        assert "All systems normal" not in page.inner_text("body")
        page.wait_for_timeout(250)


def test_s12_kill_to_stale_under_5s(browser, ditto, tmp_path):
    ditto.beating.set()
    page = open_page(browser, ditto)
    page.wait_for_function(FRESH, timeout=8000)
    page.wait_for_function(state_is("normal"), timeout=8000)
    assert "All systems normal" in page.inner_text("body")
    samples = []
    for _ in range(6):
        time.sleep(random.uniform(0.0, 1.0))
        ditto.beating.clear()
        killed_at = time.monotonic()
        page.wait_for_function(STALE, timeout=10000, polling=20)
        samples.append((time.monotonic() - killed_at) * 1000)
        assert "All systems normal" not in page.inner_text("body")
        ditto.beating.set()
        page.wait_for_function(FRESH, timeout=8000)
    C.atomic_json(
        tmp_path / "phase7_ui_s12_fake.json",
        {
            "note": "Ditto GIA: do do tre cua logic consumer, khong gom Ditto/SSE that",
            "samples_ms": [round(sample) for sample in samples],
        },
    )
    assert max(samples) < 5000
    assert min(samples) > 1900


def test_old_search_index_after_reconnect_is_rejected(browser, ditto):
    ditto.beating.set()
    page = open_page(browser, ditto)
    page.wait_for_function(FRESH, timeout=8000)
    while ditto.seq < 6:
        time.sleep(0.2)
    ditto.search_detector = detector_doc(
        ditto.boot, 2, "act", ["org.dt4n:host-h1"], True
    )
    ditto.drop_sse()
    page.wait_for_timeout(4000)
    assert page.evaluate(state_is("normal"))
    assert any(row.get("event") == "detector.rejected" for row in ditto.ui_log)


def test_act_highlights_named_entities_and_restart_shows_warming_up(browser, ditto):
    ditto.beating.set()
    page = open_page(browser, ditto)
    page.wait_for_function(FRESH, timeout=8000)
    ditto.state, ditto.act = "act", True
    ditto.affected = (
        "org.dt4n:host-h1",
        "org.dt4n:link-s1-s2",
        "org.dt4n:link-h9-s9",
    )
    page.wait_for_function(state_is("act"), timeout=5000)
    text = page.inner_text("body")
    assert "kênh nhanh" in text and "h9-s9" in text
    assert page.get_attribute(".diagram-container", "data-highlight") == "h1,s1-s2"
    ditto.affected, ditto.act = (), False
    ditto.restart_detector("boot2")
    page.wait_for_function(state_is("warming_up"), timeout=5000)
    assert page.evaluate(FRESH)
