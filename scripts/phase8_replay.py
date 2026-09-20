#!/usr/bin/env python3
"""Phat lai release detector DA DONG BANG tren mot run offline (Phase 8.1).

Dung chung cho hai probe cua Lesson 8.1. Khong train lai gi, khong nguong tu do:
moi quyet dinh deu di qua dung duong ma runtime Phase 7 di:

    scorer.observe -> fsm.step -> OperatingRangeGuard.update -> build_document

nen `evidence.affected` va `decision.state` o day bang bit voi cai twin cong bo.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import detector_contract as D  # noqa: E402
from controller.localize import roles_from_snapshot  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml import operating_range as O  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402

RELEASE_PATH = "models/detector-release-1.0.0.json"
PREREG7_PATH = "results/report/phase7_prereg.json"
DATA_DIRS = ("data/phase5/raw", "data/phase6r/raw")
ISO = "1970-01-01T00:00:00Z"   # hang so: probe khong duoc phu thuoc dong ho


def load_release() -> DetectorRelease:
    return DetectorRelease.load(C.ROOT / RELEASE_PATH)


def guard_threshold() -> float:
    """Nguong vung van hanh, lay tu prereg Phase 7 DA NIEM PHONG (khong tinh lai)."""
    document = json.loads((C.ROOT / PREREG7_PATH).read_text(encoding="utf-8"))
    return O.load_sealed_threshold(document)


def iter_runs(dirs=DATA_DIRS):
    """Sinh (path, record) cho moi run co meta, theo thu tu on dinh."""
    for directory in dirs:
        for path in sorted(glob.glob(os.path.join(str(C.ROOT), directory, "*.jsonl"))):
            meta_path = path[: -len(".jsonl")] + ".meta.json"
            if not os.path.exists(meta_path):
                continue
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
            yield path, meta["record"]


def replay(release, threshold, path):
    """Tra list tick: (tick, published_state, cause, affected, roles, snapshot)."""
    scorer, fsm = release.build(None)
    guard = O.OperatingRangeGuard(threshold)
    rows = []
    for snapshot in C.read_snapshots(path):
        reading = scorer.observe(snapshot)
        transition = fsm.step(reading)
        guard_active = guard.update(snapshot)
        document = D.build_document(
            release,
            transition,
            reading,
            boot_id="probe",
            seq=len(rows),
            heartbeat_at=ISO,
            detected_at=ISO,
            dropped=0,
            guard_active=guard_active,
        )
        properties = document["features"]["decision"]["properties"]
        evidence = document["features"]["evidence"]["properties"]
        rows.append(
            {
                "tick": transition.tick,
                "state": properties["state"],        # state DA CONG BO (sau guard)
                "fsm_state": transition.state,       # state tho cua FSM, de doi chieu
                "cause": properties.get("cause") or "",
                "guard_active": bool(guard_active),
                "affected": list(evidence["affected"]),
                "act_rule": bool(evidence["actRule"]),
                "roles": roles_from_snapshot(snapshot),
                "snapshot": snapshot,
            }
        )
    return rows


def sha256_of(path) -> str:
    return C.sha256_bytes(Path(path).read_bytes())
