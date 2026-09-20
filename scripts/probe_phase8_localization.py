#!/usr/bin/env python3
"""Probe 8.1-B - ma tran nham lan cua luat dinh vi, va cac so co owner.

Chay:  .venv/bin/python scripts/probe_phase8_localization.py
Ra:    results/report/phase8_localization_probe.json

Noi dung:
  1. Ma tran nham lan cua LUAT v2 (latch) tren toan bo du lieu da mo -> KN1/2/3.
  2. So sanh voi LUAT Delta-gap (de ghi vao prereg vi sao khong chon no),
     Delta tinh CHI tu 8 run train, qua tuong lua _assert_train_path.
  3. Muc gioi han L: tran tai hop le tren train, kem owner.
  4. Bang chung recovery burst: vi sao phai LATCH.
  5. Kich thuoc vung uc che (blast radius) cua chinh can thiep du dinh.

Khong co nguong tu do nao duoc chon sau khi nhin du lieu test: moi con so lay
tu train deu di qua tuong lua train-only cua ml/operating_range.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.localize import localize  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml import operating_range as O  # noqa: E402
from ml.blast_radius import Routing, radius  # noqa: E402
from scripts import phase8_replay as R  # noqa: E402

OUT = C.ROOT / "results/report/phase8_localization_probe.json"
MBPS = 8.0 / 1e6          # txRate cua collector la Byte/s
BURST_RUN = "F-flood-h1_to_srv1-s3005-r1"
PLANNED_TARGET_LINK = "h1-s1"


def expected_target(record) -> str | None:
    """Su that nen: chi flood moi co thu pham la mot client."""
    if (record.get("fault") or "none") != "flood":
        return None
    target = record.get("fault_target") or ""
    return target.split("->", 1)[0].strip() or None


def client_tx(snapshot, roles):
    """[(txMbps, ten)] cua client co rateValid; rong neu tick khong doc duoc."""
    values = []
    for name, role in roles.items():
        if role != "client":
            continue
        traffic = (
            (snapshot["things"]["host-" + name].get("features") or {}).get("traffic") or {}
        )
        if traffic.get("rateValid") is not True:
            continue
        values.append((float(traffic["txRate"]) * MBPS, name))
    values.sort(reverse=True)
    return values


def train_paths():
    return [C.ROOT / O.TRAIN_DIR / (run_id + ".jsonl") for run_id in O.TRAIN_RUN_IDS]


def train_only(paths):
    """Tuong lua: muon con so nao tu train thi phai qua dung 8 run train."""
    run_ids = [O._assert_train_path(path) for path in paths]
    if sorted(run_ids) != sorted(O.TRAIN_RUN_IDS):
        raise O.FirewallError("phai dung du va dung 8 run train, khong chon loc")
    return run_ids


def train_numbers(paths):
    """Delta (max gap top-nhi) va L (tran tai hop le), ca hai deu kem owner."""
    run_ids = train_only(paths)
    delta, delta_owner = -1.0, None
    ceiling, ceiling_owner = -1.0, None
    per_run = {}
    for run_id, path in zip(run_ids, paths):
        run_gap, run_max = None, None
        for index, snapshot in enumerate(C.read_snapshots(path)):
            roles = {
                key[len("host-"):]: (thing.get("attributes") or {}).get("role")
                for key, thing in (snapshot.get("things") or {}).items()
                if key.startswith("host-")
            }
            values = client_tx(snapshot, roles)
            if not values:
                continue
            top = values[0]
            run_max = top[0] if run_max is None else max(run_max, top[0])
            if top[0] > ceiling:
                ceiling = top[0]
                ceiling_owner = {"run_id": run_id, "tick": index, "host": top[1]}
            if len(values) >= 2:
                gap = top[0] - values[1][0]
                run_gap = gap if run_gap is None else max(run_gap, gap)
                if gap > delta:
                    delta = gap
                    delta_owner = {
                        "run_id": run_id,
                        "tick": index,
                        "host": top[1],
                        "top_mbps": round(top[0], 6),
                        "second_mbps": round(values[1][0], 6),
                    }
        per_run[run_id] = {
            "max_gap_mbps": None if run_gap is None else round(run_gap, 6),
            "max_client_tx_mbps": None if run_max is None else round(run_max, 6),
        }
    return {
        "delta_mbps_exact": delta,
        "delta_mbps": round(delta, 6),
        "delta_owner": delta_owner,
        "limit_ceiling_mbps": round(ceiling, 6),
        "limit_owner": ceiling_owner,
        "per_run": per_run,
    }


def delta_without(paths, excluded):
    """Delta neu ai do 'lam sach' train bang cach bo mot run - de chung minh la SAI."""
    kept = [p for p in paths if Path(p).name[: -len(".jsonl")] != excluded]
    best = -1.0
    for path in kept:
        for snapshot in C.read_snapshots(path):
            roles = {
                key[len("host-"):]: (thing.get("attributes") or {}).get("role")
                for key, thing in (snapshot.get("things") or {}).items()
                if key.startswith("host-")
            }
            values = client_tx(snapshot, roles)
            if len(values) >= 2:
                best = max(best, values[0][0] - values[1][0])
    return best


def gap_rule(values, delta):
    """Luat cu trong PHASE_8.md: top-nhi > Delta thi chi mat top."""
    if len(values) < 2:
        return values[0][1] if values else None
    return values[0][1] if (values[0][0] - values[1][0]) > delta else None


def main() -> int:
    release = R.load_release()
    threshold = R.guard_threshold()
    numbers = train_numbers(train_paths())
    delta = numbers["delta_mbps_exact"]
    delta_dropped = delta_without(train_paths(), "N-vary-s1008-r2")

    runs, burst = [], []
    matrix = {"correct_latch": 0, "wrong_latch": 0, "missed": 0, "correct_silence": 0}
    for path, record in R.iter_runs():
        ticks = R.replay(release, threshold, path)
        truth = expected_target(record)
        latched, latched_reason, first_tick = None, None, None
        per_tick_targets, gap_fires, gap_targets = [], 0, set()
        gap_fires_dropped, gap_targets_dropped = 0, set()
        for row in ticks:
            values = client_tx(row["snapshot"], row["roles"])
            if row["state"] == "act":
                loc = localize(row["affected"], row["roles"])
                if loc.target:
                    per_tick_targets.append(loc.target)
                if latched is None and first_tick is None:
                    first_tick, latched, latched_reason = row["tick"], loc.target, loc.reason
            # Luat Delta-gap khong co cong `act`: do chinh la diem yeu cua no.
            hit = gap_rule(values, delta)
            if hit:
                gap_fires += 1
                gap_targets.add(hit)
            hit_dropped = gap_rule(values, delta_dropped)
            if hit_dropped:
                gap_fires_dropped += 1
                gap_targets_dropped.add(hit_dropped)
            if record["run_id"] == BURST_RUN and 18 <= row["tick"] <= 50:
                burst.append(
                    {
                        "tick": row["tick"],
                        "state": row["state"],
                        "tx_mbps": {n: round(v, 3) for v, n in values},
                        "affected": row["affected"],
                        "target_if_per_tick": localize(row["affected"], row["roles"]).target
                        if row["state"] == "act"
                        else None,
                    }
                )

        if truth is None:
            key = "correct_silence" if latched is None else "wrong_latch"
        elif latched == truth:
            key = "correct_latch"
        elif latched is None:
            key = "missed"
        else:
            key = "wrong_latch"
        matrix[key] += 1
        runs.append(
            {
                "run_id": record["run_id"],
                "fault": record.get("fault") or "none",
                "split": record.get("split"),
                "true_culprit": truth,
                "latched_target": latched,
                "latched_reason": latched_reason,
                "first_act_tick": first_tick,
                "verdict": key,
                "per_tick_targets": sorted(set(per_tick_targets)),
                "gap_rule_n_fire": gap_fires,
                "gap_rule_targets": sorted(gap_targets),
                "gap_rule_n_fire_if_s1008_dropped": gap_fires_dropped,
                "gap_rule_targets_if_s1008_dropped": sorted(gap_targets_dropped),
            }
        )

    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    zone = sorted(radius(routing, {"links": [PLANNED_TARGET_LINK], "flows": []}))
    entities = sorted(
        {c.split(".", 1)[0] for c in release.model.columns}
        - {"agg"}
    )

    kn = "KN1" if (matrix["wrong_latch"] == 0 and matrix["missed"] == 0) else (
        "KN2" if matrix["correct_latch"] else "KN3"
    )
    out = {
        "schema": "DT4N-PHASE8-LOCALIZATION-PROBE-1",
        "release": release.version,
        "release_sha256": release.sha256,
        "guard_threshold_mbps": threshold,
        "confusion_matrix": matrix,
        "outcome": kn,
        "train_numbers": numbers,
        "delta_if_s1008_dropped": round(delta_dropped, 6),
        "gap_rule_false_fire_runs_if_s1008_dropped": None,
        "gap_rule_false_fire_runs": sorted(
            r["run_id"] for r in runs if r["true_culprit"] is None and r["gap_rule_n_fire"]
        ),
        "gap_rule_wrong_target_runs": sorted(
            r["run_id"]
            for r in runs
            if r["gap_rule_targets"] and r["true_culprit"] not in r["gap_rule_targets"]
        ),
        "suppression_zone": {
            "intervention_link": PLANNED_TARGET_LINK,
            "n_entities": len(zone),
            "n_model_entities": len(entities),
            "entities": zone,
            "outside_zone": sorted(set(entities) - set(zone)),
        },
        "recovery_burst_evidence": {"run_id": BURST_RUN, "ticks": burst},
        "runs": runs,
    }
    C.atomic_json(OUT, out)
    print("wrote", OUT)
    print("confusion:", matrix, "->", kn)
    out["gap_rule_false_fire_runs_if_s1008_dropped"] = sorted(
        r["run_id"] for r in runs
        if r["true_culprit"] is None and r["gap_rule_n_fire_if_s1008_dropped"]
    )
    C.atomic_json(OUT, out)
    print("Delta =", delta, "owner =", numbers["delta_owner"])
    print("Delta neu bo N-vary-s1008-r2 =", delta_dropped)
    print("L ceiling =", numbers["limit_ceiling_mbps"], "owner =", numbers["limit_owner"])
    print("gap-rule (Delta bo s1008) ban nham o:",
          out["gap_rule_false_fire_runs_if_s1008_dropped"])
    print("gap-rule ban nham o run binh thuong:", out["gap_rule_false_fire_runs"])
    print("gap-rule chi nham muc tieu o:", out["gap_rule_wrong_target_runs"])
    print("vung uc che:", out["suppression_zone"]["n_entities"], "/",
          out["suppression_zone"]["n_model_entities"],
          "ngoai vung:", out["suppression_zone"]["outside_zone"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
