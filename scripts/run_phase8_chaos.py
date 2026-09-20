#!/usr/bin/env python3
"""Chaos engineering cho vong kin (Lesson 8.7).

Khac cot tu voi chaos o 7.6: o do he chi QUAN SAT, chet la mat du lieu roi chay
lai. O day he co ACTUATOR, nen chet de lai DAU VET VAT LY (bw = 7 tren h1-s1)
ma KHONG AI SO HUU. Day la noi dead-man switch va revert-first phai chung minh
chung that su hoat dong.

Ba nguyen tac: pha o PHA NGAU NHIEN; >= N luot moi dong; moi dong co mot nhanh
DOI CHUNG khong bi pha, chay xen ke.

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_chaos.py --rows c9,c9b,drift,second_flood --reps 5
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import subprocess
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
from controller.runner import LEASE_TTL_S  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.intervention_log import MAX_OPEN_S  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_chaos.json"
FLOOD_RATE_MBPS = 47
LINK = "h1-s1"
LIMIT_MBPS = 7.0
DEFAULT_MBPS = 20.0
EPS = 0.01


def wait_bw(twin, want, timeout_s, link=LINK):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        have = twin.observed_bw().get(link)
        if have is not None and abs(have - want) <= EPS:
            return time.monotonic()
        time.sleep(0.05)
    return None


def wait_mode(controller, modes, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if controller.cstate.mode in modes:
            return time.monotonic()
        time.sleep(0.05)
    return None


def wait_cause_not(twin, cause, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if twin.detector_view_fields().get("cause") != cause:
            return time.monotonic()
        time.sleep(0.1)
    return None


class Rig:
    """Mot vong kin song, dung chung cho moi dong chaos."""

    def __init__(self, live, twin, detector, audit_dir):
        self.live, self.twin, self.detector = live, twin, detector
        self.audit_dir = audit_dir
        self.controller = None
        self.thread = None
        self.flood = None
        self.index = 0

    def start_controller(self, tag):
        self.index += 1
        path = self.audit_dir / ("%s_%02d.jsonl" % (tag, self.index))
        self.controller = make_controller(self.twin, self.detector, path)
        self.controller.bootstrap_safe_state()
        self.thread = threading.Thread(target=self.controller.run_forever,
                                       name="control", daemon=True)
        self.thread.start()
        return self.controller

    def stop_controller(self, graceful=True):
        if self.controller is None:
            return
        if graceful:
            self.controller.shutdown()
        else:
            self.controller.stop()          # mo phong chet: KHONG go can thiep
        if self.thread:
            self.thread.join(10)
        self.controller, self.thread = None, None

    def start_flood(self, src="h1", dst="srv1"):
        flood = TrafficFlood(src, dst, FLOOD_RATE_MBPS)
        with self.live.env.net_lock:
            flood.apply(self.live.env.net)
        return flood

    def stop_flood(self, flood):
        if flood is not None:
            with self.live.env.net_lock:
                flood.revert(self.live.env.net)

    def cleanup(self):
        self.stop_controller(graceful=True)
        with self.live.env.net_lock:
            for host in ("h1", "h2"):
                TrafficFlood(host, "srv1", 1).revert(self.live.env.net)
        # dua bw ve mac dinh du controller da chet
        self.live.env.send_command(
            {"subject": "setBandwidth", "target": "org.dt4n:link-" + LINK,
             "params": {"bw": DEFAULT_MBPS}}, cid="chaos-cleanup-%d" % self.index)
        require_clean(self.live, self.twin, timeout_s=180.0)


# ---------------------------------------------------------------- cac dong


def row_c9(rig, rng, params):
    """Dong 1+2: kill controller dang MITIGATING -> C9 (lease go) + C9-b (mu thua)."""
    controller = rig.start_controller("c9")
    flood = rig.start_flood()
    try:
        t_mit = wait_mode(controller, ("MITIGATING",), 40)
        if t_mit is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        time.sleep(rng.uniform(0.0, params.t0_s * 0.6))      # PHA NGAU NHIEN
        t_kill = time.monotonic()
        rig.stop_controller(graceful=False)                  # mo phong kill -9
        t_restored = wait_bw(rig.twin, DEFAULT_MBPS, LEASE_TTL_S + 25)
        t_unsup = wait_cause_not(rig.twin, "suppressed_intervention",
                                 MAX_OPEN_S + 40)
        return {
            "t_physical_safe_s": None if t_restored is None else round(t_restored - t_kill, 2),
            "t_sensor_restored_s": None if t_unsup is None else round(t_unsup - t_kill, 2),
            "excess_blind_window_s": (None if (t_restored is None or t_unsup is None)
                                      else round(t_unsup - t_restored, 2)),
            "lease_ttl_s": LEASE_TTL_S, "max_open_s": MAX_OPEN_S,
        }
    finally:
        rig.stop_flood(flood)


def row_drift(rig, rng, params):
    """Dong 7: mot TAC NHAN KHAC ghi de bw trong luc dang MITIGATING."""
    controller = rig.start_controller("drift")
    flood = rig.start_flood()
    try:
        if wait_mode(controller, ("MITIGATING",), 40) is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        time.sleep(rng.uniform(0.0, 3.0))
        before = controller.stats["drift_fixes"]
        t_inject = time.monotonic()
        rig.live.env.send_command(                       # NGOAI LUONG
            {"subject": "setBandwidth", "target": "org.dt4n:link-" + LINK,
             "params": {"bw": 12.0}}, cid="chaos-drift-%d" % rig.index)
        wait_bw(rig.twin, 12.0, 10)
        t_back = wait_bw(rig.twin, LIMIT_MBPS, 30)
        time.sleep(2.0)
        return {
            "t_recover_s": None if t_back is None else round(t_back - t_inject, 2),
            "drift_fixes_delta": controller.stats["drift_fixes"] - before,
            "mode_after": controller.cstate.mode,
        }
    finally:
        rig.stop_flood(flood)


def row_second_flood(rig, rng, params):
    """Dong 8: flood THU HAI tu h2 -> srv2 trong luc dang giam thieu h1.

    Duong di h2 -> s1 -> s3 -> srv2 KHAC duong cua h1, nhung TOAN BO nam trong
    vung uc che cua can thiep tren h1-s1 (15/16 entity) -> du doan: bi che.
    """
    controller = rig.start_controller("second")
    flood1 = rig.start_flood("h1", "srv1")
    flood2 = None
    try:
        if wait_mode(controller, ("MITIGATING",), 40) is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        time.sleep(rng.uniform(0.0, params.t0_s * 0.5))
        t_second = time.monotonic()
        flood2 = rig.start_flood("h2", "srv2")
        # "phat hien" = detector cong bo act VA h2 nam trong affected
        deadline = time.monotonic() + MAX_OPEN_S + 30
        t_detected = None
        while time.monotonic() < deadline:
            fields = rig.twin.detector_view_fields()
            if fields["state"] == "act" and any("host-h2" in a
                                                for a in fields["affected"]):
                t_detected = time.monotonic()
                break
            time.sleep(0.2)
        return {
            "t_masked_s": None if t_detected is None else round(t_detected - t_second, 2),
            "detected": t_detected is not None,
            "mode_at_second_flood": controller.cstate.mode,
        }
    finally:
        rig.stop_flood(flood2)
        rig.stop_flood(flood1)


def row_restart(rig, rng, params):
    """Dong 5: restart controller dang MITIGATING -> revert-first, 0 ValueError."""
    controller = rig.start_controller("restart")
    flood = rig.start_flood()
    try:
        if wait_mode(controller, ("MITIGATING",), 40) is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        time.sleep(rng.uniform(0.0, 5.0))
        rig.stop_controller(graceful=False)              # chet, de lai bw = 7
        rig.stop_flood(flood)
        flood = None
        time.sleep(2.0)
        t_boot = time.monotonic()
        new_controller = rig.start_controller("restart2")
        t_clean = wait_bw(rig.twin, DEFAULT_MBPS, 30)
        time.sleep(2.0)
        return {
            "orphans_reverted": new_controller.stats["orphans_reverted"],
            "t_revert_first_s": None if t_clean is None else round(t_clean - t_boot, 2),
            "exceptions": new_controller.stats["exceptions"],
            "mode": new_controller.cstate.mode,
        }
    finally:
        rig.stop_flood(flood)


def row_agent_kill(rig, rng, params):
    """Dong 9 (moi): giet command_agent dang MITIGATING.

    Lease song trong `_leases` - mot dict TRONG BO NHO cua agent. Agent chet ->
    lease chet theo -> watchdog khong biet gi de phuc hoi. Day la MAT XICH HO
    cua chuoi phong thu. Do xem vong reconcile cua controller co tu lanh khong.
    """
    controller = rig.start_controller("agentkill")
    flood = rig.start_flood()
    try:
        if wait_mode(controller, ("MITIGATING",), 40) is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        before = controller.stats["commands"]
        # agent chay trong CUNG tien trinh (EnvRunner) nen khong kill -9 duoc;
        # mo phong dung nhat co the: xoa cache lease + dedup cua agent.
        import bridge.command_agent as agent

        with agent._lease_lock:
            n_leases = len(agent._leases)
            agent._leases.clear()
        with agent._processed_lock:
            agent._processed_ids.clear()
        t_clear = time.monotonic()
        time.sleep(LEASE_TTL_S + 5.0)
        have = rig.twin.observed_bw().get(LINK)
        return {
            "n_leases_cleared": n_leases,
            "bw_after_lease_ttl": have,
            "still_limited": have is not None and abs(have - LIMIT_MBPS) <= EPS,
            "commands_since": controller.stats["commands"] - before,
            "t_observed_s": round(time.monotonic() - t_clear, 1),
        }
    finally:
        rig.stop_flood(flood)


def row_control(rig, rng, params):
    """Nhanh DOI CHUNG: y het cac dong tren nhung KHONG pha gi."""
    controller = rig.start_controller("control")
    flood = rig.start_flood()
    try:
        if wait_mode(controller, ("MITIGATING",), 40) is None:
            return {"aborted": "khong vao duoc MITIGATING"}
        wait_bw(rig.twin, LIMIT_MBPS, 15)
        time.sleep(30.0)
        return {"mode": controller.cstate.mode,
                "exceptions": controller.stats["exceptions"],
                "commands": controller.stats["commands"],
                "bw": rig.twin.observed_bw().get(LINK)}
    finally:
        rig.stop_flood(flood)


ROWS = {
    "c9": row_c9, "drift": row_drift, "second_flood": row_second_flood,
    "restart": row_restart, "agent_kill": row_agent_kill, "control": row_control,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default="control,c9,drift,second_flood,restart,agent_kill")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    names = [n for n in args.rows.split(",") if n.strip()]
    assert set(names) <= set(ROWS), names
    out = OUT if not args.tag else OUT.with_name("phase8_chaos_%s.json" % args.tag)
    if out.exists():
        print("[8.7-chaos] da co receipt, khong ghi de:", out)
        return 1
    health_before = infra_check(raise_on_fail=True)

    rng = random.Random(args.seed)
    params = PolicyParams()
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ("logs/phase8_chaos/%s"
                          % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    audit_dir.mkdir(parents=True, exist_ok=True)

    budget_s = int(len(names) * args.reps * 240 + 600)
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
        while time.monotonic() < deadline and LINK not in twin.observed_bw():
            time.sleep(0.2)
        sampler = TwinSampler(twin).start()
        rig = Rig(live, twin, detector, audit_dir)
        try:
            for rep in range(args.reps):
                for name in names:
                    rig.cleanup()
                    health = infra_check(raise_on_fail=False)
                    if not health["healthy"]:
                        results.append({"row": name, "rep": rep, "invalid_infra": health})
                        print("   [%s rep%d] VO HIEU do ha tang: %s" % (name, rep, health))
                        continue
                    started = time.time()
                    try:
                        payload = ROWS[name](rig, rng, params)
                    except Exception as exc:               # noqa: BLE001
                        payload = {"error": repr(exc)}
                    finally:
                        rig.cleanup()
                    results.append({"row": name, "rep": rep, "t_start": started,
                                    "result": payload})
                    print("   [%s rep%d] %s" % (name, rep, json.dumps(payload,
                                                                     ensure_ascii=False)))
        finally:
            sampler.stop()
            stop_sse.set()

    def rows_of(name):
        return [r["result"] for r in results
                if r.get("row") == name and "result" in r and "error" not in r["result"]
                and "aborted" not in r["result"]]

    content = {
        "lesson": "8.7", "experiment": "chaos duoi vong kin",
        "seed": args.seed, "reps": args.reps, "rows": names,
        "lease_ttl_s": LEASE_TTL_S, "max_open_s": MAX_OPEN_S,
        "health_before": health_before,
        "n_invalid_infra": sum(1 for r in results if "invalid_infra" in r),
        "results": results,
        "summary": {name: rows_of(name) for name in names},
        "log_counts": counter.counts,
    }
    C.atomic_json(out, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
