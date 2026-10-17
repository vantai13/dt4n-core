#!/usr/bin/env python3
"""Sinh DU DOAN niem phong cua Lesson 8.2 - chay TRUOC moi phep do live.

Chay:  .venv/bin/python scripts/run_phase8_sim.py [--n-seeds N]
Ra:    results/report/phase8_sim_predictions.json   (immutable: khong ghi de)

Ba che do:
  1. Flood lien tuc 600 s            -> can C6 nhanh "co flood"
  2. Binh thuong 600 s               -> can C6 nhanh "binh thuong" (phai = 0)
  3. Poisson 1800 s x N seed         -> phan phoi n_actions / harm / blind
                                        -> p50/p95 cho C6 va C12

Moi tham so mo hinh deu kem trich dan receipt (bang `parameter_sources`).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.policy import DEAD_TIME_S, PolicyParams  # noqa: E402
from controller.sim import (  # noqa: E402
    SimParams,
    always,
    never,
    poisson_schedule,
    run,
    run_bangbang,
)
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_sim_predictions.json"
PREREG8 = "results/report/phase8_prereg.json"

PARAMETER_SOURCES = {
    "n_act=2, release_m=3, cooldown_s=8.0": "models/detector-release-1.0.0.json -> content.fsm_params",
    "d_obs_s=1.433 (p95)": "results/report/phase7_e2e_latency.json -> layers.phys_obs.p95_ms = 1432.619",
    "d_cmd_s=0.984 (p95)": "results/report/latency_command_randomized.json -> result.p95_ms = 984.190",
    "tick=1.0 s": "bridge/detector_contract.py::TICK_INTERVAL_MS = 1000",
    "limit_mbps=7.0": "results/report/phase8_prereg.json -> content.actuator.limit_mbps",
    "default_mbps=20.0": "mininet/topology.py:88 (bw_backbone=20)",
    "t_max_s=110 < 120": "ml/intervention_log.py::MAX_OPEN_S = 120.0",
    "probe_w_s=14 >= 11.433": "cooldown 8.0 + phys_obs p95 1.433 + n_act 2 tick",
    "tick_unknown_after_tc=1": "F8-6: setBandwidth dung lai qdisc, bo dem ve 0",
}

CAVEAT = (
    "latency_command_randomized.json do tren collector qdisc_v2, con release "
    "detector-release-1.0.0 doi collector v3-qdisc-ratevalid; do tre lenh la "
    "duong truyen (Ditto -> agent -> tc) nen khong phu thuoc phien ban feature, "
    "nhung day la mot khac biet phai khai."
)


def sha256_of(rel_path: str) -> str:
    return C.sha256_bytes((C.ROOT / rel_path).read_bytes())


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return {}

    def pick(q):
        index = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
        return ordered[index]

    return {
        "min": ordered[0],
        "p50": pick(0.50),
        "p95": pick(0.95),
        "max": ordered[-1],
        "mean": round(statistics.fmean(ordered), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-seeds", type=int, default=2000)
    parser.add_argument("--horizon", type=float, default=1800.0)
    args = parser.parse_args()

    if OUT.exists():
        print("[P8.2] da niem phong, khong ghi de:", OUT)
        return 1

    policy = PolicyParams()
    sim = SimParams()

    # --- che do 1 + 2 ---------------------------------------------------
    flood = run(always, 600.0, policy, sim)
    quiet = run(never, 600.0, policy, sim)
    bangbang = run_bangbang(always, 600.0, sim)
    optimistic = run(always, 600.0, policy, SimParams(d_obs_s=1.159, d_cmd_s=0.675))
    unsuppressed = run(always, 600.0, policy,
                       SimParams(suppressed_during_mitigation=False))

    # --- che do 3: Poisson ----------------------------------------------
    per_seed = []
    for seed in range(args.n_seeds):
        schedule, spans = poisson_schedule(seed, args.horizon)
        result = run(schedule, args.horizon, policy, sim, keep_timeline=False)
        per_seed.append(
            {
                "n_actions": result.n_actions,
                "n_mitigations": result.n_mitigations,
                "harm_fraction": result.harm_fraction,
                "blind_fraction": result.blind_fraction,
                "flood_s": result.flood_s,
                "max_open_s": result.max_open_s,
                "n_spans": len(spans),
            }
        )

    content = {
        "prediction_id": "DT4N-P8-SIM-PREDICTIONS",
        "lesson": "8.2",
        "sealed_before": "moi phep do live cua 8.6 va 8.7",
        "policy_params": policy.__dict__,
        "sim_params": sim.__dict__,
        "dead_time_s": round(DEAD_TIME_S, 3),
        "parameter_sources": PARAMETER_SOURCES,
        "caveat": CAVEAT,
        "modes": {
            "continuous_flood_600s": flood.as_dict(),
            "quiet_600s": quiet.as_dict(),
            "bangbang_control_600s": bangbang.as_dict(),
            "continuous_flood_600s_optimistic_p50": optimistic.as_dict(),
            "continuous_flood_600s_unsuppressed_branch_B": unsuppressed.as_dict(),
        },
        "timeline_continuous_flood": flood.timeline,
        "poisson": {
            "n_seeds": args.n_seeds,
            "horizon_s": args.horizon,
            "rate_per_hour": 6.0,
            "mean_duration_s": 120.0,
            "n_actions": percentiles([r["n_actions"] for r in per_seed]),
            "n_mitigations": percentiles([r["n_mitigations"] for r in per_seed]),
            "harm_fraction": percentiles(
                [r["harm_fraction"] for r in per_seed if r["flood_s"]]
            ),
            "blind_fraction": percentiles([r["blind_fraction"] for r in per_seed]),
            "max_open_s": percentiles([r["max_open_s"] for r in per_seed]),
        },
        "predictions": {
            "C6_bound_actions_per_600s_under_continuous_flood": flood.n_actions,
            "C6_actions_per_600s_when_normal": quiet.n_actions,
            "C6_bound_actions_per_1800s_poisson_p95": percentiles(
                [r["n_actions"] for r in per_seed]
            ).get("p95"),
            "C12_blind_fraction_during_continuous_flood": round(
                flood.blind_fraction, 4
            ),
            "C12_blind_fraction_poisson_p50": percentiles(
                [r["blind_fraction"] for r in per_seed]
            ).get("p50"),
            "C12_blind_fraction_when_normal": 0.0,
            "harm_fraction_vs_bangbang": {
                "circuit_breaker": round(flood.harm_fraction, 4),
                "bangbang": round(bangbang.harm_fraction, 4),
            },
            "max_open_s_must_stay_below": 120.0,
        },
        "upstream_sha256": {
            "controller/policy.py": sha256_of("controller/policy.py"),
            "controller/sim.py": sha256_of("controller/sim.py"),
            "controller/localize.py": sha256_of("controller/localize.py"),
            PREREG8: sha256_of(PREREG8),
            "models/detector-release-1.0.0.json": sha256_of(
                "models/detector-release-1.0.0.json"
            ),
        },
        "deviation_policy": "immutable after creation",
    }

    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(
                C.canonical_json(content).encode("utf-8")
            ),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    document = json.loads(OUT.read_text(encoding="utf-8"))
    print("[P8.2] content_sha256 =", document["content_sha256"])
    print("[P8.2] flood lien tuc 600 s :", flood.as_dict())
    print("[P8.2] bang-bang doi chung  :", bangbang.as_dict())
    print("[P8.2] binh thuong 600 s    :", quiet.as_dict())
    print("[P8.2] Poisson %d seed x %.0f s:" % (args.n_seeds, args.horizon))
    for key in ("n_actions", "harm_fraction", "blind_fraction", "max_open_s"):
        print("   %-15s %s" % (key, content["poisson"][key]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
