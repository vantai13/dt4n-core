#!/usr/bin/env python3
"""Measure S6 at real-time and accelerated tick scales, emitting RSS only."""
from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer


REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
RUNS = ("RS-soak2M-s4001-r1", "RS-soak2M-s4002-r2", "RS-soak2M-s4003-r3")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


def rss_kib():
    with open("/proc/self/statm", encoding="ascii") as stream:
        return int(stream.read().split()[1]) * PAGE_SIZE // 1024


def _sample(series, started):
    series.append({"t_s": round(time.monotonic() - started, 1), "rss_kib": rss_kib()})


def soak(segments, scorer_factory, *, realtime, n_ticks, sample_every_s):
    """Process registered streams; reset delivery state at each run boundary."""
    gc.collect()
    started = last = time.monotonic()
    series = [{"t_s": 0.0, "rss_kib": rss_kib()}]
    n_error = 0
    processed = 0
    for snapshots in segments:
        scorer, fsm = scorer_factory()
        for snapshot in snapshots:
            if processed >= n_ticks:
                break
            try:
                fsm.step(scorer.observe(snapshot))
            except Exception:
                n_error += 1
            processed += 1
            if realtime:
                time.sleep(max(0.0, processed - (time.monotonic() - started)))
            now = time.monotonic()
            if now - last >= sample_every_s:
                _sample(series, started)
                last = now
        if processed >= n_ticks:
            break
    if processed != n_ticks:
        raise RuntimeError("nguon chi co %d/%d tick" % (processed, n_ticks))
    gc.collect()
    _sample(series, started)
    return series, n_error


def summarize(series, n_ticks, n_error):
    start, end = series[0]["rss_kib"], series[-1]["rss_kib"]
    tail = series[len(series) // 2 :]
    span = tail[-1]["t_s"] - tail[0]["t_s"]
    slope = (tail[-1]["rss_kib"] - tail[0]["rss_kib"]) / span * 60.0 if span else 0.0
    return {
        "n_ticks": n_ticks,
        "n_error": n_error,
        "duration_s": round(series[-1]["t_s"], 1),
        "rss_start_kib": start,
        "rss_end_kib": end,
        "rss_peak_kib": max(item["rss_kib"] for item in series),
        "delta_kib": end - start,
        "delta_mib": round((end - start) / 1024.0, 4),
        "second_half_slope_kib_per_min": round(slope, 2),
        "shape": "flat" if abs(slope) < 5 else "still_growing",
        "series": series,
    }


def main():
    prereg = json.loads((REPORT / "phase6r_stability_prereg.json").read_text())
    for relative, expected in prereg["content"]["code_sha256"].items():
        if C.sha256_file(C.ROOT / relative) != expected:
            raise SystemExit("code doi sau dang ky: %s" % relative)

    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**json.loads((REPORT / "phase6r_amendment_2.json").read_text())["content"]["fsm"]["params"])
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]
    snapshots = [[json.loads(line) for line in (RAW / (run + ".jsonl")).read_text().splitlines() if line.strip()] for run in RUNS]

    def fresh():
        return (
            FastOnlineScorer(model, expected_collector_version=version, conservation=conservation, conservation_mode="shadow"),
            DetectorFSM(params, None),
        )

    print("soak real-time 30 minutes (1800 ticks at 1 Hz)...", flush=True)
    rt_series, rt_errors = soak(snapshots[:1], fresh, realtime=True, n_ticks=1800, sample_every_s=30.0)
    realtime = summarize(rt_series, 1800, rt_errors)
    print("  RSS %d -> %d KiB (delta %.4f MiB, %s)" % (
        realtime["rss_start_kib"], realtime["rss_end_kib"], realtime["delta_mib"], realtime["shape"]
    ), flush=True)

    print("soak accelerated (10794 ticks)...", flush=True)
    acc_series, acc_errors = soak(snapshots, fresh, realtime=False, n_ticks=10794, sample_every_s=5.0)
    accelerated = summarize(acc_series, 10794, acc_errors)
    print("  RSS %d -> %d KiB (delta %.4f MiB, %s)" % (
        accelerated["rss_start_kib"], accelerated["rss_end_kib"], accelerated["delta_mib"], accelerated["shape"]
    ), flush=True)

    target = 1.0
    content = {
        "lesson": "6R.6",
        "slo": "S6",
        "target_mib": target,
        "phase2_baseline": {"file": "soak_30min.json", "rss_kib": [29244, 29456], "delta_kib": 212},
        "rss_source": "/proc/self/statm field[1] x PAGE_SIZE",
        "rss_rationale": "current RSS supports a curve; ru_maxrss is only a high-water mark",
        "realtime_30min": realtime,
        "accelerated": accelerated,
        "measurement_of_record": "realtime_30min",
        "why_two_scales": "real time tests time-dependent growth and Phase-2 comparability; accelerated tests tick-dependent growth",
        "verdict": "PASS" if realtime["delta_mib"] <= target and realtime["n_error"] == 0 else "FAIL",
        "firewall_compliance": {"amendment_6": True, "emits_resource_metrics_only": True, "reads_labels": False},
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(REPORT / "phase6r_soak.json", {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
