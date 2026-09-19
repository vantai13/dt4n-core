#!/usr/bin/env python3
"""Correct two diagnostic definitions in Phase 7.5 while preserving v1."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C  # noqa: E402

V1 = C.ROOT / "results/report/phase7_e2e_latency.json"
OUT = C.ROOT / "results/report/phase7_e2e_latency_v2.json"


def main() -> int:
    v1 = json.loads(V1.read_text())
    rows = [row for row in v1["content"]["rows"] if not row["warmup"]]
    offsets = sorted(
        row["inject_phase"] * row["tick_dt_across_inject_ms"] / 1000.0
        for row in rows
    )
    two_second = [
        row["trial"] for row in rows if row["tick_dt_across_inject_ms"] > 1500
    ]
    content = {
        "supersedes_field_only": ["randomization", "tick_dt_across_inject"],
        "v1_sha256": v1["content_sha256"],
        "verdicts_changed": False,
        "why": "v1 divided the injection offset by a span stretched by net_lock and "
        "the span included a tick inside (tA,tB], compressing phase and making 2 s diagnostic dt",
        "inject_offset_s_sorted": [round(value, 3) for value in offsets],
        "quartile_counts_v2": [
            sum(q / 4 <= value < (q + 1) / 4 for value in offsets)
            for q in range(4)
        ],
        "trials_with_tick_inside_cmd_window": two_second,
        "real_consecutive_dt": "not recoverable from v1 because timeline was not stored; "
        "Collector.run does not skip ticks; future measurements store the v2 field",
        "arithmetic_check": "offset 0.98-0.99 + inject_cmd about 0.35 gives tB about "
        "1.33; next tick about 2.07 gives phys_obs about 0.66 s (observed 660/660/665 ms)",
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(content["quartile_counts_v2"], two_second)
    return 0


if __name__ == "__main__":
    sys.exit(main())
