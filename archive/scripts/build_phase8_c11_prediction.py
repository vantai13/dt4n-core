#!/usr/bin/env python3
"""Ghim DU DOAN cho lan do lai C11 - TRUOC khi chay (Lesson 8.8).

Lan soak dau (phase8_soak.json) cho dRSS = 5.21 MiB > nguong 1 MiB da niem
phong. Truoc khi goi do la mot ro ri, phai hoi: DO CO DUNG THUOC KHONG?

Khong. `scripts/run_phase8_soak.py:72-77` da ghi san rang giao thuc soak duoc
Phase 7 dang ky o CAU HINH PRODUCTION (timeline TAT, khong sampler), vi hai bo
dem do la DUNG CU DO chu khong phai he:

  * detector.timeline  : deque 4096 phan tu, VAN DANG DAY trong suot 1800 s
  * sampler.rows       : ~1 dong/tick/host, khong gioi han

Lan chay dau LO co `--production`, nen no do RSS cua "he + dung cu do" roi so
voi nguong cua "he". Do la so nham thuoc, khong phai phat hien ro ri.

DAY LA SUA THEO MO HINH, KHONG THEO SO LIEU: ban sua khong dong vao nguong
(van 1.0 MiB) va khong tru mot hang so nao. No doi DUNG cau hinh da dang ky.
Va no TIEN DOAN duoc con so, vi hai cau truc bi giu lai deu da duoc ghi ra dia
o lan chay dau - nen kich thuoc cua chung do duoc DOC LAP, truoc khi chay lai.

Chay:  sudo .venv/bin/python scripts/build_phase8_c11_prediction.py
Roi:   sudo -E .venv/bin/python scripts/run_phase8_soak.py --production --tag production
"""
from __future__ import annotations

import gc
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

SOAK = C.ROOT / "results/report/phase8_soak.json"
OUT = C.ROOT / "results/report/phase8_c11_prediction.json"
AUDIT_DIR = C.ROOT / "logs/phase8_soak/20260921T000229Z"


def rss_kib() -> int:
    return int(Path("/proc/self/status").read_text().split("VmRSS:")[1].split()[0])


def retained_cost():
    """Do THANG chi phi bo nho cua hai cau truc bi giu lai.

    Chung da duoc ghi ra dia o lan chay dau, nen nap lai dung nhung file do va
    do dRSS cho ta mot uoc luong DOC LAP - khong phai suy dien tu con so 5.21.
    """
    gc.collect()
    base = rss_kib()
    ticks = json.loads((AUDIT_DIR / "ticks.json").read_text())
    gc.collect()
    after_ticks = rss_kib()
    timeline = json.loads((AUDIT_DIR / "timeline.json").read_text())
    gc.collect()
    after_timeline = rss_kib()
    cost = {
        "n_ticks": len(ticks),
        "n_timeline": len(timeline),
        "ticks_mib": round((after_ticks - base) / 1024, 2),
        "timeline_mib": round((after_timeline - after_ticks) / 1024, 2),
    }
    cost["sum_mib"] = round(cost["ticks_mib"] + cost["timeline_mib"], 2)
    del ticks, timeline
    return cost


def main() -> int:
    if OUT.exists():
        print("[8.8/C11] da ghim du doan, khong ghi de:", OUT)
        return 1
    sealed = json.loads(SOAK.read_text())
    measured_mib = sealed["content"]["resources"]["rss"]["delta_mib"]
    cost = retained_cost()
    residual = round(measured_mib - cost["sum_mib"], 2)

    content = {
        "lesson": "8.8",
        "criterion": "C11",
        "sealed_threshold_mib": 1.0,
        "threshold_unchanged": True,
        "first_run": {
            "file": "results/report/phase8_soak.json",
            "content_sha256": sealed["content_sha256"],
            "delta_mib": measured_mib,
            "production_flag_used": False,
            "second_half_slope_kib_per_min":
                sealed["content"]["resources"]["rss"]["second_half_slope_kib_per_min"],
        },
        "defect": (
            "Lan chay dau KHONG dung --production, nen detector.timeline (deque "
            "4096, van dang day) va sampler.rows (khong gioi han) - CA HAI la "
            "dung cu do - nam trong cung tien trinh duoc do RSS. Giao thuc da "
            "dang ky (run_phase8_soak.py:72-77, soak_phase7_live_v2.py:60) yeu "
            "cau do o cau hinh production."
        ),
        "correction_kind": "model_not_data",
        "why_model_not_data": (
            "Nguong giu nguyen 1.0 MiB; khong tru hang so nao; khong doi dinh "
            "nghia dRSS. Chi chay DUNG cau hinh da dang ky tu Phase 7."
        ),
        "independent_decomposition": cost,
        "residual_mib": residual,
        "PREDICTION": {
            "statement": (
                "Chay lai soak 1800 s VOI --production se cho dRSS <= 1.0 MiB."
            ),
            "point_estimate_mib": residual,
            "falsifier": (
                "Neu dRSS o cau hinh production VAN > 1.0 MiB thi gia thuyet "
                "'dung cu do chiem cho' bi BAC BO va do la RO RI THAT -> C11 "
                "FAIL, phai dieu tra tiep, KHONG duoc noi nguong."
            ),
            "sealed_before_run_utc": datetime.now(timezone.utc).isoformat(),
        },
        "known_answer_test": (
            "Du doan duoc ghim TRUOC khi chay lai, va no TIEN DOAN con so chu "
            "khong THEO SAU no. Rao #2 va #3 cua verdict taxonomy."
        ),
    }
    # Dung CUNG canonical serializer voi acceptance. Ban dau script dung
    # json.dumps mac dinh (co khoang trang, ensure_ascii=False), nen checksum
    # tu khai khong the xac minh du noi dung khong doi.
    blob = C.canonical_json(content).encode("utf-8")
    OUT.write_text(json.dumps({
        "content": content,
        "content_sha256": hashlib.sha256(blob).hexdigest(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[8.8/C11] do duoc lan dau : %.2f MiB" % measured_mib)
    print("[8.8/C11] ticks giu lai   : %.2f MiB (%d dong)"
          % (cost["ticks_mib"], cost["n_ticks"]))
    print("[8.8/C11] timeline giu lai: %.2f MiB (%d dong)"
          % (cost["timeline_mib"], cost["n_timeline"]))
    print("[8.8/C11] DU DOAN dRSS production <= 1.0 MiB (diem: %.2f)" % residual)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
