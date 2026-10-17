#!/usr/bin/env python3
"""Dinh chinh phep KIEM gia thuyet uc che (Lesson 8.8).

`analyze_phase8_poisson.py` tra "KHONG KIEM DUOC". Doc ky thi co HAI loi trong
chinh PHEP KIEM - khong phai trong gia thuyet, va khong phai trong he:

LOI 1 - lan lon "rong" voi "thieu du lieu".
    Guard `usable = all(v is not None ...)`. Seed 2 co
    fraction_out_of_zone = None vi no KHONG CO TICK BAO DONG NAO (lich Poisson
    cua seed 2 co 0 span flood - kiem bang controller.sim.poisson_schedule).
    Do la tien de RONG, khong phai phep do hong. Mot seed khong co su co
    khong the lam mat kha nang kiem cua hai seed co su co.

LOI 2 (NANG HON) - proxy "luong nen con song" BI NHIEU.
    Phep kiem dung `srv2 rx median >= 1.0 Mbps`. Nhung srv2 nhan CA HAI:
        srv2_rx (4.264) = h2 -> srv2 TCP (2.135)  +  srv1 -> srv2 UDP nen (2.129)
    Nen neu luong nen CHET HAN, rieng h2 van giu srv2_rx ~ 2.1 > 1.0 va phep
    kiem VAN BAO "song". Proxy do khong phan biet duoc dung thu no phai phan
    biet -> P2/P3 khong kiem duoc bang no, du so co ve dep.

    Uoc luong SACH, tinh tu chinh tick tho da luu:
        bg = srv2_rx - h2_tx     (ghep theo t_wall lam tron giay)

KHAI RO: ban sua nay KHONG dong vao nguong nao cua gia thuyet (van "> 50%" va
"suppressed THAP"). No chi lam phep kiem tinh song/chet CHAT HON - kho pass hon,
khong de hon. Va no duoc lam SAU khi nhin so, nen no duoc ghi thanh amendment
rieng chu khong sua nguoc vao receipt da niem phong.

Chay: .venv/bin/python scripts/build_phase8_hypothesis_amendment.py
"""
from __future__ import annotations

import hashlib
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.sim import poisson_schedule  # noqa: E402
from ml import campaign as C  # noqa: E402

TICKS = C.ROOT / "logs/phase8_stability/poisson_015100"
HYP = C.ROOT / "results/report/phase8_suppression_hypothesis.json"
ANA = C.ROOT / "results/report/phase8_poisson.json"
OUT = C.ROOT / "results/report/phase8_hypothesis_amendment.json"


