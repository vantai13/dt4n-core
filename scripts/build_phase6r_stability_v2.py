#!/usr/bin/env python3
"""Seal the Amendment-7 repair without rewriting any 6R.6 v1 receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C


REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_stability_v2.json"


def load_sealed(name):
    path = REPORT / name
    document = json.loads(path.read_text())
    digest = C.sha256_bytes(C.canonical_json(document["content"]).encode())
    if digest != document["content_sha256"]:
        raise SystemExit("receipt drift: " + name)
    return document


def main():
    if OUT.exists():
        raise SystemExit("phase6r_stability_v2.json already exists; refusing overwrite")
    v1 = load_sealed("phase6r_stability.json")
    amendment = load_sealed("phase6r_amendment_7.json")
    s11_v1 = load_sealed("phase6r_replay_o3.json")
    s11_v2 = load_sealed("phase6r_replay_o3_v2.json")
    latency_v1 = load_sealed("phase6r_latency.json")
    latency_v2 = load_sealed("phase6r_latency_v2.json")
    if s11_v1["content"]["verdict"] != "FAIL" or s11_v2["content"]["verdict"] != "PASS":
        raise SystemExit("S11 repair history is incomplete")
    for item in s11_v2["content"]["runs"].values():
        if item["n_act_entries_in_suppression_window"] != 0 or item["n_suppressed_ticks"] <= 0:
            raise SystemExit("S11 v2 did not satisfy both registered conditions")
    if latency_v2["content"]["S5_verdict_changed"] is not False:
        raise SystemExit("latency correction unexpectedly changed S5")

    implementations = (
        "ml/intervention_log.py",
        "ml/blast_radius.py",
        "ml/rcampaign_runtime.py",
        "ml/fsm.py",
        "scripts/replay_phase6r_s11_v2.py",
        "scripts/measure_phase6r_latency_v2.py",
    )
    evidence = (
        "phase6r_amendment_7.json",
        "phase6r_replay_o3.json",
        "phase6r_replay_o3_v2.json",
        "phase6r_latency.json",
        "phase6r_latency_v2.json",
        "phase6r_stability.json",
    )
    closed = dict(v1["content"]["closed_here"])
    closed["S5"] = {
        "verdict": latency_v2["content"]["verdict"]["FastOnlineScorer"],
        "p95_ms": latency_v2["content"]["per_implementation"]["FastOnlineScorer"]["p95_ms"],
        "cold_start_ms": latency_v2["content"]["per_implementation"]["FastOnlineScorer"]["cold_start_ms"],
        "evidence": "phase6r_latency_v2.json",
        "correction": "cold start now means first scored tick",
    }
    closed["S11"] = {
        "verdict": "PASS",
        "evidence": "phase6r_replay_o3_v2.json",
        "previous_verdict": "FAIL",
        "previous_evidence": "phase6r_replay_o3.json",
        "repair_authority": "phase6r_amendment_7.json",
    }
    content = {
        "lesson": "6R.6-amendment-7-repair",
        "measurement_version": 2,
        "supersedes_for_release_decisions": {
            "file": "phase6r_stability.json",
            "file_sha256": C.sha256_file(REPORT / "phase6r_stability.json"),
            "content_sha256": v1["content_sha256"],
            "history_preserved": True,
        },
        "amendment_7_content_sha256": amendment["content_sha256"],
        "implementation_sha256": {name: C.sha256_file(C.ROOT / name) for name in implementations},
        "evidence_file_sha256": {name: C.sha256_file(REPORT / name) for name in evidence},
        "closed_here": closed,
        "repair_history": {
            "S11_v1": "FAIL: one act entry and zero suppressed ticks in each run",
            "diagnosis": "H2 confirmed; strict subset failed on the omitted s1-s3-s2 detour corridor",
            "registered_fix": "interval lease plus detour-aware causal radius; thresholds unchanged",
            "S11_v2": "PASS: zero act entries and 21 suppressed ticks in each of the same two runs",
            "latency_v1_cold_field": "invalid semantic label: measured warming_up fast-exit",
            "latency_v2_cold_field": "corrected to first scored tick; S5 verdict unchanged",
        },
        "release_gates": {
            "G3_offline_harness": "PASS after amendment 7",
            "G3_phase7_live": "PENDING",
            "G4_S12": "PENDING in Phase 7",
            "phase8_release_blocked": True,
            "unblock_rule": "Phase 7 must pass live S11 and S12; offline replay alone cannot release Phase 8",
        },
        "known_risks": {
            "masking": "an independent real fault on the intervention/detour corridor during the declared interval can be suppressed",
            "lease": "an inject without revert suppresses for at most 120 s, then exposes stale_intervention and resumes alarms",
            "memory_baseline": "detector process measured about 566 MiB RSS; S6 constrains growth, not baseline footprint",
            "latency_contention": "detector-only timing excludes Phase 7 Mininet/Ditto/dashboard contention",
        },
        "deferred": v1["content"]["deferred"],
        "r_set_acceptance_opened": False,
        "labels_opened": False,
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(OUT, {"content": content, "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    print("sealed:", OUT.name)
    print("S11 history: FAIL -> PASS; Phase 8 remains blocked pending live S11 + S12")
    return 0


if __name__ == "__main__":
    sys.exit(main())
