#!/usr/bin/env python3
"""Suy phan quyet SLO tu receipt da niem phong; khong doc raw, khong cham lai."""
from __future__ import annotations

import json
import operator
import sys
from datetime import datetime, timezone

from ml import campaign as C
from ml.acceptance_stats import DosePoint, dose_bracket

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_verdicts.json"
OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq}


def sealed(name: str) -> dict:
    doc = json.loads((REPORT / name).read_text(encoding="utf-8"))
    digest = C.sha256_bytes(C.canonical_json(doc["content"]).encode())
    if digest != doc["content_sha256"]:
        raise RuntimeError("receipt bi sua: " + name)
    return doc


def judge(slo: dict, value) -> str:
    target = slo["target"]
    return "PASS" if OPS[target["op"]](value, target["value"]) else "FAIL"


def main() -> int:
    if OUT.exists():
        print("[6R-V] da ton tai, khong ghi de")
        return 1
    slo_doc = sealed("phase6r_slo.json")
    acc_doc = sealed("phase6r_acceptance.json")
    stab_doc = sealed("phase6r_stability_v2.json")
    slo = {item["id"]: item for item in slo_doc["content"]["slo"]}
    acc = acc_doc["content"]
    stab = stab_doc["content"]["closed_here"]

    s1 = acc["S1_S4"]
    s23 = acc["S2_S3"]
    rho = {run: value["rho"] for run, value in acc["residual"]["per_run"].items()}
    s1_env = s1["envelope_only"]["summary"]["detection_rate"]
    s1_comb = s1["combined"]["summary"]["detection_rate"]

    def stratified(channel: str) -> dict:
        per = s1[channel]["per_incident"]
        hi = [run for run in per if rho[run] >= 1.10]
        lo = [run for run in per if rho[run] <= 0.90]
        return {
            "rho_ge_1_10": [sum(per[run]["detected"] for run in hi), len(hi)],
            "rho_le_0_90": [sum(per[run]["detected"] for run in lo), len(lo)],
        }

    def bracket(channel: str, link: str | None = None) -> dict:
        points = acc["dose"]["axis_1"][channel]["points"]
        chosen = [
            DosePoint(run, value["separation"], value["detected"])
            for run, value in sorted(points.items())
            if link is None or ("-%s-" % link) in run
        ]
        return dose_bracket(chosen)

    s10 = {
        run: {
            "alarm_ticks": value["alarm_ticks"],
            "fp_strict": value["col_a"]["fp_ticks"],
            "fp_sensitive": value["col_b"]["fp_ticks"],
            "fp_residual": value["col_c"]["fp_ticks"],
        }
        for run, value in acc["S10"]["envelope_only"].items()
    }
    content = {
        "verdict_id": "DT4N-P6R-VERDICTS",
        "derived_from": {
            "slo_content_sha256": slo_doc["content_sha256"],
            "acceptance_content_sha256": acc_doc["content_sha256"],
            "stability_v2_content_sha256": stab_doc["content_sha256"],
        },
        "rule": "phan quyet = so da niem phong so voi slo.target; khong nguoi nao go tay",
        "slo": {
            "S1": {
                "registered_channel": "envelope_only",
                "value": s1_env,
                "target": slo["S1"]["target"],
                "verdict": judge(slo["S1"], s1_env),
                "combined_descriptive": s1_comb,
                "posthoc_stratified_by_rho": {
                    "label": "POST-HOC, mo ta; khong thay the phan quyet",
                    "envelope_only": stratified("envelope_only"),
                    "combined": stratified("combined"),
                },
            },
            "S2": {
                "registered_level": "suspect",
                "value": s23["envelope_only"]["rate_upper_per_hour"],
                "target": slo["S2"]["target"],
                "verdict": judge(slo["S2"], s23["envelope_only"]["rate_upper_per_hour"]),
                "combined_value": s23["combined"]["rate_upper_per_hour"],
                "exposure_hours": s23["envelope_only"]["exposure_hours"],
            },
            "S3": {
                "value": s23["envelope_only"]["mtbfa_lower_minutes"],
                "target": slo["S3"]["target"],
                "verdict": judge(slo["S3"], s23["envelope_only"]["mtbfa_lower_minutes"]),
                "note": "CUNG phep do voi S2, khong phai chung cu thu hai",
            },
            "S4": {
                "registered_channel": "envelope_only",
                "value_ms": s1["envelope_only"]["summary"]["t_detect_p95_ms"],
                "target": slo["S4"]["target"],
                "verdict": judge(slo["S4"], s1["envelope_only"]["summary"]["t_detect_p95_ms"]),
                "combined_value_ms": s1["combined"]["summary"]["t_detect_p95_ms"],
                "combined_meets_target": judge(
                    slo["S4"], s1["combined"]["summary"]["t_detect_p95_ms"]
                ) == "PASS",
            },
            "S7": {
                "verdict": "PASS" if acc["gates"]["G1"] else "FAIL",
                "evidence": "gate G1 (R-D + R-O, with_log va no_log)",
            },
            "S10": {"verdict": "REPORT_ONLY", "envelope_only": s10},
            "S12": {"verdict": "DEFERRED", "to": "Phase 7 (amendment 4)"},
            **{
                sid: {"verdict": stab[sid]["verdict"], "from": "phase6r_stability_v2"}
                for sid in ("S4b", "S5", "S6", "S8", "S9", "S11", "S13")
            },
        },
        "dose_axis_1_brackets": {
            "label": "thuat toan fallback DA DANG KY (ml.acceptance_stats.dose_bracket), bao cao THEM, khong thay fit",
            "envelope_only_all": bracket("envelope_only"),
            "envelope_only_s1_s2": bracket("envelope_only", "s1-s2"),
            "envelope_only_s2_s3": bracket("envelope_only", "s2-s3"),
            "combined_all": bracket("combined"),
            "registered_fit_envelope": acc["dose"]["axis_1"]["envelope_only"]["fit"],
            "registered_fit_combined": acc["dose"]["axis_1"]["combined"]["fit"],
        },
        "residual_outcome": acc["residual"]["outcome"],
        "gates": acc["gates"],
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        },
    )
    for sid, value in content["slo"].items():
        print("%-4s %s" % (sid, value["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
