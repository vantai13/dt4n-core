#!/usr/bin/env python3
"""Pre-register FSM rules and predictions before any run replay."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C
from ml.blast_radius import Routing, fraction_of_local_columns, radius
from ml.fsm import CAUSES, STATES, FSMParams
from ml.model import EnvelopeModel

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_amendment_2.json"
FSM_RECEIPT = REPORT / "phase6r_fsm.json"
CODE = (
    "ml/fsm.py",
    "ml/blast_radius.py",
    "ml/intervention_log.py",
    "ml/serve.py",
    "ml/serve_fast.py",
    "ml/snapshot_contract.py",
    "scripts/replay_phase6r_fsm.py",
)
ARTIFACTS = (
    "results/report/phase6r_slo.json",
    "results/report/phase6r_amendment_1.json",
    "results/report/phase6_envelope.json",
    "models/envelope-1.0.0.json",
    "ditto/routing_table.json",
    "results/report/experiment_matrix.json",
)
ALLOWED_DIRTY = {
    "scripts/build_phase6r_amendment2.py",
    "test/test_phase6r_amendment2.py",
    "results/report/phase6r_amendment_2.json",
}


def git_state() -> dict:
    output = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
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
        raise RuntimeError("commit truoc khi dang ky: %s" % illegal)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"head": head, "dirty_files": dirty}


def revert_targets(record: dict) -> dict:
    parameters, fault = record["fault_parameters"], record["fault"]
    if fault in ("admin_down", "degrade"):
        return {"links": [parameters["link_key"]], "flows": []}
    if fault == "flood":
        return {
            "links": [],
            "flows": [[parameters["src"], parameters["dst"]]],
        }
    if fault == "shift":
        return {
            "links": [parameters["link_key"]],
            "flows": [[parameters["flood_src"], parameters["flood_dst"]]],
        }
    raise ValueError("fault chua ho tro: %s" % fault)


def build_content() -> dict:
    if FSM_RECEIPT.exists():
        raise RuntimeError(
            "%s da ton tai: da phat lai FSM, qua muon de dang ky"
            % FSM_RECEIPT.name
        )
    slo_document = json.loads(
        (REPORT / "phase6r_slo.json").read_text(encoding="utf-8")
    )
    envelope = json.loads(
        (REPORT / "phase6_envelope.json").read_text(encoding="utf-8")
    )["content"]
    contract = C.load_contract(REPORT / "experiment_matrix.json")
    model = EnvelopeModel.load(C.ROOT / "models/envelope-1.0.0.json")
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    params = FSMParams()
    s4b = next(
        item for item in slo_document["content"]["slo"] if item["id"] == "S4b"
    )
    choice = s4b["pre_registered_choice"]
    if (params.n_suspect, params.n_act) != (
        choice["suspect"],
        choice["act"],
    ):
        raise RuntimeError("N lech lua chon da niem phong o S4b")
    baseline = slo_document["content"]["measured_baseline"]
    clusters = baseline["fp_event_ticks"]
    maximum_cluster = max(len(ticks) for ticks in clusters.values())
    if params.cooldown_s < maximum_cluster + 1:
        raise RuntimeError("cooldown < chum dai nhat + 1")

    zones = {}
    for record in contract["runs"]:
        if record.get("fault") and record["split"] == "test":
            targets = revert_targets(record)
            entities = radius(routing, targets)
            zones[record["run_id"]] = {
                "targets": targets,
                "fraction_local_columns": round(
                    fraction_of_local_columns(model.columns, entities), 6
                ),
                "entities": sorted(entities),
            }
    full = sorted(
        run_id
        for run_id, zone in zones.items()
        if zone["fraction_local_columns"] == 1.0
    )
    partial = sorted(
        run_id
        for run_id, zone in zones.items()
        if zone["fraction_local_columns"] < 1.0
    )
    event_count = baseline["n_fp_events_total"]
    tick_count = sum(len(ticks) for ticks in clusters.values())
    excess_delay = envelope["variants"]["secondary_excess"]["delay"]["per_run"]
    dual_delay = envelope["variants"]["secondary_dual"]["delay"]["per_run"]

    return {
        "amendment_id": "DT4N-P6R-AMENDMENT-2",
        "amends": {"slo_content_sha256": slo_document["content_sha256"]},
        "git": git_state(),
        "artifacts_sha256": {
            path: C.sha256_file(C.ROOT / path) for path in ARTIFACTS
        },
        "code_sha256": {path: C.sha256_file(C.ROOT / path) for path in CODE},
        "knowledge_disclosure": {
            "inputs_to_predictions": "chi so lieu da niem phong: measured_baseline (6R.1), delay per_run (Phase 6), routing",
            "fsm_replayed_by_student": False,
            "tutor_sandbox_note": "nguoi huong dan da chay replay tren sandbox de kiem code chay duoc, SAU khi chot du doan va khong sua du doan; cam ket cua de tai la thu tu commit cua sinh vien",
            "status_of_test_replay": "tap test da tieu: replay la KIEM CHUNG CAI DAT (he qua tat dinh cua so lieu da biet), khong phai bang chung khoa hoc moi; kiem chung that o R-C, R-O, R-D",
        },
        "fsm": {
            "states": list(STATES),
            "unknown_causes": list(CAUSES),
            "params": {
                "n_suspect": params.n_suspect,
                "n_act": params.n_act,
                "release_m": params.release_m,
                "cooldown_s": params.cooldown_s,
            },
            "param_sources": {
                "n_suspect, n_act": "S4b pre_registered_choice (6R.1)",
                "release_m": "luat cau truc M > n_act (nho nhat = 3); khong hieu chinh, kiem tren R-D/R-O qua S7",
                "cooldown_s": "prior: chum FP dai nhat %d tick + 1 (6R.1 measured_baseline); gia tri cuoi tren R-C"
                % maximum_cluster,
            },
            "rules": {
                "alarm_reading": "Reading.suspect OR Reading.act",
                "enter_suspect": "n_suspect tick alarm lien tiep",
                "enter_act": "n_act tick Reading.act lien tiep",
                "release": "release_m tick judgeable khong alarm -> normal (tu suspect hoac act)",
                "hold": "dang act ma chi con suspect -> giu act",
                "unknown": "Reading unknown/warming_up hoac bi uc che -> reset moi bo dem; ra khoi unknown tinh tu normal",
                "rejected": "Reading rejected -> FSM khong tien, khong doi trang thai",
                "labels": "FSM khong doc nhan, khong doc feature tho",
            },
        },
        "suppression": {
            "source": "chi InterventionLog (append-only); khong co co bat tay",
            "rule": "tick dang alarm, co can thiep con han [t_start, t_start+cooldown_s), tap entity cua cot vi pham (bo agg.*) khac rong va la tap con cua hop vung anh huong -> unknown(cause=suppressed_intervention)",
            "agg_only_evidence": "giu alarm (khong co vi tri -> khong quy duoc cho can thiep)",
            "radius": "bac hai: moi cap host co duong cat link dich; tinh luc ghi log, kem routing_sha256",
            "replay_interventions": "CHI revert cua harness (analog hanh dong khoi phuc cua controller); inject la SU CO, khong ghi log",
            "replay_radius_by_run": zones,
            "radius_covers_whole_network": full,
            "radius_partial": partial,
        },
        "definitions": {
            "fp_tick": "tick y=0 (sau warmup) co state trong nhom",
            "fp_event": "chuoi toi dai cac tick FP LIEN KE theo chi so tick trong mot run (khop n_clusters cua 6R.1)",
            "levels": {
                "suspect_level": "state in {suspect, act}",
                "act_level": "state == act",
            },
            "incident_delay": "tick dau trong [inject+1, revert] co state trong nhom tru inject+1 (khop ml.metrics.detection_delay)",
            "s7_window": "[inject+1, revert+cooldown_ticks] voi cooldown_ticks = cooldown_s / 1.0 s",
            "s7_violation": "trong chuoi state da BO unknown/warming_up va gop lap lien ke, ton tai X,Y,X voi X in {suspect, act}",
        },
        "predictions": {
            "P1_no_log_suspect_fp_events": {
                "op": "==",
                "value": event_count,
                "why": "N_s=1 khong loc chum; hold M chi keo dai, khong tach/gop chum trong mot run",
            },
            "P1_no_log_suspect_fp_ticks": {
                "op": "in",
                "value": [tick_count, tick_count + params.release_m * event_count],
                "why": "moi chum keo dai toi da release_m tick boi hold",
            },
            "P1_no_log_act_fp_events": {
                "op": "<=",
                "value": event_count,
                "why": "act chi ton tai khi con alarm; moi chuoi act FP nam trong mot chum suspect FP",
            },
            "P2_log_fp_events_full_radius_runs": {
                "op": "==",
                "value": 0,
                "runs": full,
                "why": "vung = ca mang; FP chi con neu bang chung chi co agg.*",
            },
            "P2_log_fp_events_partial_radius_runs": {
                "op": "report",
                "runs": partial,
                "why": "vung mot phan; khong du co so du doan so luong",
            },
            "P3_suspect_delay_per_run_equals_phase6_excess": excess_delay,
            "P3_act_delay_per_run": {
                run_id: None if delay is None else delay + params.n_act - 1
                for run_id, delay in dual_delay.items()
            },
            "P3_note": "log chi co revert nen cua so loi khong bi uc che -> delay giong nhau co/khong log",
            "P4_s7_violations": {
                "op": "==",
                "value": 0,
                "scope": "8 run fault, co va khong log",
            },
            "P5_control_and_train_fp_events": {"op": "==", "value": 0},
        },
        "refutation_and_outcomes": {
            "P1_fail": "cai dat FSM hoac dinh nghia su kien sai -> sua code, KHONG sua du doan; ghi deviation",
            "P2_full_fail": "ton tai FP chi co bang chung agg.* hoac cot ngoai vung -> ghi phat hien; khong mo rong vung sau khi thay",
            "P3_fail": "FSM lam doi hanh vi trong cua so loi -> loi cai dat, dung lai",
            "P4_fail": "dao dong that -> khong duoc phat hanh FSM cho Phase 8 truoc khi co amendment moi",
            "S4": "danh gia o muc suspect (S4b); delay act bao cao kem, khong gate",
        },
        "forbidden": [
            "doi params, luat, dinh nghia sau khi chay replay_phase6r_fsm",
            "mo rong vung anh huong sau khi xem FP con lai",
            "ghi inject vao InterventionLog",
            "chon cooldown tu tap test",
        ],
        "deviation_policy": "bat bien sau commit; thay doi can amendment so tiep theo",
    }


def main() -> int:
    if OUT.exists():
        print("[6R-A2] da ton tai, khong ghi de")
        return 1
    content = build_content()
    document = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": content,
        "content_sha256": C.sha256_bytes(
            C.canonical_json(content).encode("utf-8")
        ),
    }
    C.atomic_json(OUT, document)
    print("[6R-A2] content_sha256 =", document["content_sha256"])
    print(
        "[6R-A2] vung phu ca mang:",
        content["suppression"]["radius_covers_whole_network"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