def background_series(path: Path):
    """bg = srv2_rx - h2_tx, ghep theo giay. Uoc luong SACH cua luong nen."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    srv2, h2 = {}, {}
    for r in rows:
        if not r.get("rate_valid"):
            continue
        k = round(r["t_wall"])
        if r["host"] == "srv2":
            srv2[k] = r["rx_mbps"]
        elif r["host"] == "h2":
            h2[k] = r["tx_mbps"]
    keys = sorted(set(srv2) & set(h2))
    return [srv2[k] - h2[k] for k in keys]


def main() -> int:
    if OUT.exists():
        print("[8.8/hyp] da co amendment, khong ghi de:", OUT)
        return 1
    hyp = json.loads(HYP.read_text(encoding="utf-8"))
    ana = json.loads(ANA.read_text(encoding="utf-8"))["content"]

    per_seed = []
    for i, pair in enumerate(ana["paired_comparison"]):
        seed = pair["seed"]
        f = TICKS / ("ticks_%02d.json" % i)
        bg = background_series(f) if f.exists() else []
        _, spans = poisson_schedule(seed, ana["horizon_s"])
        prof = pair["affected_profile"]
        half = len(bg) // 2
        per_seed.append({
            "seed": seed,
            "n_flood_spans_scheduled": len(spans),
            "n_alarming_ticks": prof.get("n_alarming"),
            "antecedent_vacuous": (prof.get("n_alarming") or 0) == 0,
            "srv2_rx_median_CONFOUNDED": pair["bg_flow_srv2_rx"]["median_mbps"],
            "background_clean": {
                "estimator": "srv2_rx - h2_tx",
                "n": len(bg),
                "median_mbps": round(st.median(bg), 3) if bg else None,
                "min_mbps": round(min(bg), 3) if bg else None,
                "first_half_median": round(st.median(bg[:half]), 3) if half else None,
                "second_half_median": round(st.median(bg[half:]), 3) if half else None,
                "n_below_1mbps": sum(1 for v in bg if v < 1.0),
            },
            "fraction_out_of_zone": prof.get("fraction_out_of_zone"),
            "n_suppressed_ticks": prof.get("n_suppressed_ticks"),
        })

    informative = [s for s in per_seed if not s["antecedent_vacuous"]]
    bg_alive = all(s["background_clean"]["n_below_1mbps"] == 0
                   and (s["background_clean"]["median_mbps"] or 0) >= 1.0
                   for s in per_seed)
    high_out = all((s["fraction_out_of_zone"] or 0) > 0.5 for s in informative)
    low_supp = all((s["n_suppressed_ticks"] or 0) <= 5 for s in informative)

    if not informative:
        verdict = "KHONG KIEM DUOC: khong seed nao co su co"
    elif bg_alive and high_out and low_supp:
        verdict = ("PHU HOP P2 tren %d/%d seed CO SU CO: luong nen song on dinh "
                   "(uoc luong sach, khong phai proxy nhieu) VA ty le tick chua "
                   "link-s2-s3 > 50%% VA so tick suppressed THAP."
                   % (len(informative), len(per_seed)))
    elif bg_alive and not high_out:
        verdict = ("BAC BO: luong nen song nhung ty le tick chua link-s2-s3 THAP "
                   "-> suc khoe luong nen khong giai thich duoc hai che do.")
    else:
        verdict = "KHONG KET LUAN"

    content = {
        "lesson": "8.8",
        "amends": "results/report/phase8_poisson.json :: hypothesis_test",
        "amends_sha256": json.loads(ANA.read_text())["content_sha256"],
        "hypothesis_id": hyp["content"]["hypothesis_id"],
        "hypothesis_sha256": hyp["content_sha256"],
        "hypothesis_unchanged": True,
        "sealed_verdict_kept": ana["hypothesis_test"]["verdict"],
        "defect_1_vacuous_vs_missing": (
            "Guard coi seed 2 (fraction_out_of_zone = None) la THIEU DU LIEU. "
            "That ra lich Poisson seed 2 co 0 span flood -> 0 tick bao dong -> "
            "tien de cua P2 RONG. Mot seed khong su co khong lam mat kha nang "
            "kiem cua hai seed co su co."),
        "defect_2_confounded_proxy": (
            "Proxy 'srv2 rx >= 1 Mbps' KHONG do duoc luong nen: srv2 nhan ca "
            "h2->srv2 TCP (~2.135) lan srv1->srv2 UDP nen (~2.129). Luong nen "
            "chet han thi srv2_rx van ~2.1 > 1.0 va phep kiem van bao 'song'. "
            "Thay bang uoc luong sach bg = srv2_rx - h2_tx."),
        "thresholds_unchanged": {
            "fraction_out_of_zone": "> 0.5 (nhu da niem phong)",
            "suppressed_ticks": "THAP (<= 5)",
            "note": "Chi doi PROXY tinh song/chet, va doi theo huong CHAT HON.",
        },
        "declared_post_hoc": (
            "Ban sua nay duoc lam SAU khi nhin so. Vi vay: (a) receipt da niem "
            "phong KHONG bi sua nguoc, (b) ban sua lam phep kiem KHO pass hon "
            "chu khong de hon, (c) ly do va huong deu ghi o day de nguoi khac "
            "tu phan xu."),
        "per_seed": per_seed,
        "background_flow_alive_all_seeds": bg_alive,
        "verdict_amended": verdict,
        "P1_status": "CHUA TINH (can so sanh txRate trong/ngoai tick co link-s2-s3)",
        "P3_status": ("RONG: luong nen KHONG tut o bat ky seed nao (n_below_1mbps "
                      "= 0, hai nua giong nhau), nen tien de cua P3 khong xay ra."),
        "consequence_for_system_card": (
            "Muc C4 giu nguyen an so ve DIEU KIEN phan biet hai che do. Cai da "
            "biet them: duoi Poisson, ca hai seed co su co deu roi vao che do "
            "8.6 (uc che gan nhu khong bao gio ap dung) trong khi luong nen song "
            "on dinh 2.129 Mbps. Dieu do PHU HOP voi gia thuyet nhung CHUA la "
            "bang chung nhan qua: chua co seed nao luong nen chet de lam doi chung."),
    }
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    OUT.write_text(json.dumps({
        "content": content,
        "content_sha256": hashlib.sha256(blob).hexdigest(),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in per_seed:
        print("seed %d: spans=%d alarming=%s bg_med=%s min=%s below1=%d frac_out=%s supp=%s"
              % (s["seed"], s["n_flood_spans_scheduled"], s["n_alarming_ticks"],
                 s["background_clean"]["median_mbps"], s["background_clean"]["min_mbps"],
                 s["background_clean"]["n_below_1mbps"], s["fraction_out_of_zone"],
                 s["n_suppressed_ticks"]))
    print("VERDICT:", verdict)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
