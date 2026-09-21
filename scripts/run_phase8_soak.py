#!/usr/bin/env python3
"""C11 - soak 30 phut cua vong kin (no tu 8.7, tra o 8.8).

Soak khong phai "chay lau cho chac". No la phep do DUY NHAT bat duoc bon loai
loi ma moi phep do ngan deu mu:
  1. ro ri bo nho   -> RSS tang deu (do do doc theo chuoi, khong chi dau/cuoi)
  2. ro ri luong    -> so thread tang moi episode
  3. ro ri so sach  -> InterventionLog dai vo han
  4. xoay vong audit lam GAY chuoi hash -> C10 mat sach bang chung

Muc 4 la ly do soak nay ep xoay vong: max_rows nho de chac chan file bi xoay
vai lan trong 1800 s. Neu chuoi dut o cho noi file, ta muon biet BAY GIO chu
khong phai luc nghiem thu.

Tai: nhip flood ngan lap lai - du de vong kin lam viec that (co inject/revert,
co episode, co reconcile), khong phai flood lien tuc (do la viec cua C6).

Chay:
  sudo -n -E env PYTHONPATH=$PWD .venv/bin/python -u \
      scripts/run_phase8_soak.py --production --warmup-s 300 --duration 1800
"""
from __future__ import annotations

import argparse
import json
import logging
import os
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

from controller.audit import _rotation_order, read_rows, verify_chain  # noqa: E402
from controller.twin_reader import TwinReader  # noqa: E402
from measurements import blind_time, degraded, stability  # noqa: E402
from ml import campaign as C  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

OUT = C.ROOT / "results/report/phase8_soak.json"
FLOOD_RATE_MBPS = 47
# Nhip lam viec: 60 s flood / 240 s nghi = duty cycle 20%. Chon TRUOC khi chay,
# khong phai sau khi nhin so. Ly do: du dai de vong kin di het T0->2T0 it nhat
# mot lan moi chu ky, du thua de detector ve normal han giua hai chu ky.
FLOOD_ON_S = 60.0
FLOOD_PERIOD_S = 300.0
# Ep xoay vong: ~1800 tick decision trong 1800 s, max_rows 500 -> >= 3 lan xoay.
AUDIT_MAX_ROWS = 500
RSS_SAMPLE_S = 10.0
# Nguong C11, khoa TRUOC (cung tinh than voi C11 cua Phase 6R/7).
C11_MAX_DELTA_MIB = 1.0
C11_MAX_THREAD_GROWTH = 0
DEFAULT_WARMUP_S = 300.0


def measurement_window(series: list, warmup_s: float, duration_s: float) -> list:
    """Return the preregistered steady-state C11 window.

    Phase 7 S6 v2 defines the measured quantity as RSS growth after excluding
    a 300 s lazy-initialisation transient.  Keeping this selection in one pure
    helper makes it testable and prevents a future harness from silently
    reverting to the old [0, 30 min] protocol.
    """
    end_s = warmup_s + duration_s
    return [(t, value) for t, value in series if warmup_s <= t <= end_s]


