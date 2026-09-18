#!/usr/bin/env python3
"""Dien tap nghiem thu 6R.7 tren Phase 5; khong cham R-set."""
from __future__ import annotations

import json
import sys

from ml import campaign as C
from ml.acceptance_guard import SnapshotReader, log_invocation, preflight
from ml.acceptance_metrics import incident, s1_s4, s2_s3, s10
from ml.acceptance_pass import FsmSpec, build_log, run_one
from ml.blast_radius import Routing, radius
from ml.fsm import DetectorFSM, FSMParams
from ml.model import EnvelopeModel
from ml.rcampaign_runtime import targets_for
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer

REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase5/raw"
CHANNELS = ("envelope_only", "combined")


def phase5_sidecar(meta: dict, routing) -> dict:
    """Them intervention revert cho sidecar Phase 5 bang cung luat runtime."""
    out = dict(meta, interventions=[])
    record = meta["record"]
    if record.get("fault"):
        revert = next(event for event in meta["events"] if event["kind"] == "revert")
        targets = targets_for(record)
        out["interventions"] = [
            {
                "id": record["run_id"] + ":revert",
                "t_start": revert["t_source"],
                "actor": "harness",
                "action": "revert:" + record["fault"],
                "targets": targets,
                "blast_radius": sorted(radius(routing, targets)),
                "routing_sha256": routing.sha256,
            }
        ]
    return out


def main() -> int:
    info = preflight("rehearsal")
    log_invocation(info)
    prereg = json.loads(
        (REPORT / "phase6r_acceptance_prereg.json").read_text(encoding="utf-8")
    )["content"]
    frozen = prereg["frozen_configuration"]
    for path, sha in frozen["code_sha256"].items():
        if C.sha256_file(C.ROOT / path) != sha:
            raise SystemExit("code lech prereg: " + path)

    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text(encoding="utf-8")
    )["collector_version"]
    params = FSMParams(**frozen["fsm_params"])
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    manifest = json.loads(
        (REPORT / "ml_dataset_manifest.json").read_text(encoding="utf-8")
    )["runs"]
    reader = SnapshotReader({key: value["sha256"] for key, value in manifest.items()})

    incidents = {channel: {} for channel in CHANNELS}
    background, s10_rows = [], {}
    for run_id in sorted(manifest):
        meta = phase5_sidecar(
            json.loads((RAW / (run_id + ".meta.json")).read_text(encoding="utf-8")),
            routing,
        )
        snapshots = reader.read_once(run_id, RAW / (run_id + ".jsonl"))
        log = build_log(meta, routing, zone="detour")
        specs = {
            channel: FsmSpec(channel, lambda log=log: DetectorFSM(params, log))
            for channel in CHANNELS
        }
        scorer = FastOnlineScorer(
            model,
            expected_collector_version=version,
            conservation=conservation,
            conservation_mode="shadow",
        )
        trace = run_one(
            run_id, snapshots, scorer, specs, frozen["conservation"]["R"]
        )
        if meta["record"].get("fault"):
            for channel in CHANNELS:
                incidents[channel][run_id] = incident(trace, meta, channel)
        else:
            background.append(trace)
            s10_rows[run_id] = {channel: s10(trace, channel) for channel in CHANNELS}

    slo = json.loads((REPORT / "phase6r_slo.json").read_text(encoding="utf-8"))[
        "content"
    ]
    anchor = slo["phase6_anchors"]["excess_eval_primary"]["delay_per_run_ticks"]
    for run_id, delay in anchor.items():
        got = incidents["envelope_only"][run_id]["first_tick"]
        expected = None if delay is None else 21 + delay
        if got != expected:
            raise SystemExit("KNOWN-ANSWER FAIL %s: %s != %s" % (run_id, got, expected))

    json.dump(
        {
            "reader_n_files_read": reader.n_files_read,
            "s1_s4": {channel: s1_s4(incidents[channel]) for channel in CHANNELS},
            "per_incident": incidents,
            "s2_s3_background": {channel: s2_s3(background, channel) for channel in CHANNELS},
            "s10_background": s10_rows,
            "known_answer": "phase6_anchors.excess_eval_primary.delay_per_run_ticks reproduced 8/8",
        },
        sys.stdout,
        indent=1,
        default=str,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
