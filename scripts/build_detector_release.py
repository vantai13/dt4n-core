#!/usr/bin/env python3
"""Sinh detector-release-1.0.0 theo amendment 8; khong fit gi."""
from __future__ import annotations

import json
import sys

from ml import campaign as C
from ml.model import EnvelopeModel
from ml.release import SCHEMA

REPORT = C.ROOT / "results/report"
OUT = C.ROOT / "models/detector-release-1.0.0.json"


def sealed(name):
    doc = json.loads((REPORT / name).read_text(encoding="utf-8"))
    if C.sha256_bytes(C.canonical_json(doc["content"]).encode()) != doc["content_sha256"]:
        raise RuntimeError("receipt drift: " + name)
    return doc


def main():
    if OUT.exists():
        print("[REL] da ton tai; tang version thay vi ghi de")
        return 1
    amendment8 = sealed("phase6r_amendment_8.json")
    amendment1 = sealed("phase6r_amendment_1.json")
    prereg = sealed("phase6r_acceptance_prereg.json")["content"]
    s4 = sealed("phase6r_verdicts.json")["content"]["slo"]["S4"]
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    collector_version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text(encoding="utf-8")
    )["collector_version"]
    content = {
        "schema": SCHEMA,
        "version": "detector-release-1.0.0",
        "components": {
            "envelope": {
                "name": model.version,
                "path": "models/envelope-1.0.0.json",
                "content_sha256": model.content_sha256,
            },
            "conservation": {
                "name": "conservation-1.0.0",
                "path": "results/report/phase6r_amendment_1.json",
                "content_sha256": amendment1["content_sha256"],
            },
        },
        "conservation_mode": "active",
        "collector_version": collector_version,
        "warmup_ticks": 1,
        "fsm_params": prereg["frozen_configuration"]["fsm_params"],
        "scorer": "ml.serve_fast.FastOnlineScorer",
        "suppression_radius_rule": prereg["frozen_configuration"]["suppression_radius"]["rule"],
        "routing_table": {
            "path": "ditto/routing_table.json",
            "sha256": C.sha256_file(C.ROOT / "ditto/routing_table.json"),
        },
        "decided_by": {
            "amendment_8_content_sha256": amendment8["content_sha256"]
        },
        "operating_scope": amendment8["content"]["operating_scope"]["accepted_load"],
        "channels": {
            "envelope": {
                "drives": ["suspect", "act"],
                "ttd_p95_ms_R_D": round(s4["value_ms"]),
            },
            "conservation": {
                "drives": ["suspect"],
                "ttd_p95_ms_R_D": round(s4["combined_value_ms"]),
                "note": "kenh cham; khong dat S4; khong bao gio dan toi act",
            },
        },
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        },
    )
    print("[REL] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
