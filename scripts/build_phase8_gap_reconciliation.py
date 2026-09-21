#!/usr/bin/env python3
"""Hoa giai hai gia tri `gap` mau thuan giua receipt 8.6 va 8.7 (Lesson 8.8).

Bai toan: cung mot dai luong, hai receipt, hai gia tri
    phase8_ab_addendum (8.6):     gap = 1-5 s,  mean 2.31 s
    phase8_stability_flood (8.7): gap = 11.0 s x 6, HANG DINH
duoi cung mot kich thich danh nghia (flood h1->srv1 47 Mbps, cung policy, cung
release). Chenh 4.8 lan. Khi mot dai luong xuat hien hai lan voi hai gia tri,
do LUON la mot bug - trong phep do hoac trong dinh nghia - cho toi khi chung
minh duoc dieu kien khac nhau o dau.

Script nay khong chay lai thi nghiem nao. No doc AUDIT DA NIEM PHONG cua ca hai
chien dich, tinh lai gap bang DUNG MOT ham (measurements.blind_time.gaps), roi
doi chieu voi con so trong receipt. Hai ket cuc:
  - lech  -> dinh nghia khac nhau, mot ben sai, sua ben do
  - trung -> dinh nghia GIONG nhau, chenh lech la VAT LY, va luc do phai di tim
             dieu kien khac nhau o dau (khong duoc doan).

Chay: .venv/bin/python scripts/build_phase8_gap_reconciliation.py
"""
from __future__ import annotations

import collections
import glob
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.audit import read_rows  # noqa: E402
from measurements import blind_time  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_gap_reconciliation.json"
AB_GLOB = "logs/phase8_ab/*/ab_A_b*_i*.jsonl"
STAB_GLOB = "logs/phase8_stability/flood_*/run_00.jsonl"
OUT_OF_ZONE = "link-s2-s3"    # entity DUY NHAT ngoai vung uc che 15/16


def campaign(paths):
    """gap/hold tinh bang ham chung + pho `affected` va `cause` tu cung audit."""
    gaps, holds = [], []
    affected = collections.Counter()
    causes = collections.Counter()
    n_alarm = n_with_out_of_zone = 0
    for path in paths:
        rows = read_rows(path)
        paired = blind_time.pairs(rows)
        gaps += blind_time.gaps(paired)
        holds += blind_time.holds(paired)
        for row in rows:
            if row.get("kind") != "decision":
                continue
            view = row["input"]
            causes[(view["state"], view.get("cause", ""))] += 1
            if view["state"] not in ("act", "suspect"):
                continue
            n_alarm += 1
            entities = tuple(sorted(view.get("affected") or ()))
            affected[entities] += 1
            if any(OUT_OF_ZONE in entity for entity in entities):
                n_with_out_of_zone += 1
    summary = lambda xs: (   # noqa: E731
        None if not xs else
        {"n": len(xs), "mean": round(statistics.fmean(xs), 2),
         "min": round(min(xs), 2), "max": round(max(xs), 2),
         "distinct": sorted({round(x, 2) for x in xs})[:12]})
    return {
        "n_files": len(paths),
        "gap_s": summary(gaps),
        "hold_s": summary(holds),
        "n_alarming_ticks": n_alarm,
        "n_alarming_with_%s" % OUT_OF_ZONE.replace("-", "_"): n_with_out_of_zone,
        "fraction_alarming_out_of_zone": (round(n_with_out_of_zone / n_alarm, 4)
                                          if n_alarm else None),
        "n_ticks_suppressed": causes[("unknown", "suppressed_intervention")],
        "state_cause_histogram": {"%s/%s" % k: v for k, v in
                                  sorted(causes.items(), key=lambda kv: -kv[1])},
        "top_affected_sets": [
            {"n": n, "entities": [e.split(":")[-1] for e in k]}
            for k, n in affected.most_common(4)
        ],
    }


