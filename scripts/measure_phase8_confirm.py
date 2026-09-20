#!/usr/bin/env python3
"""Do TRE XAC NHAN DU DUONG cua vong kin (tra no Lesson 8.3).

8.3 do 0.03-0.11 s bang cach doc thang link.dt4n_bw TRONG tien trinh Mininet -
do la tre ACTUATOR. Day do du duong ma controller that su thay:

    t_decide -> gui lenh -> agent thuc thi tc -> collector tick ke tiep
             -> PATCH Ditto -> SSE -> TwinReader.observed_bw() thay gia tri moi

Phan ra ky vong (tu receipt Phase 7):
    lenh                0.675 s p50 / 0.984 s p95   latency_command_randomized.json
    tc -> dt4n_bw       0.03-0.11 s                 phase8_s11_bw_*.json
    cho tick collector  0 -> 1.0 s (pha ngau nhien) TICK_INTERVAL_MS = 1000
    PATCH               0.009 / 0.011 s             phase7_e2e_latency.json
    SSE                 0.008 / 0.011 s             phase7_e2e_latency.json
    => ky vong ~1.2 s p50 / ~2.0 s p95

PHA NGAU NHIEN la bat buoc (giong 7.5/8.3): neu luon gui lenh o cung mot vi tri
trong chu ky 1 s cua collector thi thanh phan "cho tick" luon roi vao cung mot
cho va ta do ra mot phan bo GIA.

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/measure_phase8_confirm.py --n 25
"""
from __future__ import annotations

import argparse
import logging
import random
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402

from controller.locked_log import LockedInterventionLog  # noqa: E402
from controller.policy import Action, PolicyParams  # noqa: E402
from controller.runner import LEASE_TTL_S, ControlRunner  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing  # noqa: E402

OUT = C.ROOT / "results/report/phase8_confirm_latency.json"
LINK = "h1-s1"
LIMIT_MBPS = 7.0
DEFAULT_MBPS = 20.0
SETTLE_S = 6.0
CONFIRM_TIMEOUT_S = 10.0


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return {}

    def pick(q):
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]

    return {
        "n": len(ordered),
        "min_ms": round(ordered[0] * 1000, 3),
        "p50_ms": round(pick(0.50) * 1000, 3),
        "p95_ms": round(pick(0.95) * 1000, 3),
        "max_ms": round(ordered[-1] * 1000, 3),
        "mean_ms": round(statistics.fmean(ordered) * 1000, 3),
    }


def wait_confirm(twin, link, want, timeout_s=CONFIRM_TIMEOUT_S):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        have = twin.observed_bw().get(link)
        if have is not None and abs(have - want) <= 0.01:
            return time.monotonic()
        time.sleep(0.01)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=25)
    parser.add_argument("--seed", type=int, default=8004)
    args = parser.parse_args()
    if OUT.exists():
        print("[P8.4] da co receipt, khong ghi de:", OUT)
        return 1

    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    rows = []
    budget_s = args.n * 25 + 180

    with Live(budget_s) as live:
        runner_detector = live.start_detector()
        twin = TwinReader()
        stop = threading.Event()
        sse = threading.Thread(target=twin.run_forever, args=(stop,),
                               name="twin-sse", daemon=True)
        sse.start()
        live.wait_published("normal", timeout_s=120)

        control = ControlRunner(
            twin=twin,
            log_store=LockedInterventionLog(runner_detector.intervention_log),
            routing=Routing.load(C.ROOT / "ditto/routing_table.json"),
            send_command=live.env.send_command,
            params=PolicyParams(),
            audit_path=C.ROOT / "logs/phase8_confirm_audit.jsonl",
        )

        # cho SSE co du lieu bw truoc khi do
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline and LINK not in twin.observed_bw():
            time.sleep(0.2)

        try:
            for index in range(args.n):
                time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))   # PHA NGAU NHIEN
                iid = "ctl-confirm-%03d" % index
                inject = Action("inject", LINK, LIMIT_MBPS, iid + ":inject",
                                "confirm_probe")
                t_decide = time.monotonic()
                control._execute(inject, now_mono=t_decide)
                t_confirm = wait_confirm(twin, LINK, LIMIT_MBPS)

                revert = Action("revert", LINK, DEFAULT_MBPS, iid + ":revert",
                                "confirm_probe")
                t_decide_rev = time.monotonic()
                control._execute(revert, now_mono=t_decide_rev)
                t_confirm_rev = wait_confirm(twin, LINK, DEFAULT_MBPS)

                row = {
                    "i": index,
                    "confirm_inject_s": None if t_confirm is None else t_confirm - t_decide,
                    "confirm_revert_s": (None if t_confirm_rev is None
                                         else t_confirm_rev - t_decide_rev),
                    "twin_events": twin.events,
                    "twin_dropped": twin.dropped,
                    "twin_reconnects": twin.reconnects,
                }
                rows.append(row)
                print("[confirm %02d] inject=%.3fs revert=%s" % (
                    index,
                    row["confirm_inject_s"] or -1.0,
                    ("%.3fs" % row["confirm_revert_s"]) if row["confirm_revert_s"] else "TIMEOUT",
                ))
        finally:
            stop.set()

    injects = [r["confirm_inject_s"] for r in rows if r["confirm_inject_s"]]
    reverts = [r["confirm_revert_s"] for r in rows if r["confirm_revert_s"]]
    content = {
        "lesson": "8.4",
        "what": "tre xac nhan DU DUONG: t_decide -> observed_bw() thay gia tri moi",
        "not_what": ("tre actuator o 8.3 (0.03-0.11 s) chi do toi luc tc doi, "
                     "doc thang trong tien trinh Mininet"),
        "n_requested": args.n,
        "seed": args.seed,
        "phase_randomised": True,
        "link": LINK,
        "limit_mbps": LIMIT_MBPS,
        "lease_ttl_s": LEASE_TTL_S,
        "confirm_inject": percentiles(injects),
        "confirm_revert": percentiles(reverts),
        "n_timeout": sum(1 for r in rows
                         if r["confirm_inject_s"] is None or r["confirm_revert_s"] is None),
        "twin": {
            "events": rows[-1]["twin_events"] if rows else 0,
            "dropped": rows[-1]["twin_dropped"] if rows else 0,
            "reconnects": rows[-1]["twin_reconnects"] if rows else 0,
        },
        "c3_budget_ms": 10000,
        "log_counts": counter.counts,
        "rows": rows,
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print("wrote", OUT)
    print("confirm inject:", content["confirm_inject"])
    print("confirm revert:", content["confirm_revert"])
    print("timeouts:", content["n_timeout"], "| twin:", content["twin"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
