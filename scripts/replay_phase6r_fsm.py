#!/usr/bin/env python3
"""Replay all runs through FastOnlineScorer and the pre-registered FSM."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.blast_radius import Routing, radius
from ml.fsm import DetectorFSM, FSMParams
from ml.intervention_log import InMemoryInterventionLog, Intervention
from ml.labels import labels_from_events
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer

REPORT = C.ROOT / "results/report"
AMEND2 = REPORT / "phase6r_amendment_2.json"
OUT = REPORT / "phase6r_fsm.json"
ALARM = {"suspect_level": ("suspect", "act"), "act_level": ("act",)}


def load_amendment():
    if not AMEND2.exists():
        raise SystemExit(
            "chua dang ky phase6r_amendment_2.json -> khong duoc phat lai FSM"
        )
    document = json.loads(AMEND2.read_text(encoding="utf-8"))
    digest = C.sha256_bytes(
        C.canonical_json(document["content"]).encode("utf-8")
    )
    if document["content_sha256"] != digest:
        raise SystemExit("amendment 2 bi sua")
    for relative, expected in document["content"]["code_sha256"].items():
        if C.sha256_file(C.ROOT / relative) != expected:
            raise SystemExit("code da doi sau dang ky: %s" % relative)
    return document


def revert_log(meta, record, routing, targets_fn):
    log = InMemoryInterventionLog()
    for event in meta["events"]:
        if event["kind"] != "revert":
            continue
        targets = targets_fn(record)
        log.append(
            Intervention(
                id="%s:revert" % record["run_id"],
                t_start=float(event["t_source"]),
                actor="harness",
                action="revert:%s" % record["fault"],
                targets=targets,
                blast_radius=radius(routing, targets),
                routing_sha256=routing.sha256,
            )
        )
    return log


def run_fsm(snapshots, model, conservation, collector_version, params, log):
    scorer = FastOnlineScorer(
        model,
        expected_collector_version=collector_version,
        conservation=conservation,
        conservation_mode="shadow",
    )
    fsm = DetectorFSM(params, log)
    return [fsm.step(scorer.observe(snapshot)) for snapshot in snapshots]


def events(ticks):
    ticks = sorted(ticks)
    return 0 if not ticks else 1 + sum(
        right - left > 1 for left, right in zip(ticks, ticks[1:])
    )


def metrics_run(transitions, labels, record, cooldown_ticks):
    output = {
        "unknown_by_cause": {},
        "n_suppressed": 0,
        "n_suppressed_on_fault_tick": 0,
    }
    for transition in transitions:
        if transition.state == "unknown":
            output["unknown_by_cause"][transition.cause] = (
                output["unknown_by_cause"].get(transition.cause, 0) + 1
            )
        if transition.cause == "suppressed_intervention":
            output["n_suppressed"] += 1
            output["n_suppressed_on_fault_tick"] += int(
                labels[transition.tick] == 1
            )
    for level, group in ALARM.items():
        false_positive = [
            transition.tick
            for transition in transitions
            if transition.tick >= 1
            and labels[transition.tick] == 0
            and transition.state in group
        ]
        output[level] = {
            "fp_ticks": len(false_positive),
            "fp_events": events(false_positive),
            "fp_tick_list": false_positive,
        }
        if record.get("fault"):
            window = [
                transition
                for transition in transitions
                if labels[transition.tick] == 1
            ]
            onset = min(transition.tick for transition in window)
            hits = [
                transition.tick
                for transition in window
                if transition.state in group
            ]
            output[level]["delay"] = None if not hits else min(hits) - onset
    if record.get("fault"):
        low = min(tick for tick, value in enumerate(labels) if value == 1)
        high = max(tick for tick, value in enumerate(labels) if value == 1) + cooldown_ticks
        sequence = [
            transition.state
            for transition in transitions
            if low <= transition.tick <= high
            and transition.state not in ("unknown", "warming_up")
        ]
        sequence = [
            state
            for index, state in enumerate(sequence)
            if index == 0 or state != sequence[index - 1]
        ]
        output["s7_violations"] = sum(
            1
            for left, middle, right in zip(
                sequence, sequence[1:], sequence[2:]
            )
            if left == right and left in ("suspect", "act")
        )
        output["state_sequence_window"] = sequence
    return output


def check(predictions, results, zones):
    runs = results["runs"]
    faults = [run_id for run_id in runs if runs[run_id]["fault"]]

    def total(mode, level, key, subset=None):
        return sum(
            runs[run_id][mode][level][key] for run_id in (subset or runs)
        )

    checks = {}
    checks["P1_no_log_suspect_fp_events"] = (
        total("no_log", "suspect_level", "fp_events")
        == predictions["P1_no_log_suspect_fp_events"]["value"]
    )
    low, high = predictions["P1_no_log_suspect_fp_ticks"]["value"]
    checks["P1_no_log_suspect_fp_ticks"] = low <= total(
        "no_log", "suspect_level", "fp_ticks"
    ) <= high
    checks["P1_no_log_act_fp_events"] = total(
        "no_log", "act_level", "fp_events"
    ) <= predictions["P1_no_log_act_fp_events"]["value"]
    full = predictions["P2_log_fp_events_full_radius_runs"]["runs"]
    checks["P2_log_fp_events_full_radius_runs"] = (
        total("with_log", "suspect_level", "fp_events", full)
        + total("with_log", "act_level", "fp_events", full)
    ) == 0
    checks["P3_suspect_delay"] = all(
        runs[run_id]["with_log"]["suspect_level"]["delay"]
        == predictions["P3_suspect_delay_per_run_equals_phase6_excess"][run_id]
        and runs[run_id]["no_log"]["suspect_level"]["delay"]
        == predictions["P3_suspect_delay_per_run_equals_phase6_excess"][run_id]
        for run_id in faults
    )
    checks["P3_act_delay"] = all(
        runs[run_id]["with_log"]["act_level"]["delay"]
        == predictions["P3_act_delay_per_run"][run_id]
        for run_id in faults
    )
    checks["P4_s7_violations"] = all(
        runs[run_id][mode]["s7_violations"] == 0
        for run_id in faults
        for mode in ("no_log", "with_log")
    )
    checks["P5_control_and_train_fp_events"] = sum(
        runs[run_id][mode][level]["fp_events"]
        for run_id in runs
        if not runs[run_id]["fault"]
        for mode in ("no_log", "with_log")
        for level in ALARM
    ) == 0
    return checks


def main() -> int:
    document = load_amendment()
    amendment = document["content"]
    from scripts.build_phase6r_amendment2 import revert_targets

    params = FSMParams(**amendment["fsm"]["params"])
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    contract = C.load_contract(REPORT / "experiment_matrix.json")
    collector_version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text()
    )["collector_version"]
    cooldown_ticks = int(params.cooldown_s)
    results = {"runs": {}}
    for record in contract["runs"]:
        paths = C.run_paths(record["run_id"], C.ROOT)
        snapshots = [
            json.loads(line)
            for line in paths["final"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
        labels = labels_from_events(len(snapshots), meta["events"])
        entry = {"fault": record.get("fault")}
        for mode in ("no_log", "with_log"):
            log = (
                revert_log(meta, record, routing, revert_targets)
                if mode == "with_log" and record.get("fault")
                else None
            )
            entry[mode] = metrics_run(
                run_fsm(
                    snapshots,
                    model,
                    conservation,
                    collector_version,
                    params,
                    log,
                ),
                labels,
                record,
                cooldown_ticks,
            )
        results["runs"][record["run_id"]] = entry
    checks = check(
        amendment["predictions"],
        results,
        amendment["suppression"]["replay_radius_by_run"],
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    content = {
        "lesson": "6R.4",
        "amendment_2_sha256": document["content_sha256"],
        "git_head": head,
        "python": sys.version.split()[0],
        "results": results,
        "prediction_checks": checks,
        "totals": {
            mode: {
                level: {
                    "fp_events": sum(
                        results["runs"][run_id][mode][level]["fp_events"]
                        for run_id in results["runs"]
                    ),
                    "fp_ticks": sum(
                        results["runs"][run_id][mode][level]["fp_ticks"]
                        for run_id in results["runs"]
                    ),
                }
                for level in ALARM
            }
            for mode in ("no_log", "with_log")
        },
    }
    output = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": content,
        "content_sha256": C.sha256_bytes(
            C.canonical_json(content).encode("utf-8")
        ),
    }
    C.atomic_json(OUT, output)
    print(json.dumps(content["totals"]))
    for name, passed in checks.items():
        print("%-40s %s" % (name, "DAT" if passed else "KHONG DAT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
