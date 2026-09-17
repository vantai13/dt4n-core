#!/usr/bin/env python3
"""Replay all 18 runs and compare online output bit-for-bit with batch."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import conservation as K
from ml.dataset import load_split
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer, OnlineScorer
from ml.serve_fast import FastOnlineScorer

ART = C.ROOT / "models/envelope-1.0.0.json"
AMEND = C.ROOT / "results/report/phase6r_amendment_1.json"
MANIFEST = C.ROOT / "results/report/ml_dataset_split_manifest.json"
OUT = C.ROOT / "results/report/phase6r_equivalence.json"
FIELDS_INT = ("k", "k_indicator", "k_rate")
FIELDS_BOOL = ("judgeable", "envelope_suspect", "act", "cons_judgeable", "cons_alarm")
FIELDS_FLOAT = ("excess", "cons_r_max")


def load_parts():
    model = EnvelopeModel.load(ART)
    conservation = ConservationLayer.load(AMEND)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    contract = C.load_contract(C.ROOT / "results/report/experiment_matrix.json")
    return model, conservation, manifest, contract


def batch_reference(model, conservation, contract) -> pd.DataFrame:
    """Official Phase 6 path: load_split, score_batch, residuals."""
    split = load_split()
    warmup = int(contract["constants"]["warmup_ticks"])
    frames = []
    for part, features, run_ids in (
        ("train", split.X_train_envelope, contract["split"]["train"]),
        ("test", split.X_test_envelope, contract["split"]["test"]),
    ):
        per_run = len(features) // len(run_ids)
        keys = pd.DataFrame(
            [(run_id, tick) for run_id in sorted(run_ids) for tick in range(warmup, warmup + per_run)],
            columns=["run_id", "tick"],
        )
        if len(keys) != len(features):
            raise RuntimeError("%s: khong dung luoi run x tick (%d vs %d)" % (part, len(keys), len(features)))
        if part == "test" and not pd.DataFrame(split.meta["test_row_keys"]).equals(keys):
            raise RuntimeError("khoa test tu dung khac test_row_keys chinh thuc")
        decision = model.score_batch(features)
        residual = K.residuals(features, conservation.incidence, floor=conservation.floor)
        frames.append(
            keys.assign(
                judgeable=decision.judgeable,
                k=decision.k,
                k_indicator=decision.k_indicator,
                k_rate=decision.k_rate,
                excess=decision.excess,
                envelope_suspect=decision.suspect,
                act=decision.act,
                cons_judgeable=residual["judgeable"].to_numpy(),
                cons_r_max=np.where(residual["judgeable"], residual["r_max"], np.nan),
                cons_alarm=K.alarm(residual, conservation.threshold),
            )
        )
    return pd.concat(frames, ignore_index=True)


def online_replay(model, conservation, contract, expected_cv, scorer_class=OnlineScorer):
    """Replay each JSONL in file order with a new scorer for every run."""
    rows, latencies, statuses = [], [], {}
    warmup = int(contract["constants"]["warmup_ticks"])
    for record in contract["runs"]:
        run_id = record["run_id"]
        scorer = scorer_class(
            model,
            expected_collector_version=expected_cv,
            warmup_ticks=warmup,
            conservation=conservation,
            conservation_mode="shadow",
        )
        with C.run_paths(run_id, C.ROOT)["final"].open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                snapshot = json.loads(line)
                started = time.perf_counter()
                reading = scorer.observe(snapshot)
                latencies.append((time.perf_counter() - started) * 1000.0)
                statuses[reading.status] = statuses.get(reading.status, 0) + 1
                if reading.status == "warming_up":
                    continue
                if reading.status not in ("scored", "unknown"):
                    raise RuntimeError("%s tick %s: trang thai bat thuong %s" % (run_id, reading.tick, reading.status))
                rows.append(
                    {
                        "run_id": run_id,
                        "tick": reading.tick,
                        "status": reading.status,
                        "reason": reading.reason,
                        "judgeable": reading.judgeable,
                        "k": reading.k,
                        "k_indicator": reading.k_indicator,
                        "k_rate": reading.k_rate,
                        "excess": reading.excess,
                        "envelope_suspect": reading.envelope_suspect,
                        "act": reading.act,
                        "cons_judgeable": reading.cons_judgeable,
                        "cons_r_max": np.nan if reading.cons_r_max is None else reading.cons_r_max,
                        "cons_alarm": reading.cons_alarm,
                    }
                )
    latency = np.array(latencies)
    timing = {
        "n_calls": int(latency.size),
        "p50_ms": float(np.percentile(latency, 50)),
        "p99_ms": float(np.percentile(latency, 99)),
        "max_ms": float(latency.max()),
        "statuses": statuses,
    }
    return pd.DataFrame(rows), timing


def compare(batch: pd.DataFrame, online: pd.DataFrame) -> dict:
    merged = batch.merge(online, on=["run_id", "tick"], how="outer", suffixes=("_b", "_o"), indicator=True)
    if not merged["_merge"].eq("both").all():
        bad = merged.loc[~merged["_merge"].eq("both"), ["run_id", "tick", "_merge"]].head()
        raise RuntimeError("tap dong khong khop:\n%s" % bad)
    matches = pd.Series(True, index=merged.index)
    per_field = {}
    for field in FIELDS_INT + FIELDS_BOOL:
        batch_values = pd.to_numeric(merged[field + "_b"], errors="coerce").fillna(-1).astype("int64").to_numpy()
        online_values = pd.to_numeric(merged[field + "_o"], errors="coerce").fillna(-1).astype("int64").to_numpy()
        equal = batch_values == online_values
        per_field[field] = int(equal.sum())
        matches &= equal
    for field in FIELDS_FLOAT:
        batch_values = pd.to_numeric(merged[field + "_b"], errors="coerce").to_numpy(dtype=float)
        online_values = pd.to_numeric(merged[field + "_o"], errors="coerce").to_numpy(dtype=float)
        equal = (batch_values == online_values) | (np.isnan(batch_values) & np.isnan(online_values))
        per_field[field] = int(equal.sum())
        matches &= equal
    status_ok = merged["status"] == np.where(merged["judgeable_b"], "scored", "unknown")
    per_field["status_vs_judgeable"] = int(status_ok.sum())
    matches &= status_ok
    reason_ok = (merged["status"] != "unknown") | merged["reason"].astype(str).str.len().gt(0)
    per_field["reason_nonempty_when_unknown"] = int(reason_ok.sum())
    matches &= reason_ok
    merged["match"] = matches
    by_run = merged.groupby("run_id")["match"].agg(["sum", "size"])
    return {
        "n_rows": int(len(merged)),
        "n_match": int(matches.sum()),
        "per_field_match": per_field,
        "by_run": {
            run_id: {"match": int(row["sum"]), "rows": int(row["size"])}
            for run_id, row in by_run.iterrows()
        },
        "first_mismatches": merged.loc[~matches, ["run_id", "tick"]].head(10).to_dict("records"),
    }


def main() -> int:
    model, conservation, manifest, contract = load_parts()
    batch = batch_reference(model, conservation, contract)
    online, timing = online_replay(model, conservation, contract, manifest["collector_version"])
    result = compare(batch, online)
    fast, fast_timing = online_replay(
        model,
        conservation,
        contract,
        manifest["collector_version"],
        scorer_class=FastOnlineScorer,
    )
    fast_result = compare(batch, fast)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip()
    document = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": {
            "lesson": "6R.3",
            "artifact_sha256": model.content_sha256,
            "amendment_1_sha256": conservation.amendment_sha256,
            "conservation_mode": "shadow",
            "git_head": head,
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "machine": platform.machine(),
            "equivalence": result,
            "timing": timing,
            "fast_equivalence": fast_result,
            "fast_timing": fast_timing,
            "compute_budget_ms": 50.0,
            "reference_meets_budget": timing["p99_ms"] <= 50.0,
            "fast_meets_budget": fast_timing["p99_ms"] <= 50.0,
            "n_snapshots_replayed": timing["n_calls"],
            "labels_read": False,
        },
    }
    document["content_sha256"] = C.sha256_bytes(C.canonical_json(document["content"]).encode("utf-8"))
    C.atomic_json(OUT, document)
    print(
        "[6R.3] %d/%d khop; p99 %.2f ms; statuses %s"
        % (result["n_match"], result["n_rows"], timing["p99_ms"], timing["statuses"])
    )
    print(
        "[6R.3-fast] %d/%d khop; p99 %.2f ms; budget 50 ms: %s"
        % (
            fast_result["n_match"],
            fast_result["n_rows"],
            fast_timing["p99_ms"],
            "dat" if fast_timing["p99_ms"] <= 50.0 else "khong dat",
        )
    )
    if result["first_mismatches"]:
        print("[6R.3] lech dau tien:", result["first_mismatches"])
    return 0 if (
        result["n_match"] == result["n_rows"]
        and fast_result["n_match"] == fast_result["n_rows"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