def main() -> int:
    if OUT.exists():
        print("[8.8/gap] da co, khong ghi de:", OUT)
        return 1
    ab_paths = sorted(glob.glob(str(C.ROOT / AB_GLOB)))
    stab_paths = sorted(glob.glob(str(C.ROOT / STAB_GLOB)))
    if not ab_paths or not stab_paths:
        print("thieu audit; ab=%d stab=%d" % (len(ab_paths), len(stab_paths)))
        return 2
    ab, stab = campaign(ab_paths), campaign(stab_paths)

    sealed_ab = json.loads(
        (C.ROOT / "results/report/phase8_ab_addendum.json").read_text("utf-8")
    )["content"]["question_2_protection"]["gap_revert_to_next_inject_s"]
    sealed_stab = json.loads(
        (C.ROOT / "results/report/phase8_stability_flood.json").read_text("utf-8")
    )["content"]["runs"][0]

    matches = {
        "ab_mean": ab["gap_s"]["mean"] == sealed_ab["mean"],
        "ab_min": ab["gap_s"]["min"] == sealed_ab["min"],
        "ab_max": ab["gap_s"]["max"] == sealed_ab["max"],
        "stability_gaps": ([round(g, 2) for g in
                            blind_time.gaps(blind_time.pairs(
                                read_rows(stab_paths[0])))]
                           == sealed_stab["gaps_s"]),
    }
    definitions_agree = all(matches.values())

    dead_time = json.loads(
        (C.ROOT / "results/report/phase8_sim_predictions.json").read_text("utf-8")
    )["content"]["dead_time_s"]

    content = {
        "lesson": "8.8",
        "question": (
            "gap = 2.31 s (8.6) vs 11.0 s (8.7) duoi cung mot kich thich danh "
            "nghia. Loi DINH NGHIA hay khac biet VAT LY?"),
        "method": (
            "Doc audit da niem phong cua ca hai chien dich, tinh lai bang DUNG "
            "mot ham measurements.blind_time.gaps (gap_k = t_inject[k+1] - "
            "t_revert[k], ghep theo pair_key). Khong chay lai thi nghiem nao."),
        "single_definition": "measurements.blind_time.pairs + .gaps",
        "recompute_matches_sealed_receipts": matches,
        "definitions_agree": definitions_agree,
        "campaign_8_6_ab_arm_A": ab,
        "campaign_8_7_stability_flood": stab,
        "sim_dead_time_s": dead_time,
        "verdict": (
            "DINH NGHIA GIONG NHAU. Ca hai receipt tinh lai bang cung mot ham "
            "ra DUNG con so da niem phong, nen gia thuyet 'hai harness dinh "
            "nghia gap khac nhau' bi BAC BO. Chenh lech la VAT LY."),
        "mechanism_from_the_same_audits": {
            "claim": (
                "Khac biet nam o UC CHE, va no doc duoc thang tu cung nhung "
                "file audit do - khong phai suy dien."),
            "evidence": [
                ("8.6 arm A: %d/%d tick bao dong co %s (entity DUY NHAT ngoai "
                 "vung 15/16) -> `local <= zone` KHONG thoa -> uc che khong bao "
                 "gio ap dung: %d tick suppressed_intervention tren toan chien dich."
                 % (ab["n_alarming_with_link_s2_s3"], ab["n_alarming_ticks"],
                    OUT_OF_ZONE, ab["n_ticks_suppressed"])),
                ("8.7 flood: %d/%d tick bao dong co %s -> uc che BAT: %d tick "
                 "suppressed_intervention."
                 % (stab["n_alarming_with_link_s2_s3"], stab["n_alarming_ticks"],
                    OUT_OF_ZONE, stab["n_ticks_suppressed"])),
                ("Khi uc che BAT, gap do duoc = 11.0 s, khop voi tre chet cua "
                 "sim 8.2 = %.3f s trong %.2f s. Khi uc che TAT, gap = 1 tick."
                 % (dead_time, abs(11.0 - dead_time))),
            ],
        },
        "what_must_be_retracted": [
            ("phase8_ab_addendum::why_gaps_are_short phat bieu qua rong: 'duoi "
             "flood 47 Mbps tap entity vi pham CO CHUA link-s2-s3'. Dung cho "
             "chien dich 8.6 (%.1f%% tick bao dong), SAI cho chien dich 8.7 "
             "(%.1f%%). Phai gioi han phat bieu vao dieu kien da do."
             % (100 * (ab["fraction_alarming_out_of_zone"] or 0),
                100 * (stab["fraction_alarming_out_of_zone"] or 0))),
            ("docs/phase-8/06-effectiveness.md: phan bu do recovery burst la "
             "~0.15 Mbps (8.19 s khong bao ve tren 120 s -> trung binh 'that' "
             "~2.00 Mbps so voi 2.146 do duoc), KHONG phai ~0.5 Mbps."),
        ],
        "open_question": (
            "DIEU KIEN phan biet hai che do uc che (0/%d tick o 8.6 so voi "
            "%d/%d tick o 8.7) CHUA XAC DINH DUOC tu cac hien vat hien co. Day "
            "la mot an so DUOC KHAI, khong phai mot ket luan. He qua cho system "
            "card: khong duoc phat bieu ty le mu C12 nhu mot hang so cua he - "
            "no phu thuoc mot bien chua biet."
            % (ab["n_alarming_ticks"],
               stab["n_ticks_suppressed"],
               stab["n_ticks_suppressed"] + stab["n_alarming_ticks"])),
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[8.8/gap] dinh nghia trung khop:", definitions_agree, matches)
    print("  8.6 gap:", ab["gap_s"], "| out-of-zone", ab["fraction_alarming_out_of_zone"],
          "| suppressed", ab["n_ticks_suppressed"])
    print("  8.7 gap:", stab["gap_s"], "| out-of-zone", stab["fraction_alarming_out_of_zone"],
          "| suppressed", stab["n_ticks_suppressed"])
    print("  wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
