#!/usr/bin/env python3
"""C6 + C7 + hoi quy S11 duoi vong kin that (Lesson 8.7).

Ba che do, tieu chi KHOA TRUOC:
  flood  600 s : so hanh dong <= can sim (13); KHONG cap nao giu < T0
  quiet  600 s : 0 hanh dong
  poisson 1800 s x N : dung DUNG N seed dau cua sim, so THEO CAP

"Dem so hanh dong" mot minh co the CHE dao dong: 12 hanh dong don vao 40 s van
la dao dong. Nen kiem them KHOANG CACH giua cac su kien va min_hold_s.

Hoi quy S11: tieu chi quy ket khoa truoc, suy tu LUAT UC CHE DA GHIM:
  Loai I  - moi entity vi pham thuoc blast_radius(<target>-s1) -> quy cho
            CONTROLLER (uc che le ra phai bat ma khong bat)  -> GATE = 0
  Loai II - co >= 1 entity NGOAI vung (thuc te: link-s2-s3)   -> quy cho FLOOD

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_stability.py --mode flood --duration 600
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402
from phase8_ab_common import TwinSampler, bind_send, make_controller, require_clean  # noqa: E402
from phase8_infra_health import check as infra_check  # noqa: E402

from controller.policy import PolicyParams  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from measurements import blind_time  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing, radius  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_stability.json"
FLOOD_RATE_MBPS = 47
SIM = C.ROOT / "results/report/phase8_sim_predictions.json"


def poisson_spans(seed, horizon_s):
    """Dung CHINH ham cua sim -> cung seed, cung lich -> so sanh THEO CAP."""
    from controller.sim import poisson_schedule

    _, spans = poisson_schedule(seed, horizon_s)
    return spans


# Tre hien thi: controller nhin trang thai detector CHAM hon mot nhip. Do o 8.4:
# xac nhan du duong p50 667 ms / p95 1003 ms, cong chu ky control tick 1 s. Mot
# view doc tai t_inject + 1 s co the da duoc detector CONG BO TRUOC khi can thiep
# duoc ghi vao log - do la view CU, khong phai uc che that bai.
VIEW_LAG_S = 2.0


def classify_act_ticks(rows, spans, routing, target_link, lag_s=0.0):
    """Quy ket moi tick `act` trong khoang can thiep: Loai I hay Loai II.

    Doc tu cac dong audit `decision` - DUNG cai controller nhin thay (timeline
    cua detector khong luu evidence.affected). Tieu chi suy tu LUAT UC CHE DA
    GHIM trong release, khong phai chon sau khi nhin so 8.7.
    """
    zone = {"org.dt4n:" + e for e in radius(routing, {"links": [target_link],
                                                      "flows": []})}
    type_i, type_ii = [], []
    for row in rows:
        if row.get("kind") != "decision":
            continue
        view = row.get("input") or {}
        if view.get("state") != "act":
            continue
        t_wall = row.get("t_wall")
        if t_wall is None or not any(lo + lag_s <= t_wall < hi for lo, hi in spans):
            continue
        affected = set(view.get("affected") or ())
        item = {"t_wall": t_wall, "affected": sorted(affected)}
        if affected and affected <= zone:
            type_i.append(item)         # GATE: uc che le ra phai bat ma khong bat
        else:
            type_ii.append(item)        # co entity ngoai vung (thuc te link-s2-s3)
    return type_i, type_ii


def audit_rows(path):
    from controller.audit import read_rows

    return read_rows(path) if Path(path).exists() else []


def pairs_from_audit(rows):
    injects, reverts = {}, {}
    for row in rows:
        if row.get("kind") not in ("inject", "revert") or not row.get("actions"):
            continue
        key = blind_time.pair_key(row["actions"][0]["intervention_id"])
        (injects if row["kind"] == "inject" else reverts)[key] = row["t_wall"]
    out = []
    for key, t_inject in sorted(injects.items(), key=lambda kv: kv[1]):
        out.append({"key": key, "t_inject": t_inject,
                    "t_revert": reverts.get(key),
                    "hold_s": (reverts[key] - t_inject) if key in reverts else None})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("flood", "quiet", "poisson"), required=True)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    tag = args.tag or args.mode
    out = OUT.with_name("phase8_stability_%s.json" % tag)
    if out.exists():
        print("[8.7] da co receipt, khong ghi de:", out)
        return 1
    health_before = infra_check(raise_on_fail=True)

    params = PolicyParams()
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    audit_dir = C.ROOT / ("logs/phase8_stability/%s_%s"
                          % (tag, datetime.now(timezone.utc).strftime("%H%M%S")))
    audit_dir.mkdir(parents=True, exist_ok=True)

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    runs = seeds if args.mode == "poisson" else [None]
    budget_s = int(len(runs) * (args.duration + 180) + 300)

    results = []
    with Live(budget_s) as live:
        detector = live.start_detector()
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,),
                         name="twin-sse", daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published("normal", timeout_s=120)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and "h1-s1" not in twin.observed_bw():
            time.sleep(0.2)
        sampler = TwinSampler(twin).start()

        for run_index, seed in enumerate(runs):
            require_clean(live, twin, timeout_s=180.0)
            audit_path = audit_dir / ("run_%02d.jsonl" % run_index)
            controller = make_controller(twin, detector, audit_path)
            controller.bootstrap_safe_state()
            thread = threading.Thread(target=controller.run_forever,
                                      name="control", daemon=True)
            thread.start()
            t0 = time.time()
            spans_plan = (poisson_spans(seed, args.duration)
                          if args.mode == "poisson" else
                          ([(0.0, args.duration)] if args.mode == "flood" else []))
            flood = None
            try:
                if args.mode == "flood":
                    flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
                    with live.env.net_lock:
                        flood.apply(live.env.net)
                    time.sleep(args.duration)
                elif args.mode == "quiet":
                    time.sleep(args.duration)
                else:
                    now = 0.0
                    for span_start, span_end in spans_plan:
                        time.sleep(max(0.0, span_start - now))
                        flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
                        with live.env.net_lock:
                            flood.apply(live.env.net)
                        time.sleep(max(0.0, span_end - span_start))
                        with live.env.net_lock:
                            flood.revert(live.env.net)
                        flood = None
                        now = span_end
                    time.sleep(max(0.0, args.duration - now))
            finally:
                if flood is not None:
                    with live.env.net_lock:
                        flood.revert(live.env.net)
                controller.shutdown()
                thread.join(10)
            t1 = time.time()

            rows = audit_rows(audit_path)
            pairs = pairs_from_audit(rows)
            holds = [p["hold_s"] for p in pairs if p["hold_s"]]
            gaps = [b["t_inject"] - a["t_revert"]
                    for a, b in zip(pairs, pairs[1:])
                    if a["t_revert"] is not None]
            spans_wall = [(t0 + lo, t0 + hi) for lo, hi in spans_plan]
            spans_int = blind_time.merge(blind_time.intervals(rows))
            # BAO CA HAI: theo dung chu cua luat da khoa (lag = 0) VA sau khi
            # tru tre hien thi da do o 8.4. Khong im lang doi tieu chi.
            type_i, type_ii = classify_act_ticks(rows, spans_int, routing, "h1-s1")
            type_i_lag, _ = classify_act_ticks(rows, spans_int, routing, "h1-s1",
                                               lag_s=VIEW_LAG_S)
            c12 = blind_time.summarise(rows, t0, t1, incident_spans=spans_wall)
            results.append({
                "run_index": run_index, "seed": seed,
                "t0": t0, "t1": t1, "duration_s": round(t1 - t0, 1),
                "n_actions": sum(1 for r in rows if r["kind"] in ("inject", "revert")),
                "n_inject": sum(1 for r in rows if r["kind"] == "inject"),
                "n_commands": controller.stats["commands"],
                "n_exceptions": controller.stats["exceptions"],
                "holds_s": [round(h, 1) for h in holds],
                "min_hold_s": round(min(holds), 2) if holds else None,
                "violates_t0": [round(h, 2) for h in holds if h < params.t0_s - 0.5],
                "gaps_s": [round(g, 2) for g in gaps],
                "c12": c12,
                "s11_type_i": type_i,          # GATE theo dung chu cua luat
                "s11_type_i_after_view_lag": type_i_lag,
                "s11_view_lag_s": VIEW_LAG_S,
                "s11_type_ii_count": len(type_ii),
                "flood_spans_planned": spans_plan,
                "infra": infra_check(raise_on_fail=False),
            })
            print("[8.7/%s] run %d seed=%s: actions=%d min_hold=%s viphamT0=%s "
                  "S11-I=%d S11-II=%d C12a=%.3f C12b=%s"
                  % (args.mode, run_index, seed, results[-1]["n_actions"],
                     results[-1]["min_hold_s"], results[-1]["violates_t0"],
                     len(type_i), len(type_ii), c12["c12a_fraction_of_uptime"],
                     c12["c12b_fraction_of_incident"]))
        sampler.stop()
        stop_sse.set()

    sim = json.loads(SIM.read_text(encoding="utf-8"))["content"]
    bound = sim["modes"]["continuous_flood_600s"]["n_actions"]
    content = {
        "lesson": "8.7", "mode": args.mode, "duration_s": args.duration,
        "policy_params": params.__dict__,
        "sim_bound_actions_flood_600s": bound,
        "sim_quiet_actions": sim["modes"]["quiet_600s"]["n_actions"],
        "sim_poisson": sim["poisson"]["n_actions"],
        "runs": results,
        "c6_pass": (
            all(r["n_actions"] <= bound and not r["violates_t0"] for r in results)
            if args.mode == "flood" else
            all(r["n_actions"] == 0 for r in results) if args.mode == "quiet" else
            None),
        "s11_regression_pass_literal": all(not r["s11_type_i"] for r in results),
        "s11_regression_pass_after_view_lag": all(
            not r["s11_type_i_after_view_lag"] for r in results),
        "health_before": health_before,
        "log_counts": counter.counts,
    }
    if args.mode == "poisson":
        live_actions = [r["n_actions"] for r in results]
        content["poisson_live_actions"] = live_actions
        content["poisson_live_mean"] = round(statistics.fmean(live_actions), 2)
        content["poisson_within_sim_p05_p95"] = None   # doi chieu o 8.8
    C.atomic_json(out, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", out, "| C6 =", content["c6_pass"],
          "| S11 Loai I =", sum(len(r["s11_type_i"]) for r in results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
