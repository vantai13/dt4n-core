#!/usr/bin/env python3
"""Offline backpressure experiment comparing synchronous and async delivery."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge.detector_runner import DetectorRunner  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402


SCALE = 10.0
RUN = "F-flood-h1_to_srv1-s3005-r1"
SLOW = (18.0, 32.0)
SLOW_S = 5.0
FAST_S = 0.02
SCAN_S = 0.07
OUT = C.ROOT / "results/report/phase7_runner_backpressure.json"


class FakeDitto:
    def __init__(self, t0):
        self.t0 = t0
        self.received = []

    def logical(self):
        return (time.monotonic() - self.t0) * SCALE

    def __call__(self, thing_id, body):
        logical_time = self.logical()
        duration = SLOW_S if SLOW[0] <= logical_time < SLOW[1] else FAST_S
        time.sleep(duration / SCALE)
        features = body["features"]
        self.received.append(
            {
                "t": round(self.logical(), 2),
                "seq": features["freshness"]["properties"]["seq"],
                "state": features["decision"]["properties"]["state"],
            }
        )
        return True, "204"


def replay(mode: str) -> dict:
    snapshots = C.read_snapshots(C.ROOT / "data/phase5/raw" / (RUN + ".jsonl"))
    release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
    prereg = json.loads(
        (C.ROOT / "results/report/phase7_prereg.json").read_text()
    )
    t0 = time.monotonic()
    ditto = FakeDitto(t0)
    runner = DetectorRunner(release, prereg, ditto)
    if mode == "async":
        runner.start_writer()
    base = 1.9e9
    seen_indices = []
    overruns = 0
    next_due = t0
    while True:
        now = time.monotonic()
        index = int(round((now - t0) * SCALE))
        if index >= len(snapshots):
            break
        snapshot = dict(snapshots[index])
        snapshot["t_source"] = base + (now - t0) * SCALE
        time.sleep(SCAN_S / SCALE)
        runner.on_tick(index, snapshot, index)
        if mode == "sync":
            item = runner.mailbox.take(timeout=0)
            if item:
                runner.transport("x", item[0])
        seen_indices.append(index)
        next_due += 1.0 / SCALE
        if time.monotonic() > next_due:
            overruns += 1
            next_due = time.monotonic()
        time.sleep(max(0.0, next_due - time.monotonic()))
    time.sleep(1.0)
    runner.stop()
    missed = sorted(set(range(len(snapshots))) - set(seen_indices))
    return {
        "ticks_processed": len(seen_indices),
        "ticks_missed": len(missed),
        "missed_in_fault_window": [index for index in missed if 20 < index <= 40],
        "collector_overruns": overruns,
        "stats": runner.stats(),
        "received_by_ditto": len(ditto.received),
        "ditto_states": [row["state"] for row in ditto.received],
        "ditto_seq_monotonic": all(
            left["seq"] < right["seq"]
            for left, right in zip(ditto.received, ditto.received[1:])
        ),
    }


def main() -> int:
    result = {
        "design": {
            "run": RUN,
            "scale": SCALE,
            "slow_window_s": SLOW,
            "slow_patch_s": SLOW_S,
            "flood_inject_s": 20,
            "flood_revert_s": 40,
        }
    }
    for mode in ("sync", "async"):
        row = replay(mode)
        row["gap_unknown_published"] = sum(
            state == "unknown" for state in row["ditto_states"]
        )
        row["act_published"] = sum(
            state == "act" for state in row["ditto_states"]
        )
        result[mode] = row
        print(
            "%-5s processed=%2d missed=%2d (fault window %d) overruns=%2d "
            "ditto_got=%2d act=%2d unknown=%2d on_tick_p95=%sms dropped=%d"
            % (
                mode,
                row["ticks_processed"],
                row["ticks_missed"],
                len(row["missed_in_fault_window"]),
                row["collector_overruns"],
                row["received_by_ditto"],
                row["act_published"],
                row["gap_unknown_published"],
                row["stats"]["on_tick_p95_ms"],
                row["stats"]["overwritten"] + row["stats"]["failed"],
            )
        )
    C.atomic_json(
        OUT,
        {
            "content": result,
            "content_sha256": C.sha256_bytes(C.canonical_json(result).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
