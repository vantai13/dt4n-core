#!/usr/bin/env python3
"""Ket qua cua bai kiem du doan C11 - DU DOAN CUA TOI SAI (Lesson 8.8).

Du doan da ghim (phase8_c11_prediction.json, truoc khi chay):
    dRSS o cau hinh production <= 1.0 MiB, diem 0.56 MiB.
    Falsifier da ghim: "Neu VAN > 1.0 MiB thi gia thuyet 'dung cu do chiem cho'
    bi BAC BO va do la RO RI THAT -> C11 FAIL, phai dieu tra tiep, KHONG duoc
    noi nguong."

Do duoc: 1.309 MiB.  > 1.0 MiB.  => FALSIFIER KICH HOAT. C11 = FAIL.

Cai DUNG trong gia thuyet: bo dung cu do that su ha dRSS tu 5.211 -> 1.309 MiB
(-3.90 MiB). Hieu ung "dung cu do chiem cho" la THAT va no CHIEM PHAN LON.

Cai SAI: diem uoc luong 0.56 MiB lech 0.75 MiB, va quan trong hon - no nam
SAI PHIA cua nguong. Phan du 1.309 MiB KHONG giai thich duoc bang dung cu do.
Do doc RSS 27.01 KiB/phut o nua sau la TANG BEN, khong phai cap phat mot lan.

Vi sao phep phan ra cua toi lech: no do chi phi bo nho bang cach NAP LAI file
JSON da ghi ra dia, roi coi do la chi phi giu trong tien trinh. Hai thu do
khong bang nhau (dict tu json.load khac voi cau truc tich luy dan; chua ke
phan manh cua allocator). Tuc la chinh "phep do doc lap" cua toi cung la mot
PROXY co thien lech - dung loai loi ma toi vua bat o proxy `srv2_rx` cua phep
kiem gia thuyet, chi khac la lan nay toi la nguoi mac.

Chay: .venv/bin/python scripts/build_phase8_c11_outcome.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

PRED = C.ROOT / "results/report/phase8_c11_prediction.json"
PROD = C.ROOT / "results/report/phase8_soak_production.json"
FIRST = C.ROOT / "results/report/phase8_soak.json"
LOG = C.ROOT / "logs/phase8_8/soak_production.log"
OUT = C.ROOT / "results/report/phase8_c11_outcome.json"


def rss_track():
    """Doc day RSS tu log de phan biet 'cap phat mot lan' voi 'tang ben'."""
    out = []
    if not LOG.exists():
        return out
    for m in re.finditer(r"t=(\d+)s rss=(\d+) KiB", LOG.read_text(encoding="utf-8")):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def main() -> int:
    if OUT.exists():
        print("[8.8/C11] da co ket qua, khong ghi de:", OUT)
        return 1
    pred = json.loads(PRED.read_text(encoding="utf-8"))
    prod = json.loads(PROD.read_text(encoding="utf-8"))
    first = json.loads(FIRST.read_text(encoding="utf-8"))

    pc = pred["content"]
    predicted = pc["PREDICTION"]["point_estimate_mib"]
    threshold = pc["sealed_threshold_mib"]
    measured = prod["content"]["resources"]["rss"]["delta_mib"]
    first_mib = first["content"]["resources"]["rss"]["delta_mib"]
    slope = prod["content"]["resources"]["rss"]["second_half_slope_kib_per_min"]
    first_slope = first["content"]["resources"]["rss"]["second_half_slope_kib_per_min"]

    track = rss_track()
    deltas = [(track[i][0], track[i][1] - track[i - 1][1])
              for i in range(1, len(track))]

    content = {
        "lesson": "8.8",
        "criterion": "C11",
        "tests": "results/report/phase8_c11_prediction.json",
        "prediction_sha256": pred["content_sha256"],
        "measured_receipt": "results/report/phase8_soak_production.json",
        "measured_sha256": prod["content_sha256"],
        "threshold_mib": threshold,
        "predicted_mib": predicted,
        "measured_mib": measured,
        "prediction_error_mib": round(measured - predicted, 3),
        "PREDICTION_OUTCOME": "SAI - falsifier da ghim BI KICH HOAT",
        "falsifier_text": pc["PREDICTION"]["falsifier"],
        "verdict": "FAIL",
        "verdict_is_not_model_correction": (
            "KHONG duoc xep PASS-with-model-correction. Rao #2 doi ban sua phai "
            "TIEN DOAN con so; ban sua cua toi tien doan 0.56 va do ra 1.309, "
            "tuc la no SAI, va sai sang phia BEN KIA nguong. Xep loai 4 o day "
            "chinh la 'sua can vi do duoc' - dung dinh nghia gian lan."),
        "what_the_hypothesis_got_RIGHT": {
            "claim": "dung cu do (timeline deque + sampler.rows) chiem phan lon dRSS",
            "first_run_mib": first_mib,
            "production_run_mib": measured,
            "reduction_mib": round(first_mib - measured, 3),
            "predicted_reduction_mib": (pc["independent_decomposition"] or {}).get("sum_mib"),
            "note": ("Bo dung cu do ha dRSS 3.90 MiB that. Hieu ung la THAT va "
                     "CHIEM PHAN LON. Nhung 'chiem phan lon' khong du de PASS."),
        },
        "what_the_hypothesis_got_WRONG": {
            "residual_mib": measured,
            "still_over_threshold_by_mib": round(measured - threshold, 3),
            "why_my_decomposition_was_biased": (
                "Toi do chi phi bo nho bang cach NAP LAI file JSON da ghi ra dia "
                "roi coi do la chi phi giu trong tien trinh. Hai thu khong bang "
                "nhau: dict tu json.load khac cau truc tich luy dan, va khong tinh "
                "phan manh allocator. Chinh 'phep do doc lap' cua toi la mot PROXY "
                "CO THIEN LECH - cung loai loi voi proxy `srv2_rx` bi nhieu ma "
                "phep kiem gia thuyet mac phai."),
        },
        "residual_growth_is_real": {
            "second_half_slope_kib_per_min": slope,
            "first_run_slope_kib_per_min": first_slope,
            "rss_track_t_kib": track,
            "deltas_per_300s_kib": deltas,
            "reading": ("Do doc nua sau 27.01 KiB/phut la TANG BEN, khong phai "
                        "mot cu cap phat roi phang. Ngoai suy 24 h ~ 38 MiB. "
                        "Khong tham hoa, nhung KHONG duoc goi la 'khong ro ri'."),
            "not_explained_by": {
                "intervention_log": (prod["content"]["resources"]
                                     .get("intervention_log_len_series")),
                "intervention_log_note": ("24 phan tu cho 12 can thiep - qua nho "
                                          "de giai thich 1.3 MiB."),
                "threads": prod["content"]["resources"]["thread_growth"],
                "exceptions": prod["content"]["controller_stats"]["exceptions"],
            },
        },
        "other_c11_components_PASS": {
            "errors": (prod["content"].get("log_counts") or {}).get("ERROR", 0),
            "thread_growth": prod["content"]["resources"]["thread_growth"],
            "exceptions": prod["content"]["controller_stats"]["exceptions"],
            "audit_chain_ok": prod["content"]["audit"]["chain"]["ok"],
            "chain_spans_rotation": prod["content"]["audit"]["chain_spans_rotation"],
            "note": "Chi thanh phan RSS truot. Ba thanh phan con lai cua C11 dat.",
        },
        "next_step_named": (
            "Phase 9 muc 1: chay soak production co tracemalloc/objgraph de quy "
            "trach 1.3 MiB nay ve tung diem cap phat. KHONG doan tiep - lan nay "
            "doan da sai roi."),
    }
    # Dung CUNG canonical serializer voi acceptance; checksum cu duoc tao bang
    # mot serialization khac nen sai co hoc ngay tu luc viet receipt.
    blob = C.canonical_json(content).encode("utf-8")
    OUT.write_text(json.dumps({
        "content": content,
        "content_sha256": hashlib.sha256(blob).hexdigest(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("du doan : %.2f MiB   do duoc: %.3f MiB   nguong: %.1f MiB"
          % (predicted, measured, threshold))
    print("=> DU DOAN SAI. C11 = FAIL.")
    print("   bo dung cu do ha duoc %.2f MiB (that), nhung con du %.3f MiB"
          % (first_mib - measured, measured))
    print("   do doc nua sau: %.2f KiB/phut (lan 1: %.2f)" % (slope, first_slope))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
