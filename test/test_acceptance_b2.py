"""B.2: known-answer receipt 6R.4 va hinh dang skeleton truoc khi mo R-set."""
from __future__ import annotations

import copy
import json

import pytest

from ml import campaign as C
from ml.acceptance_metrics import clusters, fp_ticks_a2, labels_of, s7
from ml.acceptance_pass import FsmSpec, build_log, run_one, specs_for
from ml.blast_radius import Routing, radius, radius_with_detour
from ml.acceptance_skeleton import assert_same_shape, key_paths, leaves, skeleton
from ml.fsm import DetectorFSM, FSMParams
from ml.model import EnvelopeModel
from ml.serve import ConservationLayer
from ml.serve_fast import FastOnlineScorer

REPORT = C.ROOT / "results/report"


def test_clusters_is_amendment2_fp_event():
    assert clusters([]) == 0
    assert clusters([41, 42, 43, 47, 48]) == 2


def test_build_log_recomputes_both_zones_instead_of_trusting_sidecar():
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    targets = {"links": ["s1-s2"]}
    meta = {
        "interventions": [
            {
                "id": "fixture:inject",
                "t_start": 1.0,
                "actor": "controller",
                "action": "inject:admin_down",
                "targets": targets,
                "blast_radius": ["host-bogus"],
                "routing_sha256": routing.sha256,
            }
        ]
    }
    original = build_log(meta, routing, zone="original")._items[0].blast_radius
    detour = build_log(meta, routing, zone="detour")._items[0].blast_radius
    assert original == radius(routing, targets)
    assert detour == radius_with_detour(routing, targets)
    assert original != detour


def test_specs_for_modes_are_truthful_and_cover_rc_no_log():
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    expected_modes = {
        "RD": {"with_log", "no_log"},
        "RO": {"with_log", "no_log"},
        "RC": {"with_log", "original", "no_log"},
        "RS": {"no_log"},
        "RN": {"no_log"},
    }
    for group, modes in expected_modes.items():
        specs = specs_for(group, {"interventions": []}, routing, lambda log: object())
        assert {name.split("@", 1)[1] for name in specs} == modes
        assert len(specs) == 2 * len(modes)


def test_no_log_fsm_reproduces_6r4_receipt_bit_for_bit():
    prereg = json.loads(
        (REPORT / "phase6r_acceptance_prereg.json").read_text(encoding="utf-8")
    )["content"]
    params = FSMParams(**prereg["frozen_configuration"]["fsm_params"])
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    conservation = ConservationLayer.load(REPORT / "phase6r_amendment_1.json")
    version = json.loads(
        (REPORT / "ml_dataset_split_manifest.json").read_text(encoding="utf-8")
    )["collector_version"]
    old = json.loads((REPORT / "phase6r_fsm.json").read_text(encoding="utf-8"))[
        "content"
    ]["results"]["runs"]
    raw = C.ROOT / "data/phase5/raw"
    for run_id, expected in old.items():
        meta = json.loads(
            (raw / (run_id + ".meta.json")).read_text(encoding="utf-8")
        )
        snapshots = [
            json.loads(line)
            for line in (raw / (run_id + ".jsonl")).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        scorer = FastOnlineScorer(
            model,
            expected_collector_version=version,
            conservation=conservation,
            conservation_mode="shadow",
        )
        trace = run_one(
            run_id,
            snapshots,
            scorer,
            {"nolog": FsmSpec("envelope_only", lambda: DetectorFSM(params, None))},
            prereg["frozen_configuration"]["conservation"]["R"],
        )
        labels = labels_of(trace, meta)
        for level in ("suspect_level", "act_level"):
            got = fp_ticks_a2(trace, labels, "nolog", level)
            assert got == expected["no_log"][level]["fp_tick_list"], (run_id, level)
            assert clusters(got) == expected["no_log"][level]["fp_events"], (run_id, level)
        if expected["fault"]:
            assert s7(trace, meta, "nolog", int(params.cooldown_s))[
                "v1_violations"
            ] == expected["no_log"]["s7_violations"], run_id


def _groups():
    matrix = json.loads(
        (REPORT / "phase6r_rcampaign_matrix.json").read_text(encoding="utf-8")
    )
    groups = {}
    for run in matrix["runs"]:
        groups.setdefault(run["group"], []).append(run["run_id"])
    return groups


def test_skeleton_all_null_and_keyed_by_run_id():
    skel = skeleton(_groups())
    assert all(value is None for value in leaves(skel))
    assert (
        "/S1_S4/envelope_only/per_incident/RD-degrade-s1-s2-rho125-s4103-r1"
        in key_paths(skel)
    )


def test_skeleton_rejects_added_and_removed_rows():
    skel = skeleton(_groups())
    added = copy.deepcopy(skel)
    added["S2_S3"]["combined"]["extra"] = 1
    with pytest.raises(ValueError):
        assert_same_shape(skel, added)
    removed = copy.deepcopy(skel)
    del removed["S10"]["combined"]
    with pytest.raises(ValueError):
        assert_same_shape(skel, removed)
