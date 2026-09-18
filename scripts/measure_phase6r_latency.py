#!/usr/bin/env python3
"""Measure S5 while exposing aggregate latency statistics only."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer, OnlineScorer
from ml.serve_fast import FastOnlineScorer


REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
RUNS = ("RS-soak2M-s4001-r1", "RS-soak2M-s4002-r2", "RS-soak2M-s4003-r3")
N_WARMUP = 20


def _verify_frozen_code():
    prereg = json.loads((REPORT / "phase6r_stability_prereg.json").read_text())
    for relative, expected in prereg["content"]["code_sha256"].items():
        if C.sha256_file(C.ROOT / relative) != expected:
            raise SystemExit("code doi sau dang ky: %s" % relative)


def percentile(values, quantile):
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(quantile * (len(ordered) - 1)))))
    return ordered[index]


def measure(scorer_class, snapshots, model, conservation, version, params):
    scorer = scorer_class(
        model,
        expected_collector_version=version,
        conservation=conservation,
        conservation_mode="shadow",
    )
    fsm = DetectorFSM(params, None)
    samples = []
    for snapshot in snapshots:
        started = time.monotonic()
        fsm.step(scorer.observe(snapshot))
        samples.append((time.monotonic() - started) * 1000.0)
    return samples


def main():
    _verify_frozen_code()
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**json.loads((REPORT / "phase6r_amendment_2.json").read_text())["content"]["fsm"]["params"])
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]

    per_implementation = {}
    for name, scorer_class in (("OnlineScorer", OnlineScorer), ("FastOnlineScorer", FastOnlineScorer)):
        pooled, cold = [], []
        for run_id in RUNS:
            snapshots = [json.loads(line) for line in (RAW / (run_id + ".jsonl")).read_text().splitlines() if line.strip()]
            samples = measure(scorer_class, snapshots, model, conservation, version, params)
            cold.append(samples[0])
            pooled.extend(samples[N_WARMUP:])
        per_implementation[name] = {
            "n_samples": len(pooled),
            "n_warmup_excluded": N_WARMUP * len(RUNS),
            "cold_start_ms": round(max(cold), 3),
            "p50_ms": round(percentile(pooled, 0.50), 3),
            "p95_ms": round(percentile(pooled, 0.95), 3),
            "p99_ms": round(percentile(pooled, 0.99), 3),
            "max_ms": round(max(pooled), 3),
            "mean_ms": round(sum(pooled) / len(pooled), 3),
        }
        metric = per_implementation[name]
        print("%-18s p50=%7.3f p95=%7.3f max=%8.3f cold=%8.3f ms" % (
            name, metric["p50_ms"], metric["p95_ms"], metric["max_ms"], metric["cold_start_ms"]
        ))

    target = 50.0
    content = {
        "lesson": "6R.6",
        "slo": "S5",
        "target_ms": target,
        "clock": "time.monotonic",
        "clock_rationale": "wall clock can move under NTP; monotonic measures elapsed work",
        "measures": "OnlineScorer.observe() + DetectorFSM.step()",
        "source_runs": list(RUNS),
        "per_implementation": per_implementation,
        "phase7_implementation": "FastOnlineScorer",
        "verdict": {name: "PASS" if value["p95_ms"] <= target else "FAIL" for name, value in per_implementation.items()},
        "firewall_compliance": {
            "amendment_6": True,
            "emits_percentiles_only": True,
            "emits_tick_indices": False,
            "emits_reading_or_transition_fields": False,
            "reads_labels": False,
        },
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(REPORT / "phase6r_latency.json", {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
