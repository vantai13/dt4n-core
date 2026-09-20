#!/usr/bin/env python3
"""E2E Phase 8.5: dashboard phai noi that ve VONG KIN, khong chi ve detector.

Bon kich ban, moi cai ung voi mot dong validation:
  1. detector `normal` + controller MITIGATING  -> KHONG duoc all-clear
  2. controller chet (detector VAN song)        -> STALE <= 5 s, khong bi che
  3. mo trang luc controller da chet            -> STALE ngay, khong phai IDLE
  4. STALE thi NGUNG dem nguoc
"""
from __future__ import annotations

import sys
import time

import pytest

from ml import campaign as C

sys.path.insert(0, str(C.ROOT / "scripts"))
pw = pytest.importorskip("playwright.sync_api")
if not (C.ROOT / "dashboard/dist/index.html").exists():
    pytest.skip("chua build dashboard/dist", allow_module_level=True)
from phase7_fake_ditto import FakeDitto, controlloop_doc, detector_doc  # noqa: E402

DET = "[data-detector-freshness]"
CTL = "[data-control-freshness]"
CTL_FRESH = f"() => document.querySelector('{CTL}')?.dataset.controlFreshness === 'fresh'"
CTL_STALE = f"() => document.querySelector('{CTL}')?.dataset.controlFreshness === 'stale'"


def mode_is(mode):
    return f"() => document.querySelector('{CTL}')?.dataset.controlMode === '{mode}'"


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as playwright:
        try:
            instance = playwright.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:
            pytest.skip("khong mo duoc chromium: %s" % exc)
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
    page.wait_for_selector(CTL, timeout=10000)
    return page


def test_mitigating_khong_duoc_all_clear(browser, ditto):
    """Bai hoc 8.2 o tang UI: `normal` trong luc dang giam thieu la su khoe manh
    DO CHINH CONTROLLER TAO RA. Noi "All systems normal" luc do la noi doi."""
    ditto.beating.set()
    ditto.control_beating.set()
    ditto.set_control(mode="MITIGATING", target="h1", limit_mbps=7.0,
                      hold_remaining_s=42.0)
    page = open_page(browser, ditto)
    page.wait_for_function(mode_is("MITIGATING"), timeout=8000)
    body = page.inner_text("body")
    assert "All systems normal" not in body
    assert "ĐANG GIẢM THIỂU" in body
    assert "h1" in body and "7" in body
    # detector VAN bao normal - UI khong duoc sua lai detector
    assert page.evaluate(
        f"() => document.querySelector('{DET}')?.dataset.detectorState") == "normal"


def test_controller_chet_thi_stale_duoi_5s_va_khong_lay_detector(browser, ditto):
    """Chong masking: detector song KHONG duoc che controller chet."""
    ditto.beating.set()
    ditto.control_beating.set()
    ditto.set_control(mode="IDLE")
    page = open_page(browser, ditto)
    page.wait_for_function(CTL_FRESH, timeout=8000)
    page.wait_for_function(
        f"() => document.querySelector('{DET}')?.dataset.detectorState === 'normal'",
        timeout=8000)
    assert "All systems normal" in page.inner_text("body")

    ditto.stop_control_heartbeat()          # CHI controller chet
    killed_at = time.monotonic()
    page.wait_for_function(CTL_STALE, timeout=10000, polling=20)
    assert (time.monotonic() - killed_at) <= 5.0
    body = page.inner_text("body")
    assert "All systems normal" not in body
    assert "KHÔNG XÁC NHẬN ĐƯỢC" in body
    # detector KHONG bi lay stale
    assert page.evaluate(
        f"() => document.querySelector('{DET}')?.dataset.detectorFreshness") == "fresh"


def test_mo_trang_luc_controller_da_chet(browser, ditto):
    """Chua tung nhan nhip nao -> STALE (confirmedAt === null), khong phai IDLE."""
    ditto.beating.set()
    ditto.search_control = controlloop_doc("old", 99, "IDLE")
    page = open_page(browser, ditto)
    for _ in range(6):
        assert page.evaluate(CTL_STALE)
        assert "All systems normal" not in page.inner_text("body")
        page.wait_for_timeout(250)


def test_dem_nguoc_dung_lai_khi_stale(browser, ditto):
    ditto.beating.set()
    ditto.control_beating.set()
    ditto.set_control(mode="MITIGATING", target="h1", limit_mbps=7.0,
                      hold_remaining_s=30.0)
    page = open_page(browser, ditto)
    page.wait_for_function(mode_is("MITIGATING"), timeout=8000)
    assert "probe sau" in page.inner_text("body")
    ditto.stop_control_heartbeat()
    page.wait_for_function(CTL_STALE, timeout=10000)
    body = page.inner_text("body")
    assert "probe sau" not in body          # ngung dem, khong dem am
    assert "-" not in body.split("Vòng kín")[-1][:80]


def test_quan_sat_bi_thu_hep_hien_ra_tu_cause(browser, ditto):
    """Nhan la MAP tu cause do CHINH detector cong bo, khong suy dien."""
    ditto.beating.set()
    ditto.control_beating.set()
    ditto.set_control(mode="MITIGATING", target="h1", limit_mbps=7.0)
    page = open_page(browser, ditto)
    page.wait_for_function(mode_is("MITIGATING"), timeout=8000)
    document = detector_doc(ditto.boot, ditto.seq + 50, "unknown")
    document["features"]["decision"]["properties"]["cause"] = "suppressed_intervention"
    ditto.beating.clear()
    ditto.push(document)
    page.wait_for_function(
        "() => document.body.innerText.includes('QUAN SÁT BỊ THU HẸP')",
        timeout=8000)
    body = page.inner_text("body")
    assert "mù" not in body                 # 1/3 round duoi flood khong bi uc che (8.3)
