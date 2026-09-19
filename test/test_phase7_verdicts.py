#!/usr/bin/env python3
"""Lesson 7.7: verdict tinh BANG CODE — dung quy tac amendment 3, tat dinh, fail-closed."""
from __future__ import annotations

import copy
import json

from measurements.phase7_verdicts import ORDER, derive
from ml import campaign as C

R = C.ROOT / "results/report"


def content(name):
    return json.loads((R / name).read_text())["content"]


SLO, V6R = content("phase6r_slo.json"), content("phase6r_verdicts.json")
# DRY RUN: receipt 7.4-7.7p1 (commit KHAC NHAU) chi de kiem CO CHE, khong phai nghiem thu.
DRY = {"s12": content("phase7_s12_live.json"), "e2e": content("phase7_e2e_latency.json"),
       "s11": content("phase7_s11_live.json"), "contention": content("phase7_contention.json"),
       "soak": content("phase7_soak_live_v2.json")}


def test_fourteen_rows_and_release_rule():
    out = derive(SLO, V6R, DRY, pins_ok=True)
    assert list(out["slo"]) == ORDER and len(ORDER) == 14
    assert out["slo"]["S1"]["final"] == "FAIL"               # giu nguyen FAIL cua 6R
    assert out["slo"]["S10"]["final"] == "REPORT_ONLY"
    assert all(out["slo"][s]["final"] == "PASS" for s in ("S4", "S5", "S6", "S11", "S12"))
    assert out["gates"]["released"] is True                  # S1 FAIL KHONG chan phat hanh
    assert out["fails_declared"] == ["S1"]


def test_s12_fail_blocks_release():
    rc = copy.deepcopy(DRY)
    rc["s12"]["kill_to_stale"]["max_ms"] = 5400.0
    out = derive(SLO, V6R, rc, pins_ok=True)
    assert out["slo"]["S12"]["final"] == "FAIL" and out["gates"]["G4"] is False
    assert out["gates"]["released"] is False


def test_s11_needs_three_live_interventions():
    rc = copy.deepcopy(DRY)
    rc["s11"]["arms"]["log_first"]["n"] = 2
    out = derive(SLO, V6R, rc, pins_ok=True)
    assert out["slo"]["S11"]["final"] == "NO_DATA" and out["gates"]["released"] is False


def test_missing_receipt_is_no_data_not_pass():
    rc = {k: v for k, v in DRY.items() if k != "soak"}
    out = derive(SLO, V6R, rc, pins_ok=True)
    assert out["slo"]["S6"]["final"] == "NO_DATA"


def test_drifted_6r_logic_invalidates_carried_rows():
    out = derive(SLO, V6R, DRY, pins_ok=False)
    assert out["slo"]["S8"]["final"] == "INVALID" and out["gates"]["released"] is False


def test_deterministic_canonical_sha():
    a = C.canonical_json(derive(SLO, V6R, DRY, pins_ok=True))
    b = C.canonical_json(derive(SLO, V6R, copy.deepcopy(DRY), pins_ok=True))
    assert C.sha256_bytes(a.encode()) == C.sha256_bytes(b.encode())
