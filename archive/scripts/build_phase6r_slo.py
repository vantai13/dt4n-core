#!/usr/bin/env python3
"""Lesson 6R.1: seal operational SLOs, data budget, and R-campaign.

Run once, before implementation work for Phase 6R:
    python -m scripts.build_phase6r_slo

The generated JSON is immutable by default. Derived limits are executable
calculations rather than manually copied numbers.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone

from ml import campaign as C


REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_slo.json"

T_TICK_MS = 1000
ONSET_P95_TICKS = 1
T_COMPUTE_BUDGET_MS = 50
SOAK_MINUTES = 60

UPSTREAM = (
    "results/report/phase6_envelope.json",
    "results/report/phase6_envelope_cv.json",
    "results/report/phase6_envelope_ticks.csv",
    "results/report/phase6_recovery.json",
    "results/report/ml_dataset_split_manifest.json",
    "results/report/ground_truth.json",
    "results/report/soak_30min.json",
)


def rule_of_three_per_hour(n_ticks: int, tick_ms: int = T_TICK_MS) -> float:
    """Upper 95% event-rate bound after zero events in ``n_ticks``."""
    if n_ticks < 1:
        raise ValueError("n_ticks phai >= 1")
    return (3.0 / n_ticks) * (3_600_000.0 / tick_ms)


def mtbfa_lower_bound_minutes(soak_minutes: float) -> float:
    """Lower 95% MTBFA bound after zero alarms in a soak of length T."""
    if soak_minutes <= 0:
        raise ValueError("soak phai duong")
    return soak_minutes / 3.0


def debounce_ceiling(
    budget_ms: int,
    *,
    onset_ticks: int = ONSET_P95_TICKS,
    tick_ms: int = T_TICK_MS,
    compute_ms: int = T_COMPUTE_BUDGET_MS,
) -> int:
    """Largest N satisfying (onset + N - 1)*tick + compute <= budget."""
    room = budget_ms - compute_ms - onset_ticks * tick_ms
    n = 1 + math.floor(room / tick_ms)
    if n < 1:
        raise ValueError("ngan sach S4 khong du cho ca N=1: %d ms" % budget_ms)
    return int(n)


def t_detect_p95_ms(n_debounce: int) -> int:
    return (
        (ONSET_P95_TICKS + n_debounce - 1) * T_TICK_MS
        + T_COMPUTE_BUDGET_MS
    )


def measured_baseline() -> dict:
    """Recompute the temporal decomposition of all negative test ticks."""
    rows = list(
        csv.DictReader(
            (REPORT / "phase6_envelope_ticks.csv").open(encoding="utf-8")
        )
    )
    if len(rows) != 590:
        raise RuntimeError("ticks CSV phai 590 dong, nhan %d" % len(rows))

    def bucket(row: dict) -> str:
        if row["run_id"].startswith("C-"):
            return "control_run_full"
        return (
            "fault_run_pre_inject"
            if int(row["tick"]) <= 20
            else "fault_run_post_revert"
        )

    out: dict[str, dict] = {}
    spans: dict[str, list[int]] = {}
    for row in rows:
        if row["y"] != "0":
            continue
        values = out.setdefault(
            bucket(row),
            {"n_ticks": 0, "fp_excess": 0, "fp_dual": 0, "n_unknown": 0},
        )
        values["n_ticks"] += 1
        values["fp_excess"] += row["alarm_secondary_excess"] == "True"
        values["fp_dual"] += row["alarm_secondary_dual"] == "True"
        values["n_unknown"] += row["judgeable71"] != "True"
        if row["alarm_secondary_excess"] == "True":
            spans.setdefault(row["run_id"], []).append(int(row["tick"]))

    def n_clusters(ticks: list[int]) -> int:
        ordered = sorted(ticks)
        return 1 + sum(b - a > 1 for a, b in zip(ordered, ordered[1:]))

    steady = (
        out["control_run_full"]["n_ticks"]
        + out["fault_run_pre_inject"]["n_ticks"]
    )
    steady_fp = (
        out["control_run_full"]["fp_excess"]
        + out["fault_run_pre_inject"]["fp_excess"]
    )
    if steady_fp != 0:
        raise RuntimeError("nen tinh khong con 0 FP: %d" % steady_fp)
    events = {key: n_clusters(value) for key, value in sorted(spans.items())}
    return {
        "by_window": out,
        "steady_state_normal_ticks": steady,
        "steady_state_fp_ticks": steady_fp,
        "fp_events_excess": events,
        "n_fp_events_total": sum(events.values()),
        "fp_event_ticks": {key: sorted(value) for key, value in sorted(spans.items())},
        "claim": (
            "moi FP cua excess nam sau revert_tick=40; nen tinh "
            "(control + pre-inject) co 0 FP tren %d tick" % steady
        ),
        "implication": (
            "lambda_false_alarm = f_change * P(chum|change) + "
            "p_steady * 3600; so hang thu nhat DO DUOC (7/8 su kien moi "
            "thay doi cau hinh), so hang thu hai CHUA DO DU (0/%d tick)" % steady
        ),
    }


def phase6_anchors() -> dict:
    env = json.loads((REPORT / "phase6_envelope.json").read_text(encoding="utf-8"))[
        "content"
    ]
    rec = json.loads((REPORT / "phase6_recovery.json").read_text(encoding="utf-8"))[
        "content"
    ]
    gt = json.loads((REPORT / "ground_truth.json").read_text(encoding="utf-8"))[
        "receipt"
    ]["base_rate_primary"]["per_run"]
    exc = env["variants"]["secondary_excess"]
    dual = env["variants"]["secondary_dual"]
    separation = {
        key: value["max_separation"]
        for key, value in sorted(gt.items())
        if value.get("max_separation") is not None
    }
    return {
        "mask_for_slo": "eval_primary",
        "mask_note": (
            "eval_sensitivity loai 2 tick onset + 2 tick recovery moi run; "
            "SLO neo vao eval_primary bat loi hon. eval_sensitivity chi mo ta FP."
        ),
        "excess_eval_primary": {
            "recall": exc["scores"]["recall"],
            "fpr_all": exc["scores"]["fpr"],
            "fpr_control": exc["fpr"]["control"]["fpr"],
            "n_incidents": exc["delay"]["n_incidents"],
            "n_detected": exc["delay"]["n_detected"],
            "n_censored": exc["delay"]["n_censored"],
            "median_delay_ticks": exc["delay"]["median_delay_detected"],
            "delay_per_run_ticks": exc["delay"]["per_run"],
        },
        "dual_eval_primary": {
            "recall": dual["scores"]["recall"],
            "fpr_all": dual["scores"]["fpr"],
            "precision": dual["scores"]["precision"],
        },
        "thresholds_frozen": env["thresholds"],
        "recovery_span_max_ticks": rec["maximum_observed_recovery_span_ticks"],
        "recovery_cooldown_prior_ticks": rec[
            "recommended_phase8_cooldown_ticks"
        ],
        "recovery_provenance_warning": (
            "phase6_recovery.json la diagnostic hau-freeze tren run TEST; "
            "cooldown=8 chi la prior, gia tri cuoi hieu chinh tren R-C."
        ),
        "separation_per_fault_run": separation,
        "separation_gap_unknown": [11.486, 100.0],
        "separation_ceiling_note": (
            "admin_down cho 100.000 vi Delta=1, sigma=0, floor=0.01. Day la "
            "HANG SO CAU TRUC, khong phai cuong do; khong gop cac ho fault."
        ),
    }


def slo_table() -> list[dict]:
    n_max = debounce_ceiling(3000)
    soak_ticks = int(SOAK_MINUTES * 60 * 1000 / T_TICK_MS)
    alarm_bound = rule_of_three_per_hour(soak_ticks)
    return [
        {"id": "S1", "sli": "per_incident_detection_rate (tang suspect)",
         "target": {"op": ">=", "value": 0.875, "unit": "ty le su co"},
         "derived_from": "phase6 excess delay: n_detected=7/8, 1 censored",
         "measured_on": "R-D", "verifiable_now": True},
        {"id": "S2", "sli": "su kien bao dong sai moi gio, nen tinh",
         "target": {"op": "<=", "value": round(alarm_bound, 3),
                    "unit": "su kien/gio", "kind": "gioi han tren 95%"},
         "derived_from": "0 FP tren 278 tick nen tinh + rule of three; 3/%d x 3600" % soak_ticks,
         "measured_on": "R-S soak %d phut" % SOAK_MINUTES,
         "verifiable_now": False,
         "note": "885 tick chi ket luan <=12.2/gio; bat buoc co R-S."},
        {"id": "S3", "sli": "MTBFA, nen tinh",
         "target": {"op": ">=", "value": round(mtbfa_lower_bound_minutes(SOAK_MINUTES), 2),
                    "unit": "phut", "kind": "gioi han duoi 95%"},
         "derived_from": "MTBFA >= T/3 voi T=%d phut" % SOAK_MINUTES,
         "measured_on": "R-S (CUNG RUN voi S2)", "verifiable_now": False,
         "note": "CUNG MOT PHEP DO voi S2, hai don vi; khong phai hai chung cu."},
        {"id": "S4", "sli": "time_to_detect p95 (snapshot dau co dau vet -> doi trang thai)",
         "target": {"op": "<=", "value": 3000, "unit": "ms"},
         "derived_from": "ngan sach con cua <5s end-to-end (MASTER_PLAN_V2)",
         "measured_on": "R-D + R-O", "verifiable_now": True,
         "budget_decomposition_ms": {"quan_sat_vat_ly": 1000, "detector": 3000,
                                     "twin_ui": 1000, "tong": 5000}},
        {"id": "S4b", "sli": "tran debounce N (rang buoc suy ra tu S4)",
         "target": {"op": "<=", "value": n_max, "unit": "tick"},
         "derived_from": "t=(onset+N-1)*1000+50 <=3000 voi onset=1",
         "measured_on": "suy dien thuan, khong can du lieu", "verifiable_now": True,
         "pre_registered_choice": {"suspect": 1, "act": 2},
         "choice_rationale": "0 FP le tren 278 tick; N chi tang latency, N=2 chi dung cho act.",
         "t_detect_if": {str(n): t_detect_p95_ms(n) for n in (1, 2, 3, 5)}},
        {"id": "S5", "sli": "latency p95 observe()+step(), gom flatten + aggregate + score + FSM",
         "target": {"op": "<=", "value": 50, "unit": "ms"},
         "derived_from": "<=5% chu ky tick 1000 ms", "measured_on": "R-S",
         "verifiable_now": True, "note": "phai gom flatten; khong chi do score"},
        {"id": "S6", "sli": "tang RSS sau 30 phut",
         "target": {"op": "<=", "value": 1.0, "unit": "MiB"},
         "derived_from": "Phase 2 soak_30min.json: +212 KiB", "measured_on": "R-S",
         "verifiable_now": True},
        {"id": "S7", "sli": "khong dao dong",
         "target": {"op": "==", "value": 0, "unit": "mau X->Y->X trong cua so su co"},
         "derived_from": "chong phan hoi duong Phase 8", "measured_on": "R-D + R-O",
         "verifiable_now": True, "note": "normal->suspect->act duoc phep; quay lai trang thai da roi bi cam."},
        {"id": "S8", "sli": "hanh vi khi thieu du lieu",
         "target": {"op": "==", "value": 1.0, "unit": "ty le tick co cot non-finite -> unknown"},
         "derived_from": "8 dong judgeable71=False; chinh sach DT4N-M1", "measured_on": "R-O",
         "verifiable_now": True, "repeatable": True,
         "hard_constraint": "0% tick thieu du lieu duoc map sang normal"},
        {"id": "S9", "sli": "trang thai sau restart",
         "target": {"op": "==", "value": 1.0, "unit": "ty le tick dau dung policy"},
         "derived_from": "Phase 7 gate cua MASTER_PLAN_V2", "measured_on": "R-O",
         "verifiable_now": True, "repeatable": True,
         "declared_policy": "feature stateless (0 cot d1): suspect duoc phep ngay; act N=2 doi mot tick."},
        {"id": "S10", "sli": "hanh vi o tai ngoai vung hieu chinh",
         "target": {"kind": "bao, khong dat muc tieu"},
         "derived_from": "model card muc 4: unverified and likely", "measured_on": "R-N",
         "verifiable_now": True,
         "report_two_columns": {
             "fp_thuc": "alarm khong kem lossPct>0/qdiscDropDelta>0/state_up==0",
             "phat_hien_nghen_thuc": "alarm kem it nhat mot chung cu vat ly tren"},
         "note": "8-10 Mbps co the la nghen that; them 10 Mbps lam diem bao hoa."},
        {"id": "S11", "sli": "chong tu-kich-hoat",
         "target": {"op": "==", "value": 0, "unit": "lan vao act do controller"},
         "derived_from": "phan hoi duong Phase 8", "measured_on": "R-O",
         "verifiable_now": True, "repeatable": True},
        {"id": "S12", "sli": "staleness khi detector chet",
         "target": {"op": "<=", "value": 5000, "unit": "ms den luc twin stale"},
         "derived_from": "MASTER_PLAN_V2 Phase 7 gate: detector tat thi twin phai stale",
         "measured_on": "R-O", "verifiable_now": True, "repeatable": True,
         "ttl_ticks": 3, "ttl_rationale": "1 tick jitter; 2 mot snapshot mat; 3 detector im.",
         "why_added": "restart tam thoi khac detector chet vinh vien."},
        {"id": "S13", "sli": "truy vet mo hinh",
         "target": {"op": "==", "value": 1.0, "unit": "payload co modelVersion + artifact_sha256"},
         "derived_from": "Phase 8 can truy model tao canh bao", "measured_on": "test don vi",
         "verifiable_now": True},
    ]


def data_budget() -> list[dict]:
    return [
        {"decision": "E, K", "allowed": "giu nguyen phase6_envelope_cv.json", "forbidden": "moi thu; khong refit"},
        {"decision": "link_stats (mean/std 16 kenh rate)", "allowed": "ml_dataset_split_manifest.json[link_stats]", "forbidden": "tinh lai tu du lieu dang chay", "note": "nguon training-serving skew duy nhat cua envelope"},
        {"decision": "bounds 71 cot", "allowed": "ml_dataset_split_manifest.json[envelope]", "forbidden": "refit"},
        {"decision": "tran debounce N", "allowed": "S4 (ngan sach thoi gian)", "forbidden": "-"},
        {"decision": "gia tri debounce N cuoi", "allowed": "train CV + phat lai test de dem chum, khong nhan tham so y", "forbidden": "nhan test"},
        {"decision": "cooldown", "allowed": "prior 8 khai ro tu test; gia tri cuoi tren R-C: max span + 1", "forbidden": "R-O, tap test Phase 6", "note": "hieu chinh sach bang du lieu moi"},
        {"decision": "TTL staleness", "allowed": "thiet ke thuan, 3 tick", "forbidden": "-"},
        {"decision": "nguong bien the co dieu kien", "allowed": "train CV", "forbidden": "test, R-set"},
        {"decision": "chon giua 2 bien the", "allowed": "dang ky truoc, nghiem thu R-set mot lan", "forbidden": "thu lan hai"},
        {"decision": "tham so he thong", "allowed": "khong co nhan lien quan", "forbidden": "-"},
    ]


def r_campaign() -> list[dict]:
    return [
        {"group": "R-S", "n_runs": 3, "purpose": "S2 S3 S5 S6", "knob": "load=2M, no fault, 60 phut/run", "role": "nghiem thu", "repeatable": False, "new": True},
        {"group": "R-N", "n_runs": 6, "purpose": "S10 hai cot", "knob": "load in {6,8,10} Mbps x 2 seed", "role": "nghiem thu", "repeatable": False, "confound_warning": "alarm o 8-10 Mbps co the dung; phan loai bang chung cu vat ly"},
        {"group": "R-D", "n_runs": 10, "purpose": "dose-response, ED50", "knob": "degrade factor in {0.95,0.90,0.80,0.60,0.40} x {s1-s2,s2-s3}", "role": "nghiem thu", "repeatable": False, "dose_axis": "ml.campaign.signal_check -> max_separation (DO SAU khi chay)", "response_axis": "ty le tick y=1 co suspect", "analysis_prereg": "logistic detected ~ log10(separation); ED50 + CI cluster-bootstrap theo run", "scope": "CHI trong ho degrade"},
        {"group": "R-C", "n_runs": 4, "purpose": "hieu chinh cooldown doc lap test", "knob": "flood x2, shift x2", "role": "HIEU CHINH", "repeatable": False, "new": True},
        {"group": "R-O", "n_runs": 4, "purpose": "S8 S9 S11 S12", "knob": "restart; chan snapshot 5s; controller tat s1-s2; kill detector", "role": "nghiem thu", "repeatable": True, "repeatable_rationale": "do menh de logic, khong uoc luong xac suat; neu doi nguong thi dung"},
    ]


def build_content() -> dict:
    return {
        "slo_id": "DT4N-P6R-SLO-v2",
        "lesson": "6R.1",
        "sealed_before": ["ml/model.py", "ml/serve.py", "ml/fsm.py", "scripts/build_model_artifact.py"],
        "constants": {"tick_ms": T_TICK_MS, "onset_p95_ticks": ONSET_P95_TICKS, "compute_budget_ms": T_COMPUTE_BUDGET_MS, "soak_minutes": SOAK_MINUTES},
        "upstream_sha256": {path: C.sha256_file(C.ROOT / path) for path in UPSTREAM},
        "phase6_anchors": phase6_anchors(),
        "measured_baseline": measured_baseline(),
        "slo": slo_table(),
        "data_budget": data_budget(),
        "r_campaign": r_campaign(),
        "corrections_to_plan": [
            "SLO neo eval_primary 85.625%/5.35%, khong neo eval_sensitivity 87.50%/3.38%",
            "FPR x 3600 la category error: 0 FP/278 tick nen, moi FP nam hau-revert",
            "S2 <=1/gio khong kiem duoc voi 885 tick; them R-S",
            "envelope co 0 cot d1; link_stats la nguon skew con lai",
            "dose R-D la max_separation do sau, khong phai factor",
            "admin_down separation=100 la hang so cau truc; khong gop ho fault",
            "cooldown=8 tu test chi la prior; hieu chinh lai tren R-C",
            "S7 la 0 mau X->Y->X, khong phai <=2 lan doi state",
            "them S12 staleness va S13 model provenance",
        ],
    }


def main() -> int:
    if OUT.exists():
        print("[6R.1] %s da ton tai. SLO chot MOT lan. Khong ghi de." % OUT.name)
        return 1
    content = build_content()
    s4 = next(item for item in content["slo"] if item["id"] == "S4")
    s4b = next(item for item in content["slo"] if item["id"] == "S4b")
    assert s4b["target"]["value"] == debounce_ceiling(s4["target"]["value"])
    assert content["measured_baseline"]["steady_state_fp_ticks"] == 0
    for slo in content["slo"]:
        assert slo.get("derived_from"), "SLO %s thieu nguon" % slo["id"]
    doc = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
    }
    C.atomic_json(OUT, doc)
    baseline = content["measured_baseline"]
    print("[6R.1] da ghi", OUT.name)
    print("[6R.1] content_sha256 =", doc["content_sha256"])
    print("[6R.1] nen tinh: %d tick, %d FP  ->  gioi han tren %.1f bao dong/gio" % (baseline["steady_state_normal_ticks"], baseline["steady_state_fp_ticks"], rule_of_three_per_hour(baseline["steady_state_normal_ticks"])))
    print("[6R.1] soak %d phut  ->  gioi han tren %.2f bao dong/gio, MTBFA >= %.1f phut" % (SOAK_MINUTES, rule_of_three_per_hour(int(SOAK_MINUTES * 60)), mtbfa_lower_bound_minutes(SOAK_MINUTES)))
    print("[6R.1] tran debounce N =", s4b["target"]["value"], "| t_detect p95 theo N =", s4b["t_detect_if"])
    print("[6R.1] so su kien FP tren test =", baseline["n_fp_events_total"], "(tat ca hau-revert)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
