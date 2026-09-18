#!/usr/bin/env python3
"""Run sealed R-O1/R-O2 checks and the separate R-O3 controller check."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.fsm import DetectorFSM, FSMParams
from ml.intervention_log import InMemoryInterventionLog, Intervention
from ml.model import EnvelopeModel
from ml.replay_guard import R_O1_FIELDS, R_O2_FIELDS, _sealed, replay_gap, replay_restart
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer


REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
RS_RUNS = ("RS-soak2M-s4001-r1", "RS-soak2M-s4002-r2", "RS-soak2M-s4003-r3")
RO_CTL_RUNS = ("RO-ctl_admin_down-s1-s2-s4301-r1", "RO-ctl_admin_down-s1-s2-s4302-r2")


def _write(name, content):
    C.atomic_json(REPORT / name, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
    })


def _intervention_log(meta):
    log = InMemoryInterventionLog()
    for item in meta["interventions"]:
        log.append(Intervention(
            id=item["id"],
            t_start=float(item["t_start"]),
            actor=item["actor"],
            action=item["action"],
            targets=item["targets"],
            blast_radius=frozenset(item["blast_radius"]),
            routing_sha256=item["routing_sha256"],
        ))
    return log


def main():
    prereg = json.loads((REPORT / "phase6r_stability_prereg.json").read_text())
    for relative, expected in prereg["content"]["code_sha256"].items():
        if C.sha256_file(C.ROOT / relative) != expected:
            raise SystemExit("code doi sau dang ky: %s" % relative)
    protocol = prereg["content"]["measurement_protocol"]["R_O"]

    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**json.loads((REPORT / "phase6r_amendment_2.json").read_text())["content"]["fsm"]["params"])
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]

    def scorer_factory():
        return FastOnlineScorer(model, expected_collector_version=version, conservation=conservation, conservation_mode="shadow")

    def fsm_factory():
        return DetectorFSM(params, None)

    restart_acc = dict.fromkeys(R_O1_FIELDS[:-1], True)
    gap_acc = dict.fromkeys(R_O2_FIELDS[:-1], True)
    for run_id in RS_RUNS:
        snapshots = [json.loads(line) for line in (RAW / (run_id + ".jsonl")).read_text().splitlines() if line.strip()]
        restart = replay_restart(
            scorer_factory,
            fsm_factory,
            snapshots,
            protocol["restart_ticks"],
            n_act=params.n_act,
        )
        gap = replay_gap(
            scorer_factory,
            fsm_factory,
            snapshots,
            protocol["gap_ticks"],
            gap_len=protocol["gap_length_snapshots"],
        )
        for field in restart_acc:
            restart_acc[field] = restart_acc[field] and restart[field]
        for field in gap_acc:
            gap_acc[field] = gap_acc[field] and gap[field]

    restart_public = _sealed({**restart_acc, "passed": all(restart_acc.values())}, R_O1_FIELDS)
    gap_public = _sealed({**gap_acc, "passed": all(gap_acc.values())}, R_O2_FIELDS)
    _write("phase6r_replay_o1.json", restart_public)
    _write("phase6r_replay_o2.json", gap_public)
    print("R-O1/S9 aggregate:", restart_public)
    print("R-O2/S8 aggregate:", gap_public)

    controller_runs = {}
    for run_id in RO_CTL_RUNS:
        snapshots = [json.loads(line) for line in (RAW / (run_id + ".jsonl")).read_text().splitlines() if line.strip()]
        meta_path = RAW / (run_id + ".meta.json")
        meta = json.loads(meta_path.read_text())
        interventions = meta["interventions"]
        inject = next(item for item in interventions if item["action"].startswith("inject:"))
        revert = next(item for item in interventions if item["action"].startswith("revert:"))
        start = float(inject["t_start"])
        end = float(revert["t_start"]) + params.cooldown_s
        scorer = scorer_factory()
        fsm = DetectorFSM(params, _intervention_log(meta))
        act_entries = 0
        suppressed = 0
        for snapshot in snapshots:
            transition = fsm.step(scorer.observe(snapshot))
            if start <= transition.t_source <= end:
                act_entries += int(transition.state == "act" and transition.prev != "act")
                suppressed += int(transition.cause == "suppressed_intervention")
        controller_runs[run_id] = {
            "n_act_entries_in_suppression_window": act_entries,
            "window": [start, end],
            "blast_radius": inject["blast_radius"],
            "n_suppressed_ticks": suppressed,
            "suppression_cause_seen": "suppressed_intervention" if suppressed else None,
            "sidecar_sha256": C.sha256_file(meta_path),
            "passed": act_entries == 0 and suppressed > 0,
        }

    all_no_act = all(item["n_act_entries_in_suppression_window"] == 0 for item in controller_runs.values())
    mechanism_seen = all(item["n_suppressed_ticks"] > 0 for item in controller_runs.values())
    verdict = "PASS" if all_no_act and mechanism_seen else ("INCONCLUSIVE" if all_no_act else "FAIL")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip()
    controller = {
        "lesson": "6R.6",
        "slo": "S11",
        "runs": controller_runs,
        "verdict": verdict,
        "mechanism_evidence_seen_in_every_run": mechanism_seen,
        "mechanism_note": "uses sidecar.interventions recorded before apply; events are not suppression authority",
        "reads_labels": False,
        "git_head": head,
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write("phase6r_replay_o3.json", controller)
    print("R-O3/S11 verdict:", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
