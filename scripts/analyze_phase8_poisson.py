#!/usr/bin/env python3
"""Doc run Poisson 1800 s x N va tra ba mon no (Lesson 8.8).

  1. C6-c  so THEO CAP voi sim: cung seed -> cung lich flood -> so tung luot,
           khong chi so phan phoi. Can lay tu sim DA VA (tat em), chay lai cho
           dung ba seed do - KHONG lay p50/p95 cua 10000 seed lam can cho 3 luot.
  2. C12-a con so DUY NHAT co nghia: ty le mu tren tong thoi gian van hanh
           duoi mot chu ky lam viec THAT, khong phai flood lien tuc (can tren)
           cung khong phai quiet (can duoi).
  3. Kiem GIA THUYET da niem phong o phase8_suppression_hypothesis.json bang
           du lieu tick tho (srv1 tx / srv2 rx) va pho `affected` cua cung run.

Khong chay lai thi nghiem nao. Chay:
  .venv/bin/python scripts/analyze_phase8_poisson.py
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
from controller.policy import PolicyParams  # noqa: E402
from controller.sim import poisson_schedule, run as sim_run  # noqa: E402
from ml import campaign as C  # noqa: E402

SRC = C.ROOT / "results/report/phase8_stability_poisson.json"
OUT = C.ROOT / "results/report/phase8_poisson.json"
HYP = C.ROOT / "results/report/phase8_suppression_hypothesis.json"
OUT_OF_ZONE = "link-s2-s3"


def sim_for(seed, horizon_s):
    """Chay CHINH sim (ban da va) tren CUNG seed -> so sanh theo cap."""
    schedule, spans = poisson_schedule(seed, horizon_s)
    result = sim_run(schedule, horizon_s, PolicyParams(), keep_timeline=False)
    return {
        "seed": seed,
        "n_spans": len(spans),
        "flood_s": round(sum(b - a for a, b in spans), 1),
        "n_actions": result.n_actions,
        "n_shutdown_reverts": result.n_shutdown_reverts,
        "n_mitigations": result.n_mitigations,
        "blind_fraction": round(result.blind_fraction, 4),
        "harm_fraction": round(result.harm_fraction, 4),
    }


def affected_profile(audit_path):
    """Pho `affected` + cause, doc tu CUNG file audit cua run do."""
    n_alarm = n_out = 0
    n_suppressed = 0
    for row in read_rows(audit_path):
        if row.get("kind") != "decision":
            continue
        view = row["input"]
        if view.get("cause") == "suppressed_intervention":
            n_suppressed += 1
        if view["state"] not in ("act", "suspect"):
            continue
        n_alarm += 1
        if any(OUT_OF_ZONE in entity for entity in view.get("affected") or ()):
            n_out += 1
    return {"n_alarming": n_alarm, "n_with_out_of_zone": n_out,
            "fraction_out_of_zone": round(n_out / n_alarm, 4) if n_alarm else None,
            "n_suppressed_ticks": n_suppressed}


def bg_flow_health(ticks):
    """Suc khoe luong nen srv1->srv2 UDP 2 Mbps: thu DUY NHAT di qua s2-s3."""
    rx = [(r["t_wall"], r["rx_mbps"]) for r in ticks
          if r["host"] == "srv2" and r.get("rate_valid")]
    if not rx:
        return {"n": 0, "note": "khong lay mau srv2 trong run nay"}
    values = [v for _, v in rx]
    half = len(values) // 2
    return {
        "n": len(values),
        "median_mbps": round(statistics.median(values), 4),
        "first_half_median": round(statistics.median(values[:half]), 4) if half else None,
        "second_half_median": round(statistics.median(values[half:]), 4) if half else None,
        "min_mbps": round(min(values), 4),
        "max_mbps": round(max(values), 4),
        "n_below_1mbps": sum(1 for v in values if v < 1.0),
        "fraction_below_1mbps": round(sum(1 for v in values if v < 1.0) / len(values), 4),
    }


def main() -> int:
    if OUT.exists():
        print("[8.8/poisson] da co, khong ghi de:", OUT)
        return 1
    if not SRC.exists():
        print("chua co", SRC)
        return 2
    src = json.loads(SRC.read_text(encoding="utf-8"))
    live_runs = src["content"]["runs"]
    horizon = src["content"]["duration_s"]

    audit_dirs = sorted(glob.glob(str(C.ROOT / "logs/phase8_stability/poisson_*")))
    audit_dir = Path(audit_dirs[-1]) if audit_dirs else None

    paired = []
    for index, run in enumerate(live_runs):
        seed = run["seed"]
        sim = sim_for(seed, horizon)
        audit_path = audit_dir / ("run_%02d.jsonl" % index) if audit_dir else None
        ticks_path = audit_dir / ("ticks_%02d.json" % index) if audit_dir else None
        profile = (affected_profile(audit_path)
                   if audit_path and audit_path.exists() else {})
        ticks = (json.loads(ticks_path.read_text(encoding="utf-8"))
                 if ticks_path and ticks_path.exists() else [])
        s11 = run.get("s11_by_t_source") or {}
        paired.append({
            "seed": seed,
            "sim": sim,
            "live": {
                "n_actions": run["n_actions"],
                "n_inject": run["n_inject"],
                "n_exceptions": run["n_exceptions"],
                "min_hold_s": run["min_hold_s"],
                "violates_t0": run["violates_t0"],
                "c12a": run["c12"]["c12a_fraction_of_uptime"],
                "c12b": run["c12"]["c12b_fraction_of_incident"],
                "c12c_longest_blind_s": run["c12"]["c12c_longest_blind_s"],
                "degraded_tick_fraction_h3": (
                    (run.get("degraded_tick_fraction") or {}).get("h3") or {}
                ).get("fraction"),
            },
            "delta_actions_live_minus_sim": run["n_actions"] - sim["n_actions"],
            "s11_by_t_source": {
                "n_type_i": len(s11.get("type_i") or []),
                "type_ii_count": s11.get("type_ii_count"),
                "n_unattributed": len(s11.get("unattributed") or []),
                "n_t_source_resolved": s11.get("n_t_source_resolved"),
            },
            "affected_profile": profile,
            "bg_flow_srv2_rx": bg_flow_health(ticks),
        })

    live_actions = [p["live"]["n_actions"] for p in paired]
    sim_actions = [p["sim"]["n_actions"] for p in paired]
    deltas = [p["delta_actions_live_minus_sim"] for p in paired]
    c12a = [p["live"]["c12a"] for p in paired]

    # --- kiem gia thuyet da niem phong ---
    hypothesis = json.loads(HYP.read_text(encoding="utf-8"))["content"]
    fractions = [p["affected_profile"].get("fraction_out_of_zone") for p in paired]
    bg_medians = [p["bg_flow_srv2_rx"].get("median_mbps") for p in paired]
    suppressed = [p["affected_profile"].get("n_suppressed_ticks") for p in paired]
    usable = all(v is not None for v in fractions + bg_medians)
    verdict = "KHONG KIEM DUOC (thieu du lieu srv2 hoac audit)"
    if usable:
        bg_alive = [m is not None and m >= 1.0 for m in bg_medians]
        high_out = [f is not None and f > 0.5 for f in fractions]
        if all(bg_alive) and all(high_out):
            verdict = ("PHU HOP P2: luong nen song (srv2 rx median >= 1 Mbps) "
                       "VA ty le tick chua %s > 50%% o moi seed" % OUT_OF_ZONE)
        elif all(bg_alive) and not any(high_out):
            verdict = ("BAC BO: luong nen song o moi seed nhung ty le tick chua "
                       "%s van THAP -> suc khoe luong nen KHONG giai thich duoc "
                       "hai che do" % OUT_OF_ZONE)
        elif any(bg_alive) != all(bg_alive):
            verdict = ("KIEM DUOC MOT PHAN: luong nen khac nhau giua cac seed; "
                       "doi chieu tung cap (bg_alive, fraction_out_of_zone) "
                       "trong bang `paired`")
        else:
            verdict = ("KHONG KET LUAN: luong nen chet o moi seed nen khong co "
                       "doi chung")

    content = {
        "lesson": "8.8",
        "source_receipt": str(SRC.relative_to(C.ROOT)),
        "source_sha256": src["content_sha256"],
        "horizon_s": horizon,
        "seeds": [p["seed"] for p in paired],
        "paired_comparison": paired,
        "c6c": {
            "live_actions": live_actions,
            "sim_actions_same_seed": sim_actions,
            "delta_live_minus_sim": deltas,
            "mean_abs_delta": round(statistics.fmean(abs(d) for d in deltas), 2),
            "all_within_sim_population_min_max": all(
                0 <= n <= 41 for n in live_actions),
            "no_t0_violation": all(not p["live"]["violates_t0"] for p in paired),
            "note": ("so THEO CAP voi sim DA VA (graceful_shutdown_revert=True). "
                     "Can dung la sim cua CHINH seed do, khong phai p50/p95 cua "
                     "10000 seed."),
        },
        "c12a_poisson": {
            "per_seed": c12a,
            "mean": round(statistics.fmean(c12a), 4),
            "min": min(c12a), "max": max(c12a),
            "meaning": ("ty le mu tren TONG thoi gian van hanh duoi chu ky lam "
                        "viec Poisson 6 su co/gio, thoi luong trung binh 120 s. "
                        "Day la con so DUY NHAT co nghia cho system card; 96.3% "
                        "(flood lien tuc) la CAN TREN va 0.0% (quiet) la CAN DUOI."),
        },
        "c8r": {
            "n_type_i_total": sum(p["s11_by_t_source"]["n_type_i"] for p in paired),
            "n_unattributed_total": sum(p["s11_by_t_source"]["n_unattributed"]
                                        for p in paired),
            "predicate": "t_start <= t_source < t_revert + cooldown_s",
        },
        "hypothesis_test": {
            "hypothesis_sha256": json.loads(HYP.read_text())["content_sha256"],
            "hypothesis_id": hypothesis["hypothesis_id"],
            "fraction_out_of_zone_per_seed": fractions,
            "srv2_rx_median_mbps_per_seed": bg_medians,
            "n_suppressed_ticks_per_seed": suppressed,
            "verdict": verdict,
            "rule": ("neu bac bo thi GHI BAC BO, khong bia gia thuyet moi sau "
                     "khi nhin so (dieu da khoa trong chinh file gia thuyet)"),
        },
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[8.8/poisson] live =", live_actions, "| sim cung seed =", sim_actions,
          "| delta =", deltas)
    print("  C12-a Poisson: per seed", c12a, "-> mean",
          content["c12a_poisson"]["mean"])
    print("  C8-r Loai I =", content["c8r"]["n_type_i_total"],
          "| khong quy ket duoc =", content["c8r"]["n_unattributed_total"])
    print("  gia thuyet uc che:", verdict)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
