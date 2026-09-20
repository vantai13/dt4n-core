#!/usr/bin/env python3
"""Probe 8.1-A - loai su co nao len duoc `act`, va ai la ung vien tai tick act dau.

Chay:  .venv/bin/python scripts/probe_phase8_actionability.py
Ra:    results/report/phase8_actionability.json

KHONG co nguong tu do. KHONG train lai gi. Chi phat lai release da dong bang
qua dung duong runtime (co ca guard vung van hanh cua Phase 7).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.localize import localize  # noqa: E402
from ml import campaign as C  # noqa: E402
from scripts import phase8_replay as R  # noqa: E402

OUT = C.ROOT / "results/report/phase8_actionability.json"


def episodes_of(rows):
    """Nhom cac tick act lien tiep (theo state DA CONG BO) thanh episode."""
    out, previous = [], None
    for row in rows:
        if row["state"] != "act":
            previous = None
            continue
        record = dict(row)
        loc = localize(row["affected"], row["roles"])
        record.update(
            target=loc.target, reason=loc.reason, candidates=list(loc.candidates)
        )
        record.pop("snapshot", None)
        record.pop("roles", None)
        if previous is None or row["tick"] != previous + 1:
            out.append([record])
        else:
            out[-1].append(record)
        previous = row["tick"]
    return out


def main() -> int:
    release = R.load_release()
    threshold = R.guard_threshold()
    rows = []
    for path, record in R.iter_runs():
        try:
            ticks = R.replay(release, threshold, path)
        except Exception as exc:  # con tro LFS, schema lech...
            rows.append({"run_id": record["run_id"], "error": repr(exc)})
            continue
        episodes = episodes_of(ticks)
        # Quyet dinh cua controller = quyet dinh tai tick act DAU cua episode DAU
        # (LATCH). Xem muc 5.3 cua Lesson 8.1: khong danh gia lai moi tick.
        first = episodes[0][0] if episodes else None
        rows.append(
            {
                "run_id": record["run_id"],
                "fault": record.get("fault") or "none",
                "fault_target": record.get("fault_target"),
                "split": record.get("split"),
                "n_ticks": len(ticks),
                "n_act_ticks": sum(len(e) for e in episodes),
                "n_episodes": len(episodes),
                "n_guard_active_ticks": sum(1 for t in ticks if t["guard_active"]),
                "n_fsm_act_ticks": sum(1 for t in ticks if t["fsm_state"] == "act"),
                "first_act_tick": first["tick"] if first else None,
                "latched_target": first["target"] if first else None,
                "latched_reason": first["reason"] if first else None,
                "latched_candidates": first["candidates"] if first else [],
                "candidates_seen_in_run": sorted(
                    {c for e in episodes for r in e for c in r["candidates"]}
                ),
                "targets_if_evaluated_every_tick": sorted(
                    {r["target"] for e in episodes for r in e if r["target"]}
                ),
                "n_act_ticks_act_rule_false": sum(
                    1 for e in episodes for r in e if not r["act_rule"]
                ),
                "sha256": R.sha256_of(path),
            }
        )

    summary = {
        "n_runs": len([r for r in rows if "error" not in r]),
        "n_runs_error": len([r for r in rows if "error" in r]),
        "n_runs_with_act": len([r for r in rows if r.get("n_act_ticks")]),
        "n_runs_latched": len([r for r in rows if r.get("latched_target")]),
        "latched_by_fault": {},
        "latch_vs_per_tick_differs": sorted(
            r["run_id"]
            for r in rows
            if r.get("targets_if_evaluated_every_tick")
            and set(r["targets_if_evaluated_every_tick"])
            != ({r["latched_target"]} if r.get("latched_target") else set())
        ),
    }
    for row in rows:
        if "error" in row:
            continue
        bucket = summary["latched_by_fault"].setdefault(
            row["fault"], {"n_runs": 0, "targets": []}
        )
        bucket["n_runs"] += 1
        bucket["targets"].append(row["latched_target"])

    out = {
        "schema": "DT4N-PHASE8-ACTIONABILITY-1",
        "release": release.version,
        "release_sha256": release.sha256,
        "guard_threshold_mbps": threshold,
        "localization_rule": "v2 single-client, latch at episode onset",
        "summary": summary,
        "runs": rows,
    }
    C.atomic_json(OUT, out)
    print("wrote", OUT, "-", len(rows), "runs")
    print("runs with act:", summary["n_runs_with_act"], "| latched:", summary["n_runs_latched"])
    for fault, bucket in sorted(summary["latched_by_fault"].items()):
        print("  %-12s n=%2d targets=%s" % (fault, bucket["n_runs"], bucket["targets"]))
    print("latch differs from per-tick on:", summary["latch_vs_per_tick_differs"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
