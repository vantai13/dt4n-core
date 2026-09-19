#!/usr/bin/env python3
"""Lesson 7.7: tai lap bit-exact — build lai verdict tu receipt da niem phong ra DUNG content_sha256."""
from __future__ import annotations

import json
import subprocess

import pytest

from measurements.phase7_verdicts import derive
from ml import campaign as C

R = C.ROOT / "results/report"
V = R / "phase7_verdicts.json"
FILE_OF = {"s12": "phase7_s12_live.json", "e2e": "phase7_e2e_latency.json", "s11": "phase7_s11_live.json",
           "contention": "phase7_contention.json", "soak": "phase7_soak_live_v2.json"}


@pytest.mark.skipif(not V.exists(), reason="chua co phase7_verdicts.json")
def test_verdicts_rebuild_bit_exact():
    doc = json.loads(V.read_text())
    c = doc["content"]
    rc = {k: json.loads((R / "phase7_acceptance" / f).read_text())["content"]
          for k, f in FILE_OF.items() if k in c["receipts"]}
    slo = json.loads((R / "phase6r_slo.json").read_text())["content"]
    v6r = json.loads((R / "phase6r_verdicts.json").read_text())["content"]
    again = derive(slo, v6r, rc, c["pins_6r_ok"], {k: v["history"] for k, v in c["slo"].items() if "history" in v})
    for key in ("slo", "gates", "fails_declared", "budgets_master_plan"):
        assert again[key] == c[key], key
    assert doc["content_sha256"] == C.sha256_bytes(C.canonical_json(c).encode())
    frozen = subprocess.run(["git", "rev-list", "-n", "1", "phase-7-frozen"], cwd=C.ROOT,
                            capture_output=True, text=True).stdout.strip()
    assert c["frozen_commit"] == frozen
