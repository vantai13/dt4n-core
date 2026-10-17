#!/usr/bin/env python3
"""Khoi dong VONG KIN Phase 8 day du: 4 luong, tat em, dead-man switch.

    collector ──mailbox──> detector-writer ──PATCH──> Ditto
                                                        │ SSE
                                                   twin-sse
                                                        │ cache
                                                     CONTROL

Chay (can Mininet + Ditto + Ryu):
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_loop.py --duration 600 [--flood]

SIGTERM / Ctrl-C -> tat em: go can thiep dang mo, cong bo HOLD, roi thoat.
Khong dua vao dead-man switch o duong thoat binh thuong.
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_live_common import LevelCounter, Live  # noqa: E402

from bridge.controlloop_contract import CONTROLLOOP_THING_ID  # noqa: E402
from bridge.detector_runner import DittoTransport  # noqa: E402
from controller.locked_log import LockedInterventionLog  # noqa: E402
from controller.policy import PolicyParams  # noqa: E402
from controller.runner import ControlRunner  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_loop_run.json"
FLOOD_RATE_MBPS = 47


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--flood", action="store_true",
                        help="bat flood h1->srv1 sau 30 s de vong kin co viec lam")
    parser.add_argument("--flood-at", type=float, default=30.0)
    parser.add_argument("--flood-stop", type=float, default=None)
    parser.add_argument("--tag", default="")
    parser.add_argument("--debug-every", type=float, default=0.0,
                        help="in view cua controller va published cua detector moi N giay")
    args = parser.parse_args()

    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    transport = DittoTransport()
    stop_sse = threading.Event()

    with Live(int(args.duration) + 120) as live:
        detector = live.start_detector()
        twin = TwinReader()
        sse = threading.Thread(target=twin.run_forever, args=(stop_sse,),
                               name="twin-sse", daemon=True)
        sse.start()
        live.wait_published("normal", timeout_s=120)

        control = ControlRunner(
            twin=twin,
            # Diem giao DUY NHAT giua khoang collector va khoang control.
            log_store=LockedInterventionLog(detector.intervention_log),
            routing=Routing.load(C.ROOT / "ditto/routing_table.json"),
            send_command=live.env.send_command,
            publish=lambda body: transport(CONTROLLOOP_THING_ID, body),
            params=PolicyParams(),
            audit_path=C.ROOT / "logs/controller_audit.jsonl",
        )

        control_thread = threading.Thread(target=control.run_forever,
                                          name="control", daemon=True)

        def on_signal(signum, _frame):
            logging.getLogger("loop").warning("nhan tin hieu %s -> tat em", signum)
            control.shutdown()
            stop_sse.set()

        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)

        control_thread.start()
        flood = None
        started = time.monotonic()
        try:
            while time.monotonic() - started < args.duration:
                elapsed = time.monotonic() - started
                if args.flood and flood is None and elapsed >= args.flood_at:
                    flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
                    with live.env.net_lock:
                        flood.apply(live.env.net)
                    print("[loop] flood ON tai t=%.0f s" % elapsed)
                if (flood is not None and args.flood_stop
                        and elapsed >= args.flood_stop):
                    with live.env.net_lock:
                        flood.revert(live.env.net)
                    flood = None
                    args.flood = False
                    print("[loop] flood OFF tai t=%.0f s" % elapsed)
                if args.debug_every and int(elapsed) % int(args.debug_every) == 0:
                    view = control.build_view()
                    last = list(detector.timeline)[-1:] or [{}]
                    print("[dbg t=%3.0f] view state=%s cause=%s fresh=%s aff=%s "
                          "| detector published=%s cause=%s | mode=%s bw=%s"
                          % (elapsed, view.state, view.cause, view.fresh,
                             list(view.affected)[:3], last[0].get("published"),
                             last[0].get("cause"), control.cstate.mode,
                             twin.observed_bw().get("h1-s1")))
                time.sleep(1.0)
        finally:
            if flood is not None:
                with live.env.net_lock:
                    flood.revert(live.env.net)
            control.shutdown()          # tat em: go can thiep truoc khi thoat
            stop_sse.set()
            control_thread.join(10)

        content = {
            "lesson": "8.4",
            "duration_s": args.duration,
            "flood": bool(args.flood or args.flood_at is not None),
            "controller_stats": control.stats,
            "controller_final": {
                "mode": control.cstate.mode,
                "reason": control.cstate.reason,
                "episode": control.cstate.episode,
                "attempt": control.cstate.attempt,
            },
            "twin": {"events": twin.events, "dropped": twin.dropped,
                     "reconnects": twin.reconnects},
            "detector": {
                "ticks": getattr(detector, "seq", None),
                "dropped": getattr(detector, "dropped", None),
            },
            "intervention_log_len": len(control.log),
            "audit_path": str(control.audit.path),
            "log_counts": counter.counts,
        }

    out = OUT if not args.tag else OUT.with_name("phase8_loop_run_%s.json" % args.tag)
    C.atomic_json(
        out,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print("wrote", out)
    print(json.dumps(content["controller_stats"], indent=1))
    print("final:", content["controller_final"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
