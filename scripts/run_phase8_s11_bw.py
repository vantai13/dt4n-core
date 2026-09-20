#!/usr/bin/env python3
"""S11 cho actuator MOI (setBandwidth) - gate C8 cua Phase 8.3.

S11: hanh dong cua controller KHONG duoc lam detector tu bao dong. Neu no bao
dong -> controller thay `act` -> hanh dong tiep -> vong phan hoi DUONG (leo
thang), nguy hiem hon dao dong.

Ba nhanh (giu nguyen khuon 7.6):
  log_first : ghi InterventionLog -> gui lenh          nhanh DUNG        -> ky vong 0 act
  log_late  : gui lenh -> doi hau qua -> moi ghi log   doi chung AM      -> ky vong >=1 alarm
  no_log    : gui lenh, KHONG ghi log                  doi chung DUONG   -> ky vong >=1 act

Hai kich ban:
  quiet : tai nen 2 Mbps, bop xuong 1 Mbps (DUOI tai -> chac chan sinh drop).
          Day la gate C8. 1 Mbps la tham so cua PHEP DO, khong phai cua policy.
  flood : flood UDP 47 Mbps dang chay, bop xuong 7.0 (dung tham so that).
          Dung de DONG AN SO 9.3, KHONG dung lam gate vi da co act do flood.

Chay (can Mininet + Ditto + Ryu):
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_s11_bw.py --scenario quiet --reps 5
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402

from controller.intervene import to_command, to_intervention  # noqa: E402
from measurements.stability import window_counts  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing  # noqa: E402
from ml.intervention_log import MAX_OPEN_S  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_s11_bw.json"
CONTRACT = C.ROOT / "results/report/phase8_contract.json"

COOLDOWN_S = 8.0          # detector-release-1.0.0.json::fsm_params
TAIL_S = 10.0             # giong 7.6
HOLD_S = 20.0             # << MAX_OPEN_S 120 s: khong duoc cham lease
SETTLE_S = 5.0
DEFAULT_BW = 20.0         # mininet/topology.py:88
QUIET_BW = 1.0            # DUOI tai nen 2 Mbps -> chac chan sinh drop
FLOOD_BW = 7.0            # dung tham so that cua policy
FLOOD_RATE_MBPS = 47      # giong F-flood-* cua Phase 5
LINK = "h1-s1"
MODES = ("log_first", "log_late", "no_log")
TICK_KEYS = ("seq", "t_source", "fsm", "published", "cause",
             "envelope", "conservation", "act_rule")


@dataclass(frozen=True)
class FakeAction:
    """Action toi thieu de tai dung controller/intervene.py that.

    KHONG goi decide() o day: phep do nay do ACTUATOR, khong do policy. Nhung
    duong bien Action -> Intervention -> command PHAI la duong that, neu khong
    thi ta dang do mot he khac voi he se chay o 8.4.
    """

    kind: str
    link: str
    bw_mbps: float
    intervention_id: str
    reason: str


class RateLimitController:
    """Ban sao cua LiveController (7.6) nhung dung actuator setBandwidth."""

    def __init__(self, intervention_log, send_command, runner, clock=time.time):
        self.log = intervention_log
        self.send_command = send_command
        self.runner = runner
        self.routing = Routing.load(C.ROOT / "ditto/routing_table.json")
        self.clock = clock

    def _wait_consequence(self, after_seq, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for entry in list(self.runner.timeline):
                if entry["seq"] >= after_seq and (
                    entry["envelope"] or entry["conservation"] or entry["act_rule"]
                ):
                    return entry
            time.sleep(0.05)
        return None

    def act(self, kind, pair, mode, bw, late_timeout_s=10.0):
        if mode not in MODES:
            raise ValueError(mode)
        action = FakeAction(
            kind=kind,
            link=LINK,
            bw_mbps=bw if kind == "inject" else DEFAULT_BW,
            intervention_id="%s:%s" % (pair, kind),
            reason="s11_probe",
        )
        record = {"pair": pair, "kind": kind, "link": LINK, "mode": mode,
                  "bw_mbps": action.bw_mbps}
        t_decide = self.clock()
        seq_before = self.runner.seq
        if mode == "log_first":                       # M5: write-ahead
            self.log.append(to_intervention(action, self.routing, t_decide))
            record["t_log_wall"] = self.clock()
        record["t_post_wall"] = self.clock()
        command = to_command(action)
        record["command"] = command
        record["post"] = self.send_command(command)
        if mode == "log_late":
            hit = self._wait_consequence(seq_before, late_timeout_s)
            record["late_after_seq"] = hit["seq"] if hit else None
            self.log.append(to_intervention(action, self.routing, t_decide))
            record["t_log_wall"] = self.clock()
        record["t_decide_wall"] = t_decide
        return record


def observed_bw(live, link_key=LINK):
    """Xac nhan hieu luc qua capacity.bwMbps, KHONG qua ma 202."""
    with live.env.net_lock:
        for link in live.env.net.links:
            names = {link.intf1.node.name, link.intf2.node.name}
            if names == set(link_key.split("-", 1)):
                return getattr(link, "dt4n_bw", None)
    return None


def one_round(live, controller, mode, rng, bw):
    started_normal = live.wait_published("normal")
    time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))     # pha ngau nhien (7.5)
    pair = "s11bw-%s-%d" % (mode, rng.randrange(10**6))
    bw_before = observed_bw(live)
    inject = controller.act("inject", pair, mode, bw)
    t_effect, waited = None, 0.0
    while waited < 5.0:
        if observed_bw(live) == bw:
            t_effect = time.time()
            break
        time.sleep(0.1)
        waited += 0.1
    time.sleep(max(0.0, HOLD_S - waited))
    revert_mode = "no_log" if mode == "no_log" else "log_first"
    revert = controller.act("revert", pair, revert_mode, bw)
    time.sleep(COOLDOWN_S + TAIL_S + 1.0)

    t0 = inject["t_decide_wall"]
    t1 = revert["t_decide_wall"] + COOLDOWN_S + TAIL_S
    ticks = [
        {key: entry.get(key) for key in TICK_KEYS}
        for entry in live.runner.timeline
        if entry["t_source"] is not None and t0 <= entry["t_source"] < t1
    ]
    in_hold = [t for t in ticks if t["t_source"] < revert["t_decide_wall"]]
    published = {}
    for tick in in_hold:
        key = tick["published"] + ("/" + tick["cause"] if tick["cause"] else "")
        published[key] = published.get(key, 0) + 1
    return {
        "mode": mode,
        "pair": pair,
        "bw_mbps": bw,
        "bw_before": bw_before,
        "bw_after_revert": observed_bw(live),
        "started_from_normal": started_normal,
        "effect_latency_s": (t_effect - inject["t_post_wall"]) if t_effect else None,
        "inject": inject,
        "revert": revert,
        "window_wall": [t0, t1],
        "counts": window_counts(list(live.runner.timeline), t0, t1),
        "published_during_mitigation": published,
        "first_tick_after_inject": next(
            ({"published": t["published"], "cause": t["cause"]}
             for t in ticks if t["t_source"] > inject["t_post_wall"]), None
        ),
        "ticks": ticks,
    }


def seal(path, content):
    C.atomic_json(
        path,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("quiet", "flood"), required=True)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--seed", type=int, default=8003)
    parser.add_argument("--arms", default="log_first,log_late,no_log")
    args = parser.parse_args()
    arms = args.arms.split(",")
    assert set(arms) <= set(MODES), arms
    if not CONTRACT.exists():
        print("hop dong 8.3 chua niem phong; chay build_phase8_contract.py truoc")
        return 2

    bw = QUIET_BW if args.scenario == "quiet" else FLOOD_BW
    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    rows = []
    budget_s = args.reps * len(arms) * 70 + 240
    with Live(budget_s) as live:
        runner = live.start_detector()
        controller = RateLimitController(
            runner.intervention_log, live.env.send_command, runner
        )
        live.wait_published("normal", timeout_s=120)
        flood = None
        if args.scenario == "flood":
            flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
            with live.env.net_lock:
                flood.apply(live.env.net)
            time.sleep(10.0)      # de flood on dinh va detector vao act
        try:
            for rep in range(args.reps):
                order = list(arms)
                rng.shuffle(order)
                for mode in order:
                    row = one_round(live, controller, mode, rng, bw)
                    row["rep"] = rep
                    rows.append(row)
                    print("[%s/%s rep%d] act_entries=%d alarm_entries=%d "
                          "published=%s effect=%.2fs"
                          % (args.scenario, mode, rep,
                             row["counts"].get("act_entries", 0),
                             row["counts"].get("alarm_entries", 0),
                             row["published_during_mitigation"],
                             row["effect_latency_s"] or -1.0))
        finally:
            if flood is not None:
                with live.env.net_lock:
                    flood.revert(live.env.net)

    by_arm = {}
    for mode in arms:
        subset = [r for r in rows if r["mode"] == mode]
        merged = {}
        for row in subset:
            for key, value in row["published_during_mitigation"].items():
                merged[key] = merged.get(key, 0) + value
        by_arm[mode] = {
            "n": len(subset),
            "act_entries": sum(r["counts"].get("act_entries", 0) for r in subset),
            "alarm_entries": sum(r["counts"].get("alarm_entries", 0) for r in subset),
            "ticks": sum(r["counts"].get("ticks", 0) for r in subset),
            "all_started_from_normal": all(r["started_from_normal"] for r in subset),
            "published_during_mitigation": merged,
            "effect_latency_s": [r["effect_latency_s"] for r in subset],
            "first_tick_after_inject": [r["first_tick_after_inject"] for r in subset],
        }

    valid = args.scenario != "quiet" or by_arm.get("no_log", {}).get("act_entries", 0) >= 1
    content = {
        "lesson": "8.3",
        "scenario": args.scenario,
        "actuator": "setBandwidth",
        "link": LINK,
        "bw_mbps": bw,
        "hold_s": HOLD_S,
        "cooldown_s": COOLDOWN_S,
        "tail_s": TAIL_S,
        "lease_max_open_s": MAX_OPEN_S,
        "lease_touched": any(r["counts"].get("ticks", 0) and
                             r["revert"]["t_decide_wall"] - r["inject"]["t_decide_wall"]
                             >= MAX_OPEN_S for r in rows),
        "seed": args.seed,
        "contract_sha256": C.sha256_bytes(CONTRACT.read_bytes()),
        "arms": by_arm,
        "measurement_valid": bool(valid),
        "c8_verdict": (
            "PASS" if (args.scenario == "quiet" and valid
                       and by_arm.get("log_first", {}).get("act_entries", 1) == 0)
            else ("N/A (khong dung lam gate)" if args.scenario == "flood" else "FAIL")
        ),
        "log_counts": counter.counts,
        "rows": rows,
    }
    out = OUT.with_name("phase8_s11_bw_%s.json" % args.scenario)
    seal(out, content)
    print("wrote", out)
    print("arms:", {k: {kk: vv for kk, vv in v.items()
                        if kk in ("n", "act_entries", "alarm_entries",
                                  "published_during_mitigation")}
                    for k, v in by_arm.items()})
    print("measurement_valid =", valid, "| C8 =", content["c8_verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
