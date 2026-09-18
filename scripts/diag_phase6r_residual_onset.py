#!/usr/bin/env python3
"""D-6R7-1: chan doan mo ta residual onset da dang ky trong amendment 8."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.release import DetectorRelease
from ml.serve_fast import FastOnlineScorer

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_diag_residual_onset.json"
RUNS = (
    "RD-degrade-s1-s2-rho200-s4101-r1",
    "RD-degrade-s1-s2-rho150-s4102-r1",
    "RD-degrade-s1-s2-rho125-s4103-r1",
)


def trace(release, path):
    scorer = FastOnlineScorer(
        release.model,
        expected_collector_version=release.content["collector_version"],
        warmup_ticks=int(release.content["warmup_ticks"]),
        conservation=release.conservation,
        conservation_mode="shadow",
    )
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            reading = scorer.observe(json.loads(line))
            if reading.status != "scored":
                continue
            rows.append(
                {
                    "tick": reading.tick,
                    "r_max": reading.cons_r_max,
                    "switch": reading.cons_switch,
                    "alarm": bool(reading.cons_alarm),
                    "k": reading.k,
                }
            )
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/phase6r/raw")
    parser.add_argument("--runs", nargs="*", default=list(RUNS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and OUT.exists():
        print("[D-6R7-1] da ton tai")
        return 1
    release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
    threshold = release.conservation.threshold
    result = {}
    for run_id in args.runs:
        path = C.ROOT / args.data_dir / (run_id + ".jsonl")
        head = path.read_bytes()[:40]
        if head.startswith(b"version https://git-lfs"):
            raise SystemExit("%s la LFS pointer: chay `git lfs pull` truoc" % path)
        rows = trace(release, path)
        first = next((row["tick"] for row in rows if row["alarm"]), None)
        result[run_id] = {"first_alarm_tick": first, "ticks": rows}
        print("\n== %s  R=%.4f  first_alarm_tick=%s" % (run_id, threshold, first))
        print(" tick   r_max    switch  alarm   k")
        for row in rows:
            if 15 <= row["tick"] <= 45:
                residual = "   nan" if row["r_max"] is None else "%.4f" % row["r_max"]
                print(
                    "%5d  %s  %6s  %5s  %3s"
                    % (row["tick"], residual, row["switch"], row["alarm"], row["k"])
                )
    if args.dry_run:
        return 0
    content = {
        "diagnostic_id": "D-6R7-1",
        "label": "POST-HOC MO TA; dang ky o amendment 8; khong doi gi",
        "registered_in_amendment_8_content_sha256": json.loads(
            (REPORT / "phase6r_amendment_8.json").read_text()
        )["content_sha256"],
        "R": threshold,
        "runs": result,
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