def rss_kib() -> int:
    with open("/proc/self/status", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=1800.0)
    parser.add_argument("--warmup-s", type=float, default=DEFAULT_WARMUP_S)
    parser.add_argument("--tag", default="")
    # Phase 7 dang ky giao thuc soak o CAU HINH PRODUCTION: timeline TAT, khong
    # co sampler (scripts/soak_phase7_live_v2.py:60). Hai bo dem do la DUNG CU
    # DO, khong phai he: timeline deque 4096 phan tu van dang day trong 1800 s,
    # va sampler tich luy ~1 dong/tick/host khong gioi han. Do RSS tren cau
    # hinh co do dac roi so voi nguong cua cau hinh production la so nham thuoc.
    parser.add_argument("--production", action="store_true",
                        help="timeline TAT + khong sampler: so duoc voi Phase 7")
    args = parser.parse_args()

    out = OUT if not args.tag else OUT.with_name("phase8_soak_%s.json" % args.tag)
    if out.exists():
        print("[8.8/soak] da co receipt, khong ghi de:", out)
        return 1
    health_before = infra_check(raise_on_fail=True)

    counter = LevelCounter()
    logging.getLogger().addHandler(counter)
    audit_dir = C.ROOT / ("logs/phase8_soak/%s"
                          % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "soak.jsonl"

    rss_series, thread_series, log_len_series = [], [], []
    stop_probe = threading.Event()

    def probe():
        t0 = time.monotonic()
        while not stop_probe.wait(RSS_SAMPLE_S):
            rss_series.append((round(time.monotonic() - t0, 1), rss_kib()))
            thread_series.append(threading.active_count())

    spans_plan = []
    total_s = args.warmup_s + args.duration
    with Live(int(total_s + 420)) as live:
        detector = live.start_detector(
            timeline_samples=0 if args.production else 4096)
        twin = TwinReader()
        stop_sse = threading.Event()
        threading.Thread(target=twin.run_forever, args=(stop_sse,),
                         name="twin-sse", daemon=True).start()
        bind_send(live.env.send_command)
        live.wait_published("normal", timeout_s=120)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and "h1-s1" not in twin.observed_bw():
            time.sleep(0.2)
        sampler = None if args.production else TwinSampler(twin).start()
        require_clean(live, twin, timeout_s=180.0)

        controller = make_controller(twin, detector, audit_path)
        controller.audit.max_rows = AUDIT_MAX_ROWS     # ep xoay vong
        controller.bootstrap_safe_state()
        thread = threading.Thread(target=controller.run_forever, name="control",
                                  daemon=True)
        thread.start()
        threading.Thread(target=probe, name="rss-probe", daemon=True).start()

        t0 = time.time()
        mono0 = time.monotonic()
        try:
            while time.monotonic() - mono0 < total_s:
                cycle_start = time.monotonic() - mono0
                flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
                with live.env.net_lock:
                    flood.apply(live.env.net)
                time.sleep(min(FLOOD_ON_S, total_s - cycle_start))
                with live.env.net_lock:
                    flood.revert(live.env.net)
                spans_plan.append((cycle_start,
                                   min(cycle_start + FLOOD_ON_S, total_s)))
                rest = FLOOD_PERIOD_S - FLOOD_ON_S
                remaining = total_s - (time.monotonic() - mono0)
                if remaining <= 0:
                    break
                time.sleep(min(rest, remaining))
                print("[8.8/soak] t=%.0fs rss=%d KiB threads=%d ticks=%d cmds=%d "
                      "exc=%d" % (time.monotonic() - mono0, rss_kib(),
                                  threading.active_count(),
                                  controller.stats["ticks"],
                                  controller.stats["commands"],
                                  controller.stats["exceptions"]), flush=True)
                log_len_series.append(len(detector.intervention_log))
        finally:
            stop_probe.set()
            controller.shutdown()
            thread.join(10)
        t1 = time.time()
        ticks = ([] if sampler is None
                 else [r for r in sampler.rows if t0 <= r["t_wall"] < t1])
        if sampler is not None:
            sampler.stop()
        stop_sse.set()
        timeline = list(detector.timeline)

    (audit_dir / "ticks.json").write_text(json.dumps(ticks), encoding="utf-8")
    (audit_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    spans_wall = [(t0 + lo, t0 + hi) for lo, hi in spans_plan]
    chain = verify_chain(audit_path)
    rotated = sorted(p.name for p in audit_dir.glob("soak.jsonl.*"))
    verdict_rss_series = measurement_window(
        rss_series, args.warmup_s, args.duration)
    rss = stability.rss_slope(verdict_rss_series)
    full_run_rss = stability.rss_slope(rss_series)
    delta_mib = (rss.get("delta_mib") or 0.0)
    thread_growth = (max(thread_series) - thread_series[0]) if thread_series else 0
    errors = counter.counts.get("ERROR", 0) + counter.counts.get("CRITICAL", 0)

    # PHAI doc CA cac file da xoay vong. Doc mot minh audit_path se bo sot moi
    # inject/revert da bi day sang audit.jsonl.1/.2/... - va chinh soak nay ep
    # xoay vong, nen do la hau het chung. Bat duoc khi soat lai script 8.8.
    all_rows = []
    for part in _rotation_order(audit_path):
        all_rows += read_rows(part)
    rows = blind_time.pairs(all_rows)
    content = {
        "lesson": "8.8",
        "experiment": "C11 soak",
        "config": {
            "production": bool(args.production),
            "timeline_samples": 0 if args.production else 4096,
            "sampler": sampler is not None,
            "warmup_s": args.warmup_s,
            "verdict_window_s": [args.warmup_s, total_s],
            "comparable_to_phase7": bool(
                args.production and args.warmup_s == DEFAULT_WARMUP_S
                and args.duration == 1800.0),
            "why": ("Phase 7 dang ky nguong <= 1 MiB tren CAU HINH PRODUCTION "
                    "(timeline tat, khong sampler) va loai 300 s warmup. Cau "
                    "hinh co do dac mang them hai bo dem cua DUNG CU DO, hoac "
                    "do tu t=0, khong so truc tiep voi nguong do duoc."),
        },
        "duration_s": args.duration,
        "total_run_s": round(t1 - t0, 1),
        "duty_cycle": {"flood_on_s": FLOOD_ON_S, "period_s": FLOOD_PERIOD_S,
                       "n_flood_spans": len(spans_plan)},
        "audit": {
            "path": str(audit_path.relative_to(C.ROOT)),
            "max_rows_per_file": AUDIT_MAX_ROWS,
            "rotated_files": rotated,
            "n_rotations": len(rotated),
            "n_rows_all_files": len(all_rows),
            "chain": chain,
            # Chuoi phai lien tuc QUA cac file da xoay vong; neu khong, C10 mat
            # sach bang chung va moi ket luan dung lai tren no do theo.
            "chain_spans_rotation": bool(chain.get("ok")) and len(rotated) > 0,
        },
        "resources": {
            "rss": rss,
            "rss_full_run_report_only": full_run_rss,
            "n_rss_samples": len(rss_series),
            "n_rss_samples_verdict": len(verdict_rss_series),
            "threads_start": thread_series[0] if thread_series else None,
            "threads_max": max(thread_series) if thread_series else None,
            "thread_growth": thread_growth,
            "intervention_log_len_series": log_len_series,
        },
        "controller_stats": dict(getattr(controller, "stats", {})),
        "n_interventions": len(rows),
        "holds_s": [round(h, 1) for h in blind_time.holds(rows)],
        "gaps_s": [round(g, 2) for g in blind_time.gaps(rows)],
        "degraded_tick_fraction": {
            host: degraded.fraction(ticks, spans_wall, host)
            for host in ("h1", "h2", "h3")
        },
        "n_raw_ticks_saved": len(ticks),
        "log_counts": counter.counts,
        "c11_thresholds": {"max_delta_mib": C11_MAX_DELTA_MIB,
                           "max_thread_growth": C11_MAX_THREAD_GROWTH,
                           "max_errors": 0},
        "c11_pass": bool(
            chain.get("ok")
            and errors == 0
            and abs(delta_mib) <= C11_MAX_DELTA_MIB
            and thread_growth <= C11_MAX_THREAD_GROWTH
            and getattr(controller, "stats", {}).get("exceptions", 1) == 0
        ),
        "health_before": health_before,
        "health_after": infra_check(raise_on_fail=False),
        "pid_note": "RSS do tren tien trinh harness (PID %d), bao gom ca "
                    "detector + controller + collector cung tien trinh" % os.getpid(),
    }
    C.atomic_json(out, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("wrote", out, "| C11 =", content["c11_pass"],
          "| dRSS %.3f MiB | threads +%d | ERROR %d | xoay vong %d | chuoi %s"
          % (delta_mib, thread_growth, errors, len(rotated), chain.get("ok")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
