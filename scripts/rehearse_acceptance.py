#!/usr/bin/env python3
"""Dien tap one-pass 6R.7 tren Phase 5; khong cham R-set."""
from __future__ import annotations

import json
import sys

from ml import campaign as C
from ml.acceptance_guard import SnapshotReader, log_invocation, preflight, progress, quiet_run
from ml.acceptance_metrics import clusters, fp_ticks_a2, incident, labels_of, s7
from ml.acceptance_pass import run_one, specs_for
from ml.acceptance_report import fill, key
from ml.acceptance_skeleton import assert_same_shape, key_paths, leaves, skeleton
from ml.blast_radius import Routing, radius
from ml.fsm import DetectorFSM, FSMParams
from ml.labels import event_ticks
from ml.model import EnvelopeModel
from ml.rcampaign_runtime import targets_for
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer
from scripts.run_phase6r_acceptance import probes_for

REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase5/raw"
OUT = REPORT / "phase6r_rehearsal_b3.json"


def fake_groups(run_ids) -> dict[str, list[str]]:
    """Anh xa 18 run Phase 5 de cover moi nhanh cua fill()."""
    groups = {name: [] for name in ("RD", "RO", "RC", "RN", "RS")}
    for run_id in sorted(run_ids):
        if run_id in (
            "F-degrade-s1-s2-s3003-r1",
            "F-degrade-s2-s3-s3004-r1",
        ):
            group = "RD"
        elif run_id == "F-admin_down-s1-s2-s3001-r1":
            group = "RO"
        elif run_id.startswith("F-"):
            group = "RC"
        elif run_id.startswith("C-"):
            group = "RS"
        elif run_id.startswith("N-"):
            group = "RN"
        else:
            raise ValueError("run Phase 5 chua duoc anh xa: %s" % run_id)
        groups[group].append(run_id)
    return groups


def phase5_sidecar(meta: dict, routing, group: str) -> dict:
    """Them intervention de exercise dung nhanh log cua group gia."""
    out = dict(meta, interventions=[])
    record = meta["record"]
    if not record.get("fault"):
        return out
    targets = targets_for(record)
    events = {event["kind"]: event for event in meta["events"]}
    kinds = ("inject", "revert") if group == "RO" else ("revert",)
    out["interventions"] = [
        {
            "id": record["run_id"] + ":" + kind,
            "t_start": events[kind]["t_source"],
            "actor": "controller" if group == "RO" else "harness",
            "action": kind + ":" + record["fault"],
            "targets": targets,
            "blast_radius": sorted(radius(routing, targets)),
            "routing_sha256": routing.sha256,
        }
        for kind in kinds
    ]
    return out


def _content(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))["content"]


def _known_answer_2(traces, metas, groups, params) -> None:
    old = _content("phase6r_fsm.json")["results"]["runs"]
    group_of = {
        run_id: group for group, run_ids in groups.items() for run_id in run_ids
    }
    for run_id, expected in old.items():
        trace, meta = traces[run_id], metas[run_id]
        channel = key("envelope_only", "no_log")
        labels = labels_of(trace, meta)
        for level in ("suspect_level", "act_level"):
            ticks = fp_ticks_a2(trace, labels, channel, level)
            if ticks != expected["no_log"][level]["fp_tick_list"]:
                raise RuntimeError("KNOWN-ANSWER #2 tick mismatch: %s" % run_id)
            if clusters(ticks) != expected["no_log"][level]["fp_events"]:
                raise RuntimeError("KNOWN-ANSWER #2 event mismatch: %s" % run_id)
        if expected["fault"]:
            got = s7(trace, meta, channel, int(params.cooldown_s))["v1_violations"]
            if got != expected["no_log"]["s7_violations"]:
                raise RuntimeError("KNOWN-ANSWER #2 S7 mismatch: %s" % run_id)
        if group_of[run_id] not in groups:
            raise AssertionError(run_id)


