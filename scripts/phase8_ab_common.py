#!/usr/bin/env python3
"""Ha tang chung cho A/B (8.6): lay mau twin, dua he ve sach, chay mot luot.

Giao thuc DANG KY TRUOC, khong chinh giua chung.
"""
from __future__ import annotations

import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.locked_log import LockedInterventionLog  # noqa: E402
from controller.policy import PolicyParams  # noqa: E402
from controller.runner import ControlRunner  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing  # noqa: E402
from rl.scenarios import TrafficFlood  # noqa: E402

MBPS = 8.0 / 1e6
CLIENTS = ("h1", "h2", "h3")
SERVERS = ("srv1",)
DEFAULT_MBPS = 20.0
EPS = 0.01
SETTLE_S = 20.0
FLOOD_S = 120.0
FLOOD_RATE_MBPS = 47
CLEAN_TIMEOUT_S = 60.0
PRIMARY_WINDOW = (2.0, 122.0)      # BIEN CHINH
SECONDARY_WINDOW = (2.0, 32.0)     # thu cap: "hieu qua giai doan dau"


class TwinSampler:
    """Lay mau twin 4 Hz, KHU TRUNG theo bo dem byte.

    Bo dem doi moi tick collector (1 Hz), nen khu trung theo txBytes/rxBytes cho
    dung mot mau moi tick - khong dem hai lan cung mot tick, khong bo sot tick.
    """

    def __init__(self, twin, hosts=CLIENTS + SERVERS, period_s=0.25):
        self.twin = twin
        self.hosts = tuple(hosts)
        self.period_s = period_s
        self.rows: list[dict] = []
        self._last = {}
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="sampler",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(3)

    def _loop(self):
        while not self._stop.wait(self.period_s):
            now = time.time()
            with self.twin._lock:
                things = dict(self.twin.things)
            for host in self.hosts:
                thing = things.get("org.dt4n:host-" + host)
                traffic = (((thing or {}).get("features") or {}).get("traffic")
                           or {}).get("properties") or {}
                if not traffic:
                    continue
                key = (traffic.get("txBytes"), traffic.get("rxBytes"))
                if key == self._last.get(host) or key == (None, None):
                    continue
                self._last[host] = key
                self.rows.append({
                    "t_wall": now,
                    "host": host,
                    "tx_mbps": float(traffic.get("txRate") or 0.0) * MBPS,
                    "rx_mbps": float(traffic.get("rxRate") or 0.0) * MBPS,
                    # rateValid == False -> BO tick, KHONG thay bang 0: doi bw
                    # sinh 1 tick unknown (F8-6) nen thay 0 se PHAT nhanh co
                    # controller.
                    "rate_valid": bool(traffic.get("rateValid")),
                })

    def window(self, t0, t1, host, field="tx_mbps"):
        values = [r[field] for r in self.rows
                  if r["host"] == host and r["rate_valid"] and t0 <= r["t_wall"] < t1]
        invalid = sum(1 for r in self.rows
                      if r["host"] == host and not r["rate_valid"]
                      and t0 <= r["t_wall"] < t1)
        mean = sum(values) / len(values) if values else None
        return mean, len(values), invalid


def require_clean(live, twin, timeout_s=CLEAN_TIMEOUT_S):
    """KIEM TRA trang thai, khong sleep suong. Tra (ok, chi tiet).

    Ton du that giua hai luot, co so: cooldown 8 s (release), lease 15 s (8.4),
    recovery burst ~3 tick (8.1), release_m 3 tick, iperf con sot.
    """
    deadline = time.monotonic() + timeout_s
    detail = {}
    while time.monotonic() < deadline:
        observed = twin.observed_bw()
        detail["bw"] = {k: v for k, v in observed.items() if k.endswith("-s1")}
        bw_ok = all(abs(v - DEFAULT_MBPS) <= EPS
                    for k, v in observed.items()
                    if k.endswith("-s1") and k.split("-")[0] in CLIENTS)
        fields = twin.detector_view_fields()
        detail["detector"] = fields["state"]
        if bw_ok and fields["state"] == "normal":
            calm = live.wait_published("normal", calm_ticks=3, timeout_s=10)
            if calm:
                return True, detail
        time.sleep(0.5)
    return False, detail


