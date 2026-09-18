#!/usr/bin/env python3
"""Second S11 measurement under amendment 7; never overwrites v1 evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.blast_radius import Routing, radius_with_detour
from ml.fsm import DetectorFSM, FSMParams
from ml.intervention_log import InMemoryInterventionLog, Intervention
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer


REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
OUT = REPORT / "phase6r_replay_o3_v2.json"
RUNS = (
    "RO-ctl_admin_down-s1-s2-s4301-r1",
    "RO-ctl_admin_down-s1-s2-s4302-r2",
)


def load_sealed(name):
    document = json.loads((REPORT / name).read_text())
    digest = C.sha256_bytes(C.canonical_json(document["content"]).encode())
    if digest != document["content_sha256"]:
        raise SystemExit("receipt drift: " + name)
    return document


def amended_log(meta, routing):
    log = InMemoryInterventionLog()
    for item in meta["interventions"]:
        if item["routing_sha256"] != routing.sha256:
            raise SystemExit("routing SHA differs from sealed sidecar")
        blast_radius = (
            radius_with_detour(routing, item["targets"])
            if item["action"].endswith(":admin_down")
            else frozenset(item["blast_radius"])
        )
        log.append(
            Intervention(
                id=item["id"],
                t_start=float(item["t_start"]),
                actor=item["actor"],
                action=item["action"],
                targets=item["targets"],
                blast_radius=blast_radius,
                routing_sha256=item["routing_sha256"],
            )
        )
    return log


def main():
    if OUT.exists():
        raise SystemExit("phase6r_replay_o3_v2.json already exists; refusing overwrite")
    amendment = load_sealed("phase6r_amendment_7.json")
    failed = load_sealed("phase6r_replay_o3.json")
    trigger = amendment["content"]["trigger"]
    if trigger["failed_receipt_file_sha256"] != C.sha256_file(REPORT / "phase6r_replay_o3.json"):
        raise SystemExit("original failure no longer matches amendment 7")

    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**load_sealed("phase6r_amendment_2.json")["content"]["fsm"]["params"])
    version = json.loads((REPORT / "ml_dataset_split_manifest.json").read_text())["collector_version"]
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")

    results = {}
    for run_id in RUNS:
        snapshots = [
            json.loads(line)
            for line in (RAW / (run_id + ".jsonl")).read_text().splitlines()
            if line.strip()
        ]
        meta_path = RAW / (run_id + ".meta.json")
        meta = json.loads(meta_path.read_text())
        inject = next(item for item in meta["interventions"] if item["action"].startswith("inject:"))
        revert = next(item for item in meta["interventions"] if item["action"].startswith("revert:"))
        start = float(inject["t_start"])
        end = float(revert["t_start"]) + params.cooldown_s
        scorer = FastOnlineScorer(
            model,
            expected_collector_version=version,
            conservation=conservation,
            conservation_mode="shadow",
        )
        log = amended_log(meta, routing)
        fsm = DetectorFSM(params, log)
        act_entries = suppressed = 0
        suppression_ids = set()
        for snapshot in snapshots:
            transition = fsm.step(scorer.observe(snapshot))
            if start <= transition.t_source <= end:
                act_entries += int(transition.state == "act" and transition.prev != "act")
                if transition.cause == "suppressed_intervention":
                    suppressed += 1
                    suppression_ids.update(transition.suppressed_by)
        amended_radius = sorted(radius_with_detour(routing, inject["targets"]))
        passed = act_entries == 0 and suppressed > 0
        results[run_id] = {
            "n_act_entries_in_suppression_window": act_entries,
            "window": [start, end],
            "blast_radius": amended_radius,
            "radius_added_by_amendment_7": sorted(set(amended_radius) - set(inject["blast_radius"])),
            "n_suppressed_ticks": suppressed,
            "suppression_cause_seen": "suppressed_intervention" if suppressed else None,
            "suppressed_by": sorted(suppression_ids),
            "sidecar_sha256": C.sha256_file(meta_path),
            "passed": passed,
        }

    verdict = "PASS" if all(item["passed"] for item in results.values()) else "FAIL"
    content = {
        "lesson": "6R.6-S11-repair",
        "slo": "S11",
        "measurement_number": 2,
        "amendment_7_content_sha256": amendment["content_sha256"],
        "supersedes_for_S11_only": {
            "file": "phase6r_replay_o3.json",
            "file_sha256": C.sha256_file(REPORT / "phase6r_replay_o3.json"),
            "content_sha256": failed["content_sha256"],
            "original_verdict": failed["content"]["verdict"],
        },
        "runs": results,
        "verdict": verdict,
        "pass_rule": "every run has n_act_entries == 0 AND n_suppressed_ticks > 0",
        "thresholds_changed": False,
        "extra_runs_collected": False,
        "reads_labels": False,
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True).stdout.strip(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(OUT, {"content": content, "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    print("S11 v2:", verdict)
    for run_id, item in results.items():
        print(run_id, "act_entries=%d suppressed=%d" % (item["n_act_entries_in_suppression_window"], item["n_suppressed_ticks"]))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