def main() -> int:
    info = preflight("rehearsal")
    log_invocation(info)
    prereg = _content("phase6r_acceptance_prereg.json")
    frozen = prereg["frozen_configuration"]
    for path, sha256 in frozen["code_sha256"].items():
        if C.sha256_file(C.ROOT / path) != sha256:
            raise SystemExit("code lech prereg: " + path)

    model = EnvelopeModel.load(C.ROOT / frozen["artifact"]["file"])
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text(encoding="utf-8")
    )["collector_version"]
    params = FSMParams(**frozen["fsm_params"])
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    phase5_manifest = json.loads(
        (REPORT / "ml_dataset_manifest.json").read_text(encoding="utf-8")
    )
    manifest = phase5_manifest["runs"]
    constants = phase5_manifest["constants"]
    groups = fake_groups(manifest)
    group_of = {
        run_id: group for group, run_ids in groups.items() for run_id in run_ids
    }
    reader = SnapshotReader({key: value["sha256"] for key, value in manifest.items()})

    traces, metas, extras = {}, {}, {}
    order = sorted(manifest)
    with quiet_run():
        for index, run_id in enumerate(order, start=1):
            ok = False
            try:
                raw_meta = json.loads(
                    (RAW / (run_id + ".meta.json")).read_text(encoding="utf-8")
                )
                group = group_of[run_id]
                meta = phase5_sidecar(raw_meta, routing, group)
                snapshots = reader.read_once(run_id, RAW / (run_id + ".jsonl"))
                record = meta["record"]
                specs = specs_for(
                    group, meta, routing, lambda log: DetectorFSM(params, log)
                )
                trace = run_one(
                    run_id,
                    snapshots,
                    FastOnlineScorer(
                        model,
                        expected_collector_version=version,
                        conservation=conservation,
                        conservation_mode=prereg["channels"][
                            "conservation_mode_for_the_pass"
                        ],
                    ),
                    specs,
                    frozen["conservation"]["R"],
                    probes=probes_for(record),
                )
                if group == "RD":
                    label_window = event_ticks(len(snapshots), meta["events"])
                    measured = C.signal_check(
                        record,
                        constants,
                        snapshots,
                        label_window[0],
                        label_window[1],
                    )["max_separation"]
                    sidecar = manifest[run_id]["checks"]["max_separation"]
                    if measured != sidecar:
                        raise RuntimeError("separation mismatch: %s" % run_id)
                    extras[run_id] = {
                        "separation": measured,
                        "separation_sidecar": sidecar,
                    }
                traces[run_id], metas[run_id] = trace, meta
                ok = True
            finally:
                progress(index, len(order), run_id, ok)
                if not ok:
                    raise

    anchor = _content("phase6r_slo.json")["phase6_anchors"][
        "excess_eval_primary"
    ]["delay_per_run_ticks"]
    for run_id, delay in anchor.items():
        got = incident(
            traces[run_id],
            metas[run_id],
            key("envelope_only", "no_log"),
        )["first_tick"]
        expected = None if delay is None else 21 + delay
        if got != expected:
            raise RuntimeError("KNOWN-ANSWER #1 mismatch: %s" % run_id)
    _known_answer_2(traces, metas, groups, params)

    external = {
        "replay_o1": _content("phase6r_replay_o1.json"),
        "replay_o2": _content("phase6r_replay_o2.json"),
        "replay_o3": _content("phase6r_replay_o3_v2.json"),
        "stability": _content("phase6r_stability_v2.json"),
    }
    process = {
        "n_files_read": reader.n_files_read,
        "n_acceptance_invocations": 0,
        "git_head": info["head"],
        "python": info["python"],
        "numpy": info["numpy"],
        "pandas": info["pandas"],
    }
    skel = skeleton(groups)
    filled = fill(
        groups,
        traces,
        metas,
        extras,
        external,
        process,
        cooldown_ticks=int(params.cooldown_s),
    )
    assert_same_shape(skel, filled)
    null_paths = sorted(
        path
        for path in key_paths(filled)
        if _value_at(filled, path) is None
    )
    receipt = {
        "single_pass": True,
        "reader_n_files_read": reader.n_files_read,
        "n_runs": len(order),
        "known_answer_1": "phase6 anchors reproduced 8/8",
        "known_answer_2": "phase6r_fsm no_log reproduced 18/18",
        "separation_crosscheck": "2/2 RD-like runs exact",
        "shape_key_paths": len(key_paths(filled)),
        "shape_matches": True,
        "null_leaf_paths": null_paths,
        "filled": filled,
    }
    C.atomic_json(
        OUT,
        {
            "content": receipt,
            "content_sha256": C.sha256_bytes(C.canonical_json(receipt).encode()),
        },
    )
    sys.__stdout__.write("DONE\n")
    return 0


def _value_at(document: dict, path: str):
    value = document
    for part in path.strip("/").split("/"):
        value = value[part]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
