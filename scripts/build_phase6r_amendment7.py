#!/usr/bin/env python3
"""Register the prospective S11 repair after the sealed failure is known."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C


REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_amendment_7.json"
ALLOWED_DIRTY = {
    "scripts/diag_s11_suppression.py",
    "scripts/build_phase6r_amendment7.py",
    "results/report/phase6r_amendment_7.json",
}


def git_state():
    output = subprocess.run(
        ["git", "status", "--porcelain"], cwd=C.ROOT, capture_output=True, text=True, check=True
    ).stdout
    dirty = sorted(line[3:] for line in output.splitlines() if line)
    illegal = [
        path
        for path in dirty
        if path not in ALLOWED_DIRTY
        and not path.startswith("logs/")
        and path != "results/report/feature_audit.csv"
    ]
    if illegal:
        raise RuntimeError("commit before amendment 7: %s" % illegal)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    return {"head": head, "dirty_files": dirty}


def sealed(name):
    document = json.loads((REPORT / name).read_text())
    digest = C.sha256_bytes(C.canonical_json(document["content"]).encode())
    if digest != document["content_sha256"]:
        raise RuntimeError("receipt drift: " + name)
    return document


def main():
    if OUT.exists():
        print("[6R-A7] da ton tai")
        return 1
    amendment_6 = sealed("phase6r_amendment_6.json")
    failed = sealed("phase6r_replay_o3.json")
    stability = sealed("phase6r_stability.json")
    observed = {
        run_id: {
            "n_act_entries_in_suppression_window": item["n_act_entries_in_suppression_window"],
            "n_suppressed_ticks": item["n_suppressed_ticks"],
        }
        for run_id, item in failed["content"]["runs"].items()
    }
    if failed["content"]["verdict"] != "FAIL" or any(
        item != {"n_act_entries_in_suppression_window": 1, "n_suppressed_ticks": 0}
        for item in observed.values()
    ):
        raise RuntimeError("sealed S11 failure does not match amendment trigger")

    content = {
        "amendment_id": "DT4N-P6R-AMENDMENT-7",
        "amends": {
            "amendment_6_content_sha256": amendment_6["content_sha256"],
            "stability_v1_content_sha256": stability["content_sha256"],
        },
        "git": git_state(),
        "trigger": {
            "type": "sealed SLO failure",
            "slo": "S11",
            "failed_receipt_file_sha256": C.sha256_file(REPORT / "phase6r_replay_o3.json"),
            "failed_receipt_content_sha256": failed["content_sha256"],
            "observed_by_run": observed,
            "knowledge_state": "S11 FAIL was known before this amendment; every change below is a disclosed post-failure repair",
        },
        "diagnosis": {
            "tool": "scripts/diag_s11_suppression.py",
            "tool_sha256": C.sha256_file(C.ROOT / "scripts/diag_s11_suppression.py"),
            "scope": "two repeatable RO-ctl runs only; never R-S",
            "H1_unknown_before_suppression": {
                "confirmed": False,
                "observation": "ticks 21-28 are scored and alarming in both runs",
            },
            "H2_local_not_subset_of_zone": {
                "confirmed": True,
                "observation": "while inject is active, link-s2-s3 is outside the stored radius at tick 21 and link-s1-s3 plus link-s2-s3 are outside from tick 22",
                "mechanism": "the stored radius follows frozen pre-action routes through s1-s2 and omits the physical detour corridor s1-s3-s2",
            },
            "determinism": "same status, outside-zone links, act entry, and zero suppression in seeds 4301 and 4302",
        },
        "root_causes": {
            "point_not_interval": {
                "mechanism": "active_at covers only [t_start,t_start+cooldown); admin_down remains applied for about 20 s",
                "why_not_raise_cooldown": "cooldown describes post-action transient; raising it would create an overlong blind window and threaten S1/S4",
            },
            "pre_action_radius_omits_detour": {
                "mechanism": "strict local subset radius is retained, but the radius lacks the shortest alternate switch path after removing the administered link",
                "why_not_use_intersection": "suppressing when any one entity intersects the zone could hide independent out-of-zone evidence",
                "why_not_whole_network": "whole-network suppression would mask unrelated faults beyond the causally affected corridor",
            },
        },
        "planned_changes": {
            "ml/intervention_log.py": "pair inject/revert as an interval; open intervals use MAX_OPEN_S=120 lease and stale_open exposes expiry",
            "ml/blast_radius.py": "add deterministic detour radius for link-state interventions: remove target switch edge, find shortest alternate switch path, union its switches and links with the existing radius",
            "ml/rcampaign_runtime.py": "record detour-aware radius for future admin_down interventions",
            "ml/fsm.py": "expose stale_intervention after a lease expires; do not reorder unknown handling because H1 was falsified",
            "scripts/replay_phase6r_stability.py": "for v2 only, reconstruct amended admin_down radius from sealed targets after verifying routing SHA; preserve v1 receipt",
        },
        "unchanged": {
            "S11_target": "0 act entries",
            "cooldown_s": 8.0,
            "n_suspect": 1,
            "n_act": 2,
            "release_m": 3,
            "subset_rule": "all local violating entities must remain within the amended causal radius",
            "amendment_6_firewall": "unchanged; R-O1/R-O2 are not rerun",
        },
        "new_risks": {
            "masking": "a real independent fault on the declared intervention/detour corridor during the interval can be masked; document in model card v2",
            "stale_lease": "if revert is never recorded, suppression stops at MAX_OPEN_S and stale_intervention is exposed; fail noisy rather than silently blind",
            "historical_radius_reconstruction": "v2 replay uses a disclosed amended policy on the same repeatable RO-ctl snapshots; original sidecars and v1 receipt remain immutable",
        },
        "remeasurement_policy": {
            "allowed": "yes; S11 is a deterministic proposition on R-O repeatable=true",
            "conditions": [
                "keep target at zero",
                "reuse exactly the two registered RO-ctl runs",
                "do not delete or overwrite the failed receipt",
                "write phase6r_replay_o3_v2.json and identify it as measurement two",
                "commit this amendment before changing runtime code",
            ],
            "forbidden": [
                "loosen S11",
                "collect extra RO-ctl runs",
                "change scorer/FSM thresholds",
                "rerun R-O1/R-O2 on R-S after semantic changes",
            ],
        },
        "predictions_after_fix": {
            "P_S11_v2": "both runs have zero act entries and more than zero suppressed ticks; zero/zero is not PASS",
            "P_interval": "suppression spans inject through revert+8 s and stops thereafter",
            "P_lease": "an unclosed inject stops suppression at 120 s and becomes stale_intervention",
        },
        "timing_and_knowledge": {
            "labels_opened": False,
            "r_set_acceptance_opened": False,
            "R_S_read_for_diagnosis": False,
            "R_O3_detailed_output_read": True,
        },
        "deviation_policy": "immutable after commit",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(OUT, {"content": content, "content_sha256": C.sha256_bytes(C.canonical_json(content).encode())})
    print("[6R-A7] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
