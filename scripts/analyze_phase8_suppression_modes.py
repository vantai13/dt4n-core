#!/usr/bin/env python3
"""E3 (8.9): phan xu H-BISTABLE / H-FEEDBACK / H0-OUTLIER theo luat da ghim."""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_phase8_gap_reconciliation import OUT_OF_ZONE, campaign  # noqa: E402

from controller.audit import read_rows  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_suppression_modes.json"
PREREG = "results/report/phase8_closure_prereg.json"
SUPPRESSION_MIN_TICKS = 50


def first_alarm_has_out_of_zone(rows):
    for row in rows:
        if row.get("kind") == "decision" and row["input"]["state"] in (
            "act",
            "suspect",
        ):
            return any(OUT_OF_ZONE in e for e in row["input"].get("affected") or ())
    return None


def suppressed_by_half(rows):
    ticks = [r for r in rows if r.get("kind") == "decision"]
    half = len(ticks) // 2

    def count(xs):
        return sum(
            1
            for r in xs
            if r["input"]["state"] == "unknown"
            and r["input"].get("cause") == "suppressed_intervention"
        )

    return count(ticks[:half]), count(ticks[half:])


def background_estimate(ticks_path):
    """bg = srv2.rx - h2.tx moi tick (proxy sach theo amendment 8.8)."""
    if not ticks_path.exists():
        return None
    rows = json.loads(ticks_path.read_text(encoding="utf-8"))
    by_t = {}
    for row in rows:
        by_t.setdefault(round(row["t_wall"]), {})[row["host"]] = row
    bg = [
        values["srv2"]["rx_mbps"] - values["h2"]["tx_mbps"]
        for values in by_t.values()
        if "srv2" in values
        and "h2" in values
        and values["srv2"].get("rate_valid")
        and values["h2"].get("rate_valid")
    ]
    if not bg:
        return None
    return {
        "n": len(bg),
        "median_mbps": round(statistics.median(bg), 3),
        "min_mbps": round(min(bg), 3),
        "n_below_1mbps": sum(1 for value in bg if value < 1.0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True)
    args = ap.parse_args()
    runs = []
    for tag in args.tags.split(","):
        dirs = sorted(glob.glob(str(C.ROOT / ("logs/phase8_stability/%s_*" % tag))))
        if len(dirs) != 1:
            print("tag %s: can DUNG 1 thu muc, thay %d" % (tag, len(dirs)))
            return 2
        directory = Path(dirs[0])
        rows = read_rows(directory / "run_00.jsonl")
        stats = campaign([directory / "run_00.jsonl"])
        first_half, second_half = suppressed_by_half(rows)
        mode = (
            "SUPPRESSION"
            if stats["n_ticks_suppressed"] >= SUPPRESSION_MIN_TICKS
            else "NO_SUPPRESSION"
        )
        runs.append(
            {
                "tag": tag,
                "dir": str(directory.relative_to(C.ROOT)),
                "mode": mode,
                "first_alarm_has_s2_s3": first_alarm_has_out_of_zone(rows),
                "suppressed_first_half": first_half,
                "suppressed_second_half": second_half,
                "mode_switched_within_run": (first_half >= 25) != (second_half >= 25),
                "background": background_estimate(directory / "ticks_00.json"),
                **stats,
            }
        )
    modes = [run["mode"] for run in runs]
    feedback_ok = all(
        (run["first_alarm_has_s2_s3"] is True) == (run["mode"] == "NO_SUPPRESSION")
        and not run["mode_switched_within_run"]
        for run in runs
    )
    bistable_ok = all(
        (run["background"] or {}).get("n_below_1mbps", 1) == 0
        and run["mode"] == "NO_SUPPRESSION"
        and (run["fraction_alarming_out_of_zone"] or 0) > 0.5
        for run in runs
        if run["background"]
    )
    content = {
        "lesson": "8.9",
        "experiment": "E3 suppression modes",
        "prereg_sha256": C.sha256_file(C.ROOT / PREREG),
        "mode_rule": "SUPPRESSION neu n_ticks_suppressed >= %d"
        % SUPPRESSION_MIN_TICKS,
        "runs": runs,
        "modes": modes,
        "H0_OUTLIER_consistent": all(mode == "NO_SUPPRESSION" for mode in modes),
        "H_FEEDBACK_consistent": feedback_ok,
        "H_BISTABLE_consistent_where_testable": bistable_ok,
        "note": "'consistent' = khong bi bac bo tren n=3, KHONG phai 'da chung minh'",
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(
        "modes=%s H0=%s H-FEEDBACK=%s H-BISTABLE=%s"
        % (
            modes,
            content["H0_OUTLIER_consistent"],
            feedback_ok,
            bistable_ok,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
