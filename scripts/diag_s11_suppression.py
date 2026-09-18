#!/usr/bin/env python3
"""Diagnose S11 on repeatable RO-ctl runs; this is not sealed evidence.

This tool must never be pointed at R-S.  Detailed output is permitted here
because RO-ctl carries no S2/S3 probability estimate.
"""
from __future__ import annotations

import json

from ml import campaign as C
from ml.blast_radius import entity_of
from ml.fsm import DetectorFSM, FSMParams
from ml.intervention_log import InMemoryInterventionLog, Intervention
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer


REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
RUNS = (
    "RO-ctl_admin_down-s1-s2-s4301-r1",
    "RO-ctl_admin_down-s1-s2-s4302-r2",
)


def build_log(meta):
    log = InMemoryInterventionLog()
    for item in meta["interventions"]:
        log.append(
            Intervention(
                id=item["id"],
                t_start=float(item["t_start"]),
                actor=item["actor"],
                action=item["action"],
                targets=item["targets"],
                blast_radius=frozenset(item["blast_radius"]),
                routing_sha256=item["routing_sha256"],
            )
        )
    return log


def main():
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(
        **json.loads((REPORT / "phase6r_amendment_2.json").read_text())["content"]["fsm"]["params"]
    )
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]

    for run_id in RUNS:
        snapshots = [
            json.loads(line)
            for line in (RAW / (run_id + ".jsonl")).read_text().splitlines()
            if line.strip()
        ]
        meta = json.loads((RAW / (run_id + ".meta.json")).read_text())
        log = build_log(meta)
        zone = frozenset().union(
            *(frozenset(item["blast_radius"]) for item in meta["interventions"])
        )
        scorer = FastOnlineScorer(
            model,
            expected_collector_version=version,
            conservation=conservation,
            conservation_mode="shadow",
        )
        fsm = DetectorFSM(params, log)

        print("\n" + "=" * 96)
        print(run_id)
        print(
            "%-5s %-7s %-12s %-6s %-29s %-6s %s"
            % ("tick", "t_rel", "status/cause", "alarm", "state(cause)", "nActv", "outside_zone")
        )
        print("-" * 96)
        for snapshot in snapshots:
            reading = scorer.observe(snapshot)
            transition = fsm.step(reading)
            t_rel = snapshot.get("t_rel", 0.0)
            if not 17 <= t_rel <= 52:
                continue
            active = log.active(reading.t_source, params.cooldown_s) if reading.t_source else []
            local = {entity_of(column) for column in reading.violating} - {None}
            outside = sorted(local - zone)
            print(
                "%-5s %-7.2f %-12s %-6s %-29s %-6d %s"
                % (
                    snapshot.get("tick"),
                    t_rel,
                    "%s/%s" % (reading.status, reading.cause or "-"),
                    "Y" if reading.suspect or reading.act else ".",
                    "%s(%s)" % (transition.state, transition.cause or "-"),
                    len(active),
                    (",".join(outside) or "-") if local else "(violating empty)",
                )
            )

        print("\nINTERPRETATION:")
        print("  H1: ticks while intervention is active are unknown/missing_data.")
        print("  H2: they are scored+alarming+active but outside_zone is non-empty.")
        print("  Otherwise investigate a third mechanism before amendment 7.")


if __name__ == "__main__":
    main()