def make_controller(twin, detector_runner, audit_path, view_provider=None):
    return ControlRunner(
        twin=twin,
        log_store=LockedInterventionLog(detector_runner.intervention_log),
        routing=Routing.load(C.ROOT / "ditto/routing_table.json"),
        send_command=lambda cmd, cid=None: _send(cmd, cid),
        params=PolicyParams(),
        audit_path=audit_path,
        view_provider=view_provider,
    )


_SEND = {"fn": None}


def bind_send(fn):
    _SEND["fn"] = fn


def _send(cmd, cid=None):
    return _SEND["fn"](cmd, cid=cid)


def run_trial(live, twin, sampler, arm, block, index, rng, detector_runner,
              audit_dir, view_provider_factory=None, flood_s=FLOOD_S):
    """Mot luot. Tra dict ket qua + co huy neu khong dua ve trang thai sach duoc."""
    clean, detail = require_clean(live, twin)
    if not clean:
        return {"block": block, "index": index, "arm": arm, "aborted": True,
                "abort_detail": detail, "primary": None}

    time.sleep(SETTLE_S + rng.uniform(0.0, 1.0))      # PHA NGAU NHIEN

    controller = None
    thread = None
    if arm in ("A", "C"):
        provider = view_provider_factory() if view_provider_factory else None
        controller = make_controller(
            twin, detector_runner,
            audit_dir / ("ab_%s_b%d_i%d.jsonl" % (arm, block, index)),
            view_provider=provider if arm == "C" else None,
        )
        controller.cstate = controller.bootstrap_safe_state()
        thread = threading.Thread(target=controller.run_forever,
                                  name="control-%s" % arm, daemon=True)
        thread.start()

    flood = TrafficFlood("h1", "srv1", FLOOD_RATE_MBPS)
    t_flood = time.time()
    with live.env.net_lock:
        flood.apply(live.env.net)
    time.sleep(flood_s)
    with live.env.net_lock:
        flood.revert(live.env.net)
    time.sleep(10.0)

    stats = dict(controller.stats) if controller else {}
    if controller is not None:
        controller.shutdown()
        thread.join(10)

    def window(host, span, field="tx_mbps"):
        return sampler.window(t_flood + span[0], t_flood + span[1], host, field)

    primary, n_valid, n_invalid = window("h3", PRIMARY_WINDOW)
    secondary_30, _, _ = window("h3", SECONDARY_WINDOW)
    h2_mean, _, _ = window("h2", PRIMARY_WINDOW)
    h1_mean, _, _ = window("h1", PRIMARY_WINDOW)
    srv1_rx, _, _ = window("srv1", PRIMARY_WINDOW, field="rx_mbps")
    return {
        "block": block, "index": index, "arm": arm, "aborted": False,
        "t_flood": t_flood,
        # BIEN CHINH: trung binh txRate h3 tren cua so neo vao t_flood
        "primary": primary,
        "n_ticks": n_valid,
        "n_ticks_invalid": n_invalid,
        "secondary": {
            "h3_window30": secondary_30,     # "hieu qua giai doan dau"
            "h2": h2_mean,                   # DOI CHUNG AM
            "h1": h1_mean,
            "srv1_rx": srv1_rx,
            "n_commands": stats.get("commands"),
            "n_renewals": stats.get("renewals"),
            "n_drift": stats.get("drift_fixes"),
        },
    }


def block_order(rng):
    """ABBA hoac BAAB do DONG XU CO SEED: co so hop le cho randomization test."""
    return ["A", "B", "B", "A"] if rng.random() < 0.5 else ["B", "A", "A", "B"]
