#!/usr/bin/env python3
"""Phu luc phan tich cho A/B 8.6 - tinh TU RECEIPT DA NIEM PHONG, khong chay lai.

Tra loi hai cau hoi ma receipt goc khong tra loi duoc:
  1. Bien ket cuc co BAO HOA (hieu ung tran) khong?  -> arm_means + canh bao
  2. Ty le thoi gian DUOC BAO VE that su la bao nhieu? -> tinh tu audit
     (cap inject/revert), doc lap voi bien ket cuc.

Chay: .venv/bin/python scripts/build_phase8_ab_addendum.py
Ra:   results/report/phase8_ab_addendum.json   (immutable)
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.audit import read_rows  # noqa: E402
from measurements.ab_stats import arm_means, ceiling_warnings  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_ab_addendum.json"
AB = "results/report/phase8_ab_c5.json"
AUDIT_GLOB = "logs/phase8_ab/*/ab_A_b*_i*.jsonl"
WINDOW = (2.0, 122.0)


def protected_fraction(trial, audit_path):
    """Ty le thoi gian co can thiep dang mo trong cua so do, tu audit."""
    t0 = trial["t_flood"] + WINDOW[0]
    t1 = trial["t_flood"] + WINDOW[1]
    events = sorted((r["t_wall"], r["kind"]) for r in read_rows(audit_path)
                    if r["kind"] in ("inject", "revert"))
    protected, opened = 0.0, None
    holds, gaps, last_revert = [], [], None
    for t_wall, kind in events:
        if kind == "inject":
            opened = t_wall
            if last_revert is not None:
                gaps.append(t_wall - last_revert)
        elif opened is not None:
            protected += max(0.0, min(t_wall, t1) - max(opened, t0))
            holds.append(t_wall - opened)
            last_revert, opened = t_wall, None
    if opened is not None:
        protected += max(0.0, t1 - max(opened, t0))
    return {
        "protected_s": round(protected, 3),
        "fraction": round(protected / (t1 - t0), 4),
        "n_inject": sum(1 for _, k in events if k == "inject"),
        "holds_s": [round(h, 1) for h in holds],
        "gaps_s": [round(g, 2) for g in gaps],
    }


def main() -> int:
    if OUT.exists():
        print("[8.6-addendum] da co, khong ghi de:", OUT)
        return 1
    content_ab = json.loads((C.ROOT / AB).read_text(encoding="utf-8"))
    ab = content_ab["content"]
    trials = [t for t in ab["trials"] if not t["aborted"]]

    stats = arm_means(trials, key="primary")
    stats_h1 = arm_means([dict(t, v=t["secondary"]["h1"]) for t in trials], key="v")
    stats_h2 = arm_means([dict(t, v=t["secondary"]["h2"]) for t in trials], key="v")

    index = {(t["block"], t["index"]): t for t in trials if t["arm"] == "A"}
    per_trial = []
    for path in sorted(glob.glob(str(C.ROOT / AUDIT_GLOB))):
        name = Path(path).name
        block = int(name.split("_b")[1].split("_")[0])
        idx = int(name.split("_i")[1].split(".")[0])
        trial = index.get((block, idx))
        if trial is None:
            continue
        row = protected_fraction(trial, path)
        row.update(block=block, index=idx, h1_mbps=trial["secondary"]["h1"],
                   h3_mbps=trial["primary"])
        per_trial.append(row)

    fractions = [r["fraction"] for r in per_trial]
    holds = [h for r in per_trial for h in r["holds_s"]]
    gaps = [g for r in per_trial for g in r["gaps_s"]]
    h1_mean = stats_h1["A"]["mean"]
    implied_free_s = (h1_mean * 120.0 - 7.0 * 120.0) / (20.0 - 7.0)

    content = {
        "lesson": "8.6-addendum",
        "source_receipt": AB,
        "source_sha256": content_ab["content_sha256"],
        "question_1_ceiling": {
            "arm_means_h3": stats,
            "arm_means_h1": stats_h1,
            "arm_means_h2_untouched": stats_h2,
            "warnings": ceiling_warnings(stats),
            "reading": (
                "Nhanh A co SD = %.4f Mbps tren %d luot live (CV = %.4f%%) va trung "
                "binh %.4f ~ muc cua h2 KHONG he bi dong toi (%.4f). Bien ket cuc "
                "BAO HOA o toc do chao cua luong TCP: phan tut trong probe duoc bu "
                "lai bang recovery burst sau do, nen trung binh cua so hoi tu ve toc "
                "do chao. Hau qua: bien nay KHONG phan biet duoc muc bao ve 93%% voi "
                "100%%."
                % (stats["A"]["sd"], stats["A"]["n"],
                   100 * stats["A"]["sd"] / stats["A"]["mean"], stats["A"]["mean"],
                   stats_h2["A"]["mean"])
            ),
        },
        "question_2_protection": {
            "method": "tu audit: tong thoi gian co can thiep mo trong cua so do",
            "n_trials": len(per_trial),
            "fraction_mean": round(statistics.fmean(fractions), 4),
            "fraction_min": round(min(fractions), 4),
            "fraction_max": round(max(fractions), 4),
            "unprotected_s_mean": round((1 - statistics.fmean(fractions)) * 120, 2),
            "n_inject_per_trial": sorted({r["n_inject"] for r in per_trial}),
            "hold_s_observed": sorted({round(h) for h in holds}),
            "gap_revert_to_next_inject_s": {
                "mean": round(statistics.fmean(gaps), 2),
                "min": round(min(gaps), 2), "max": round(max(gaps), 2),
            },
            "cross_check_h1": {
                "h1_mean_mbps": h1_mean,
                "implied_unprotected_s": round(implied_free_s, 2),
                "audit_unprotected_s": round(
                    (1 - statistics.fmean(fractions)) * 120, 2),
                "agree_within_s": round(
                    abs(implied_free_s - (1 - statistics.fmean(fractions)) * 120), 2),
            },
        },
        "why_gaps_are_short": (
            "Sim 8.2 gia dinh sau revert detector bi uc che het cooldown 8 s nen "
            "phat hien lai mat ~9-13 s. Thuc te khoang trong chi 1-3 s, vi duoi "
            "flood 47 Mbps tap entity vi pham CO CHUA link-s2-s3 - entity DUY NHAT "
            "nam ngoai vung uc che 15/16 - nen dieu kien `local <= zone` cua "
            "ml/fsm.py khong thoa va uc che KHONG ap dung. Chinh 'lo ho uc che' do "
            "(phat hien o 8.3, 1/3 round) lam vong kin tai bao ve NHANH HON mo hinh: "
            "ty le bao ve do duoc %.1f%% so voi 82%% du doan. Doi lai la mat quan sat."
            % (100 * statistics.fmean(fractions))
        ),
        "implications": [
            "C5 VAN PASS va huong khong doi: 8/8 khoi cung chieu, doi chung am sach.",
            "KHONG duoc phat bieu 'khoi phuc 88%% goodput': +1.893 Mbps la chenh lech "
            "TAI TRAN cua bien ket cuc.",
            "Ket qua ablation la NULL TAI TRAN: ca hai nhanh cham cung mot tran nen "
            "phep so sanh khong co kha nang phan biet; bang chung phan biet that nam "
            "o cac ca AM TINH do offline.",
            "8.7 phai them mot bien BEN voi hien tuong dem: degraded_tick_fraction, "
            "va phai LUU chuoi tick tho (receipt 8.6 chi co n_ticks nen khong tinh "
            "nguoc duoc).",
        ],
        "per_trial": per_trial,
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[8.6-addendum] sha =", json.loads(OUT.read_text())["content_sha256"][:16])
    print("  arm A h3: mean %.4f sd %.4f  | canh bao: %s"
          % (stats["A"]["mean"], stats["A"]["sd"], content["question_1_ceiling"]["warnings"]))
    print("  ty le bao ve tu audit: %.3f (khong bao ve %.1f s); h1 suy ra %.1f s; lech %.2f s"
          % (content["question_2_protection"]["fraction_mean"],
             content["question_2_protection"]["unprotected_s_mean"],
             implied_free_s,
             content["question_2_protection"]["cross_check_h1"]["agree_within_s"]))
    print("  hold quan sat:", content["question_2_protection"]["hold_s_observed"],
          "| gap:", content["question_2_protection"]["gap_revert_to_next_inject_s"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
