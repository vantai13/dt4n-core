#!/usr/bin/env python3
"""Nghiem thu 6R.7: mot lan quet R-set, dien skeleton va niem phong."""
from __future__ import annotations

import json
import sys

from ml import campaign as C
from ml.acceptance_guard import (
    SnapshotReader,
    count_invocations,
    log_invocation,
    preflight,
    progress,
    quiet_run,
)
from ml.acceptance_pass import _num, run_one, specs_for
from ml.acceptance_report import fill
from ml.acceptance_skeleton import assert_same_shape, skeleton
from ml.blast_radius import Routing
from ml.fsm import DetectorFSM, FSMParams
from ml.labels import event_ticks
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer

REPORT = C.ROOT / "results/report"
RAW = C.ROOT / "data/phase6r/raw"
OUT = REPORT / "phase6r_acceptance.json"

EXTERNAL = {
    "replay_o1": "phase6r_replay_o1.json",
    "replay_o2": "phase6r_replay_o2.json",
    "replay_o3": "phase6r_replay_o3_v2.json",
    "stability": "phase6r_stability_v2.json",
}


def _document(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def _verified_content(name: str, expected_sha256: str) -> dict:
    document = _document(name)
    content = document["content"]
    actual = C.sha256_bytes(C.canonical_json(content).encode())
    if document.get("content_sha256") != actual or actual != expected_sha256:
        raise ValueError("content SHA lech prereg: %s" % name)
    return content


def _content_or_self(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    return document["content"] if "content" in document else document


def probes_for(record: dict) -> dict:
    """Lay target txRate tu cung snapshot trong lan quet dau cua R-D."""
    target = record.get("fault_target")
    if record.get("fault") != "degrade" or not target:
        return {}
    column = "link-%s.traffic.txRate" % target
    return {"target_tx": lambda flat, column=column: _num(flat.get(column))}


def _verify_environment(info: dict) -> None:
    receipt = _document("phase6r_equivalence.json")["content"]
    observed = {name: info[name] for name in ("python", "numpy", "pandas")}
    expected = {name: str(receipt[name]) for name in observed}
    if observed != expected:
        raise RuntimeError(
            "environment lech equivalence receipt: %r != %r" % (observed, expected)
        )


def main() -> int:
    # Giai doan 0: moi guard nay chay truoc byte R-set dau tien.
    info = preflight("acceptance")
    log_invocation(info)
    _verify_environment(info)

    prereg_document = _document("phase6r_acceptance_prereg.json")
    prereg = prereg_document["content"]
    if prereg_document.get("content_sha256") != C.sha256_bytes(
        C.canonical_json(prereg).encode()
    ):
        raise ValueError("self-hash prereg lech")
    frozen = prereg["frozen_configuration"]
    for path, sha256 in frozen["code_sha256"].items():
        if C.sha256_file(C.ROOT / path) != sha256:
            raise SystemExit("code lech prereg: " + path)

    model = EnvelopeModel.load(C.ROOT / frozen["artifact"]["file"])
    if model.content_sha256 != frozen["artifact"]["content_sha256"]:
        raise ValueError("model content SHA lech prereg")

    matrix = json.loads(
        (REPORT / "phase6r_rcampaign_matrix.json").read_text(encoding="utf-8")
    )
    records = {run["run_id"]: run for run in matrix["runs"]}
    groups = {}
    for run in matrix["runs"]:
        groups.setdefault(run["group"], []).append(run["run_id"])

    skeleton_document = _document("phase6r_acceptance.json")
    committed = skeleton_document["content"]
    if skeleton_document.get("skeleton_sha256") != C.sha256_bytes(
        C.canonical_json(committed).encode()
    ):
        raise ValueError("skeleton SHA lech")
    skel = skeleton(groups)
    assert_same_shape(skel, committed)

    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    params = FSMParams(**frozen["fsm_params"])
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text(encoding="utf-8")
    )["collector_version"]
    constants = matrix["constants"]

    manifest_path = REPORT / "phase6r_rcampaign_manifest.json"
    if C.sha256_file(manifest_path) != prereg["amends"][
        "rcampaign_manifest_file_sha256"
    ]:
        raise ValueError("R-campaign manifest file SHA lech prereg")
    manifest = _content_or_self(manifest_path)["runs"]
    reader = SnapshotReader({key: value["sha256"] for key, value in manifest.items()})
    external = {
        name: _verified_content(path, prereg["external_receipts"][name])
        for name, path in EXTERNAL.items()
    }
    order = [
        run["run_id"]
        for run in sorted(matrix["runs"], key=lambda record: record["exec_index"])
    ]

    # Giai doan 1: moi snapshot path duoc doc dung mot lan.
    traces, metas, extras = {}, {}, {}
    with quiet_run():
        for index, run_id in enumerate(order, start=1):
            ok = False
            try:
                meta = json.loads(
                    (RAW / (run_id + ".meta.json")).read_text(encoding="utf-8")
                )
                snapshots = reader.read_once(run_id, RAW / (run_id + ".jsonl"))
                record = records[run_id]
                specs = specs_for(
                    record["group"],
                    meta,
                    routing,
                    lambda log: DetectorFSM(params, log),
                )
                scorer = FastOnlineScorer(
                    model,
                    expected_collector_version=version,
                    conservation=conservation,
                    conservation_mode=prereg["channels"][
                        "conservation_mode_for_the_pass"
                    ],
                )
                trace = run_one(
                    run_id,
                    snapshots,
                    scorer,
                    specs,
                    frozen["conservation"]["R"],
                    probes=probes_for(record),
                )
                if record["group"] == "RD":
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
                        raise ValueError("separation lech sidecar: %s" % run_id)
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

    # Giai doan 2/3: chi con ham thuan va ghi receipt mot lan.
    filled = fill(
        groups,
        traces,
        metas,
        extras,
        external,
        process={
            "n_files_read": reader.n_files_read,
            "n_acceptance_invocations": count_invocations("acceptance"),
            "git_head": info["head"],
            "python": info["python"],
            "numpy": info["numpy"],
            "pandas": info["pandas"],
        },
        cooldown_ticks=int(params.cooldown_s),
    )
    assert_same_shape(skel, filled)
    C.atomic_json(
        OUT,
        {
            "content": filled,
            "content_sha256": C.sha256_bytes(C.canonical_json(filled).encode()),
        },
    )
    sys.__stdout__.write("DONE\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
