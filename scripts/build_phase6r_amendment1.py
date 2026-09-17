#!/usr/bin/env python3
"""Pre-register Phase 6R conservation residual before any R-campaign run."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml import campaign as C
from ml import conservation as K
from ml import dataset as D
from ml.missing import apply_policy
from twin.link_direction import UPSTREAM_OF_CORE


REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_amendment_1.json"
HASH_FIELD = "content_sha256"
R_CAMPAIGN_DIR = C.ROOT / "data/phase6r"

PINNED_ARTIFACTS = (
    "results/report/phase6r_slo.json",
    "models/envelope-1.0.0.json",
    "results/report/ml_dataset_split_manifest.json",
    "results/report/experiment_matrix.json",
    "ditto/topology_spec.json",
)
CODE_AT_REGISTRATION = (
    "ml/conservation.py",
    "twin/link_direction.py",
    "mininet/topology.py",
    "rl/scenarios.py",
    "bridge/collector.py",
)
ALLOWED_DIRTY = {
    "scripts/build_phase6r_amendment1.py",
    "test/test_phase6r_amendment1.py",
    "results/report/phase6r_amendment_1.json",
}
ALLOWED_DIRTY_PREFIXES = ("logs/",)

SEALED_R_D_FACTORS = (0.95, 0.90, 0.80, 0.60, 0.40)
R_D_LINKS = {"s1-s2": 20.0, "s2-s3": 5.0}
BW_FLOOR_MBPS = 1.0
TARGET_RHO = (2.0, 1.5, 1.25, 0.8, 0.5)
RHO_DETECT = 1.10
RHO_SILENT = 0.90
MIN_TICK_SHARE = 0.50


def git_state() -> dict:
    def run(*argv):
        return subprocess.run(
            argv, cwd=C.ROOT, capture_output=True, text=True, check=True
        ).stdout

    dirty = sorted(
        line[3:]
        for line in run("git", "status", "--porcelain").splitlines()
        if line
    )
    illegal = [
        path
        for path in dirty
        if path not in ALLOWED_DIRTY
        and not path.startswith(ALLOWED_DIRTY_PREFIXES)
    ]
    if illegal:
        raise RuntimeError(
            "commit truoc khi dang ky; file chua commit: %s" % illegal
        )
    return {
        "head": run("git", "rev-parse", "HEAD").strip(),
        "dirty_files": dirty,
    }


def load_switches() -> list[str]:
    spec = json.loads(
        (C.ROOT / "ditto/topology_spec.json").read_text(encoding="utf-8")
    )
    return sorted(item["name"] for item in spec["switches"])


SWITCHES = load_switches()


def train_frame_with_keys() -> pd.DataFrame:
    """Rebuild train keys and prove bit-exact alignment with load_split()."""
    split = D.load_split()
    contract = C.load_contract(REPORT / "experiment_matrix.json")
    raw, _ = D._frames(contract, C.ROOT, list(contract["split"]["train"]))
    train, _ = apply_policy(
        raw, warmup_ticks=int(contract["constants"]["warmup_ticks"])
    )
    train = train.sort_values(["run_id", "tick"]).reset_index(drop=True)
    inc = K.incidence(UPSTREAM_OF_CORE, SWITCHES)
    columns = K.required_columns(inc)
    ours = train[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    theirs = split.X_train_envelope[columns].to_numpy(dtype=float)
    if ours.shape != theirs.shape or not np.array_equal(
        ours, theirs, equal_nan=True
    ):
        raise RuntimeError("khoa dong train khong khop X_train_envelope - dung lai")
    sources = {
        value
        for column in train.columns
        if column.endswith(".traffic.utilDirectionSource")
        for value in train[column].dropna().unique()
    }
    if sources != {"directed_map"}:
        raise RuntimeError("du lieu khong do bang ban do huong: %s" % sorted(sources))
    train["config_id"] = train["run_id"].map(
        lambda run_id: next(
            D.config_id(run)
            for run in contract["runs"]
            if run["run_id"] == run_id
        )
    )
    return train


def calibrate(train: pd.DataFrame) -> dict:
    inc = K.incidence(UPSTREAM_OF_CORE, SWITCHES)
    residual = K.residuals(train, inc)
    if not residual["judgeable"].all():
        raise RuntimeError(
            "train co dong residual khong judgeable: %d"
            % (~residual["judgeable"]).sum()
        )
    owner_index = int(residual["r_max"].to_numpy().argmax())
    threshold = float(residual["r_max"].iloc[owner_index])
    per_switch = {
        switch: {
            "median": float(residual["r." + switch].median()),
            "std": float(residual["r." + switch].std()),
            "min": float(residual["r." + switch].min()),
            "max": float(residual["r." + switch].max()),
        }
        for switch in SWITCHES
    }
    for switch, stats in per_switch.items():
        if abs(stats["median"]) > 0.005:
            raise RuntimeError(
                "median r(%s)=%.4f - nghi sai chieu tx/rx"
                % (switch, stats["median"])
            )
    per_config = (
        residual.assign(config_id=train["config_id"])
        .groupby("config_id")["r_max"]
        .max()
        .round(6)
        .to_dict()
    )
    return {
        "R": threshold,
        "rule": (
            "R = max_{train rows} max_S r(S); alarm iff judgeable and "
            "r_max > R (strict, one-sided)"
        ),
        "owner": {
            "run_id": train["run_id"].iloc[owner_index],
            "tick": int(train["tick"].iloc[owner_index]),
            "switch": residual["argmax_switch"].iloc[owner_index],
            "config_id": train["config_id"].iloc[owner_index],
        },
        "n_train_rows": len(residual),
        "per_switch": per_switch,
        "r_max_by_config": per_config,
        "r_max_p99": float(residual["r_max"].quantile(0.99)),
        "rule_of_three_fpr_upper_per_tick": 3.0 / len(residual),
        "why_no_loco": (
            "r(S) cua moi dong chi dung chinh dong do va topology dong bang; "
            "khong co tham so fit, nen held-out = in-sample. R van bi dong "
            "xau nhat cua train quyet dinh, nen phai bao owner."
        ),
    }


def offered_load_prior(train: pd.DataFrame) -> dict:
    load2 = train[train["config_id"] == "normal|2"]
    if load2.empty:
        raise RuntimeError("khong tim thay config 2M trong train")
    return {
        key: float(load2[K.link_column(key, "txRate")].median())
        for key in R_D_LINKS
    }


def sealed_design_collisions() -> dict:
    output = {}
    for key, baseline in R_D_LINKS.items():
        bandwidths = [
            max(BW_FLOOR_MBPS, baseline * (1 - factor))
            for factor in SEALED_R_D_FACTORS
        ]
        output[key] = {
            "new_bw_mbps": [round(value, 6) for value in bandwidths],
            "n_distinct_doses": len({round(value, 6) for value in bandwidths}),
        }
    return output


def corrected_factors(prior: dict) -> dict:
    output = {}
    for key, baseline in R_D_LINKS.items():
        offered_mbps = prior[key] * 8.0 / 1e6
        factors = [
            round(1.0 - (offered_mbps / rho) / baseline, 4)
            for rho in TARGET_RHO
        ]
        bandwidths = [baseline * (1 - factor) for factor in factors]
        if min(bandwidths) <= BW_FLOOR_MBPS or len(
            {round(value, 6) for value in bandwidths}
        ) != len(bandwidths):
            raise RuntimeError(
                "thiet ke R-D moi van cham floor hoac trung lieu: %s" % key
            )
        output[key] = factors
    return output


def prediction_table(prior: dict, factors: dict) -> list[dict]:
    rows = []
    for key, baseline in R_D_LINKS.items():
        for factor in factors[key]:
            rho = K.saturation_ratio(prior[key], baseline, factor)
            expected = (
                "detect"
                if rho >= RHO_DETECT
                else "silent"
                if rho <= RHO_SILENT
                else "no_prediction"
            )
            rows.append(
                {
                    "link": key,
                    "factor": factor,
                    "baseline_mbps": baseline,
                    "new_bw_mbps": max(1.0, baseline * (1 - factor)),
                    "rho_prior_2M": round(rho, 3),
                    "expected_prior": expected,
                    "expected_switch": UPSTREAM_OF_CORE[key][0],
                }
            )
    return rows


KNOWLEDGE_DISCLOSURE = {
    "origin": "post-hoc, exploratory; phan tich sau khi tap test Phase 6 da tieu",
    "test_runs_inspected": "ca 10 run test (tom tat r(S) theo pha), khong doi nguong/nhan nao",
    "observed_on_spent_test": {
        "F-degrade-s1-s2-s3003-r1": (
            "r(s1) trung binh 0.144 tick 22-40; 16/19 tick > 0.0797; "
            "lossPct=0; sum(in-out) tick 21-40 = +2.40 MB, tick 41-59 = -1.3 kB"
        ),
        "F-degrade-s2-s3-s3004-r1": "r(s2) trung binh 0.177; lossPct 27.4%",
        "F-admin_down-*": "r max <= 0.012 (residual KHONG phan ung)",
        "F-flood-*": "r trung binh 0.03 / 0.097",
        "F-shift-*": "r(s2) trung binh 0.67 / 0.62",
        "C-*": "r max <= 0.07",
    },
    "consequence": (
        "Chi ho degrade tren R-D la KIEM CHUNG. admin_down, flood, shift da "
        "bi nhin thay nen chi BAO CAO MO TA."
    ),
    "earlier_wrong_prior": (
        "Du doan nhap bat admin_down va khong bat shift da sai; ghi lai de "
        "khong trinh bay nhu du doan."
    ),
    "r_campaign_collected": False,
}


def build_content() -> dict:
    if R_CAMPAIGN_DIR.exists():
        raise RuntimeError(
            "%s da ton tai: R-campaign da thu, qua muon de dang ky"
            % R_CAMPAIGN_DIR
        )
    train = train_frame_with_keys()
    calibration = calibrate(train)
    prior = offered_load_prior(train)
    factors = corrected_factors(prior)
    slo = json.loads((REPORT / "phase6r_slo.json").read_text(encoding="utf-8"))
    inc = K.incidence(UPSTREAM_OF_CORE, SWITCHES)
    return {
        "amendment_id": "DT4N-P6R-AMENDMENT-1",
        "amends": {
            "slo_id": slo["content"]["slo_id"],
            "slo_content_sha256": slo["content_sha256"],
        },
        "git": git_state(),
        "pinned_artifacts_sha256": {
            rel: C.sha256_file(C.ROOT / rel) for rel in PINNED_ARTIFACTS
        },
        "code_at_registration_sha256": {
            rel: C.sha256_file(C.ROOT / rel) for rel in CODE_AT_REGISTRATION
        },
        "knowledge_disclosure": KNOWLEDGE_DISCLOSURE,
        "detector": {
            "name": "conservation_residual",
            "artifact_version_planned": "conservation-1.0.0",
            "envelope_artifact_unchanged": "models/envelope-1.0.0.json",
            "formula": "r(S) = (sum_in(S) - sum_out(S)) / max(sum_in(S), floor)",
            "floor_bps": K.RATE_FLOOR_BPS,
            "floor_origin": "bang floor rxRate/txRate cua envelope; khong phai tham so moi",
            "direction_source": "twin.link_direction.UPSTREAM_OF_CORE",
            "direction_semantics": "counter tren interface UPSTREAM: txRate=up->down, rxRate=down->up",
            "switches": SWITCHES,
            "incidence": inc,
            "stateless": True,
            "judgeable": "moi cot incidence finite; nguoc lai unknown, KHONG normal",
            "measures": "drop + tang backlog; khong phan biet drop voi xep hang",
        },
        "calibration": calibration,
        "combination": {
            "suspect": "(judgeable71 AND excess > E) OR (judgeable_cons AND r_max > R)",
            "act": "khong doi: dual rule cua envelope-1.0.0",
            "reason_field": "khi residual bao: ghi argmax_switch va r_max",
            "unknown": "tang khong judgeable khong duoc bao normal thay cho ca he",
        },
        "prediction": {
            "scope": "CHI ho degrade trong R-D (10 run, factor da sua)",
            "rho_rule": (
                "rho = median(link txRate, tick 2..20 cua chinh run) / "
                "(max(1, baseline*(1-factor))*1e6/8)"
            ),
            "rho_detect": RHO_DETECT,
            "rho_silent": RHO_SILENT,
            "run_detected": "ty le tick y=1 & eval_primary co residual alarm >= %.2f"
            % MIN_TICK_SHARE,
            "P1": "moi run rho >= %.2f: residual phat hien run" % RHO_DETECT,
            "P2": "moi run rho <= %.2f: residual KHONG phat hien run"
            % RHO_SILENT,
            "P3": "tren tick alarm: argmax_switch = upstream link degrade",
            "no_prediction_band": [RHO_SILENT, RHO_DETECT],
            "offered_load_prior_bps_2M": prior,
            "illustrative_table_using_prior": prediction_table(prior, factors),
        },
        "r_d_design_correction": {
            "sealed_in": "6R.1 r_campaign R-D knob",
            "defect": "LinkDegrade kep new_bw >=1.0 Mbps; factor niem phong trung lieu",
            "evidence_source": "code rl/scenarios.py (khong phai du lieu)",
            "sealed_collisions": sealed_design_collisions(),
            "target_rho": list(TARGET_RHO),
            "rule": "factor = 1 - (offered_Mbps_prior_2M / target_rho) / baseline; round 4",
            "corrected_factors": factors,
            "unchanged": "10 run, link, seed policy, t_inject=20, t_revert=40, load 2M, dose=separation",
            "requires": "R-D phai load 2M/client; rho that do tick 2..20",
        },
        "refutation": {
            "F1_sensitivity": "P1 dat <75% run rho>=1.10 -> BAC co che bao hoa",
            "F2_specificity_mechanism": "bat ky run rho<=0.90 bi phat hien -> BAC",
            "F3_background": "residual alarm >2% tick nen R-D -> BAC tinh dung duoc",
            "R_N_note": "R-N 8-10 Mbps co the bao hoa that; bao rho, khong tinh F3",
            "F4_localization": "argmax dung <90% tick alarm -> BAC dinh vi",
            "F5_incremental_value": "0 tick y=1 residual bat ma excess bo sot -> KHONG them",
            "F6_slo": "suspect ket hop vi pham S2 tren R-S -> KHONG them",
        },
        "outcomes": {
            "all_pass": "phat hanh conservation-1.0.0; suspect=excess OR residual",
            "F4_only": "giu phat hien, bo tuyen bo dinh vi",
            "any_of_F1_F2_F3_F5_F6": "khong them van hanh; giu envelope-1.0.0",
        },
        "forbidden": [
            "doi R, floor, rho_detect, rho_silent, MIN_TICK_SHARE sau R-campaign",
            "dung R-set de hieu chinh tham so",
            "them bien the residual thu hai sau ket qua",
            "goi ket qua admin_down/flood/shift la kiem chung",
        ],
        "deviation_policy": "Bat bien sau commit; thay doi can amendment tiep theo.",
    }


def main() -> int:
    if OUT.exists():
        print("[6R-A1] %s da ton tai. Dang ky MOT lan. Khong ghi de." % OUT.name)
        return 1
    content = build_content()
    doc = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": content,
        HASH_FIELD: C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
    }
    C.atomic_json(OUT, doc)
    print(
        "[6R-A1] R =",
        content["calibration"]["R"],
        "owner =",
        content["calibration"]["owner"],
    )
    print("[6R-A1] content_sha256 =", doc[HASH_FIELD])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
