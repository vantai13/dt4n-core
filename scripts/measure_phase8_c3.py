#!/usr/bin/env python3
"""Do C3 TRUC TIEP: `act` cong bo -> thu pham that su bi gioi han (Lesson 8.6).

KHONG cong p95 cua cac tang lai: p95 cua TONG != tong cac p95 khi cac tang
khong doc lap (bay da xu ly o 7.5, measurements/e2e_budget.py).

Moc bat dau la `act` CONG BO tren twin - dung dinh nghia da niem phong o prereg
8.1 ("tre act -> thu pham bi gioi han"), KHONG phai luc flood bat dau.

PHA NGAU NHIEN bat buoc: tang "cho nhip control tick" la 0-1000 ms phan phoi
deu va CHIEM UU THE; khong ngau nhien hoa thi do ra mot hang so chu khong phai
mot phan phoi.

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/measure_phase8_c3.py --n 12
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
from phase8_ab_common import (  # noqa: E402
    FLOOD_RATE_MBPS, bind_send, make_controller, require_clean,
)

from controller.twin_reader import TwinReader  # noqa: E402
from ml import campaign as C  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_c3.json"
LIMIT_MBPS = 7.0
LINK = "h1-s1"
C3_BUDGET_MS = 10000.0


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return {}

    def pick(q):
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]

    return {"n": len(ordered), "min_ms": round(ordered[0], 2),
            "p50_ms": round(pick(0.50), 2), "p95_ms": round(pick(0.95), 2),
            "max_ms": round(ordered[-1], 2),
            "mean_ms": round(statistics.fmean(ordered), 2)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260920)
    args = parser.parse_args()
    if OUT.exists():
        print("[C3] da co receipt, khong ghi de:", OUT)
        return 1

    rng = random.Random(args.seed)
    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    rows = []
    with Live(args.n * 90 + 300) as live:
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

        controller = make_controller(twin, detector,
                                     C.ROOT / "logs/phase8_c3_audit.jsonl")
        controller.bootstrap_safe_state()
        threading.Thread(target=controller.run_forever, name="control",
                         daemon=True).start()
        try:
            for index in range(args.n):
                # Cho DAI hon: sau khi flood tat, controller VAN giu gioi han
                # theo LICH (toi T_max = 110 s) - dung thiet ke, khong phai loi.
                # Lan do dau tien co 3/12 luot bi huy vi cho khong du.
                ok, detail = require_clean(live, twin, timeout_s=180.0)
                if not ok:
                    rows.append({"i": index, "aborted": True, "detail": detail})
                    continue
                time.sleep(5.0 + rng.uniform(0.0, 1.0))      # PHA NGAU NHIEN
                flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
                with live.env.net_lock:
                    flood.apply(live.env.net)

                t_act = None
                t_limited = None
                deadline_probe = time.monotonic() + 30.0
                while time.monotonic() < deadline_probe:
                    fields = twin.detector_view_fields()
                    if t_act is None and fields["state"] == "act":
                        t_act = time.monotonic()
                    if t_act is not None:
                        have = twin.observed_bw().get(LINK)
                        if have is not None and abs(have - LIMIT_MBPS) <= 0.01:
                            t_limited = time.monotonic()
                            break
                    time.sleep(0.02)
                with live.env.net_lock:
                    flood.revert(live.env.net)
                time.sleep(20.0)        # nhip nghi toi thieu; require_clean lo phan con lai

                rows.append({
                    "i": index, "aborted": False,
                    "c3_ms": None if (t_act is None or t_limited is None)
                             else (t_limited - t_act) * 1000.0,
                    "saw_act": t_act is not None,
                })
                print("[C3 %02d] %s ms" % (index, rows[-1]["c3_ms"]))
        finally:
            controller.shutdown()
            stop_sse.set()

    values = [r["c3_ms"] for r in rows if not r.get("aborted") and r.get("c3_ms")]
    summary = percentiles(values)
    content = {
        "lesson": "8.6",
        "metric": "C3",
        "definition": ("act CONG BO tren twin -> capacity.bwMbps cua link truy "
                       "nhap thu pham = 7.0 (xac nhan bang trang thai quan sat "
                       "duoc, khong bang ma 202)"),
        "anchor_note": ("moc bat dau la `act`, KHONG phai luc flood bat dau: tre "
                        "phat hien (~3.4 s) thuoc S-rows Phase 7, nam NGOAI C3"),
        "measured_directly": True,
        "phase_randomised": True,
        "budget_ms": C3_BUDGET_MS,
        "summary": summary,
        "c3_pass": bool(summary and summary["p95_ms"] <= C3_BUDGET_MS),
        "n_aborted": sum(1 for r in rows if r.get("aborted")),
        "log_counts": counter.counts,
        "rows": rows,
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", OUT)
    print("C3:", summary, "-> ", "PASS" if content["c3_pass"] else "FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
