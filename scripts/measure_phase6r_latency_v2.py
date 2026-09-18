#!/usr/bin/env python3
"""Correct the cold-start field while preserving the original S5 receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.fsm import FSMParams
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer, OnlineScorer
from ml.serve_fast import FastOnlineScorer
from scripts.measure_phase6r_latency import N_WARMUP, RAW, REPORT, RUNS, measure, percentile


OUT = REPORT / "phase6r_latency_v2.json"
FIRST_SCORED = 1


def summary(samples_by_run):
    pooled = []
    cold = []
    for samples in samples_by_run:
        if len(samples) <= FIRST_SCORED:
            raise ValueError("run has no scored latency sample")
        cold.append(samples[FIRST_SCORED])
        pooled.extend(samples[N_WARMUP:])
    result = {
        "n_samples": len(pooled),
        "n_warmup_excluded": N_WARMUP * len(samples_by_run),
        "cold_start_ms": round(max(cold), 3),
        "cold_start_definition": "first scored tick (index 1); index 0 is warming_up fast-exit",
        "p50_ms": round(percentile(pooled, 0.50), 3),
        "p95_ms": round(percentile(pooled, 0.95), 3),
        "p99_ms": round(percentile(pooled, 0.99), 3),
        "max_ms": round(max(pooled), 3),
        "mean_ms": round(sum(pooled) / len(pooled), 3),
    }
    if not result["max_ms"] >= result["p99_ms"] >= result["p95_ms"] >= result["p50_ms"]:
        raise AssertionError("latency percentile sanity inequality failed")
    return result


def main():
    if OUT.exists():
        raise SystemExit("phase6r_latency_v2.json already exists; refusing overwrite")
    original_path = REPORT / "phase6r_latency.json"
    original = json.loads(original_path.read_text())
    amendment = json.loads((REPORT / "phase6r_amendment_7.json").read_text())
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**json.loads((REPORT / "phase6r_amendment_2.json").read_text())["content"]["fsm"]["params"])
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]

    per_implementation = {}
    for name, scorer_class in (("OnlineScorer", OnlineScorer), ("FastOnlineScorer", FastOnlineScorer)):
        samples_by_run = []
        for run_id in RUNS:
            snapshots = [json.loads(line) for line in (RAW / (run_id + ".jsonl")).read_text().splitlines() if line.strip()]
            samples_by_run.append(measure(scorer_class, snapshots, model, conservation, version, params))
        per_implementation[name] = summary(samples_by_run)
        metric = per_implementation[name]
        print("%-18s cold(scored)=%7.3f p95=%7.3f ms" % (name, metric["cold_start_ms"], metric["p95_ms"]))

    target = original["content"]["target_ms"]
    content = {
        "lesson": "6R.6-latency-correction",
        "slo": "S5",
        "measurement_number": 2,
        "correction": "v1 cold_start_ms used sample[0], which is warming_up fast-exit; v2 uses sample[1], the first scored tick",
        "supersedes_field_only": "phase6r_latency.json::per_implementation.*.cold_start_ms",
        "original_file_sha256": C.sha256_file(original_path),
        "original_content_sha256": original["content_sha256"],
        "amendment_7_content_sha256": amendment["content_sha256"],
        "clock": "time.monotonic",
        "source_runs": list(RUNS),
        "per_implementation": per_implementation,
        "phase7_implementation": "FastOnlineScorer",
        "verdict": {name: "PASS" if value["p95_ms"] <= target else "FAIL" for name, value in per_implementation.items()},
        "S5_verdict_changed": False,
        "firewall_compliance": {
            "emits_aggregate_latency_only": True,
            "emits_tick_indices": False,
            "emits_reading_or_transition_fields": False,
            "reads_labels": False,
        },
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(OUT, {"content": content, "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    return 0


if __name__ == "__main__":
    sys.exit(main())
