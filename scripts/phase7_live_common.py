"""Shared startup and measurement helpers for live Phase 7.6 harnesses."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import detector_contract as D  # noqa: E402
from bridge.collector import Collector  # noqa: E402
from bridge.detector_runner import (  # noqa: E402
    TIMELINE_SAMPLES,
    DetectorRunner,
    DittoTransport,
)
from ml import campaign as C  # noqa: E402
from ml.design import git_provenance  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from mininet.env_runner import EnvRunner  # noqa: E402

PAGE = os.sysconf("SC_PAGE_SIZE")


class LevelCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.counts, self.first_errors, self.overran = {}, [], 0

    def emit(self, record):
        self.counts[record.levelname] = self.counts.get(record.levelname, 0) + 1
        message = record.getMessage()
        if "overran" in message.lower():
            self.overran += 1
        if record.levelno >= logging.ERROR and len(self.first_errors) < 20:
            self.first_errors.append(
                "%s %s: %s" % (record.levelname, record.name, message[:200])
            )


def rss_kib() -> int:
    return int(Path("/proc/self/statm").read_text().split()[1]) * PAGE // 1024


def cpu_s() -> float:
    times = os.times()
    return times.user + times.system


def system_rss() -> dict:
    output = {"processes_kib": {}, "containers": {}}
    ps = subprocess.run(
        ["ps", "-eo", "rss=,comm="], capture_output=True, text=True
    ).stdout
    for line in ps.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            name = parts[1].strip()
            for key in (
                "python3", "node", "chrome", "headless_shell", "ryu-manager",
                "java", "mongod", "nginx",
            ):
                if name.startswith(key):
                    output["processes_kib"][key] = (
                        output["processes_kib"].get(key, 0) + int(parts[0])
                    )
    docker = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}"],
        capture_output=True,
        text=True,
    ).stdout
    for line in docker.splitlines():
        name, _, usage = line.partition(" ")
        output["containers"][name] = usage.split("/")[0].strip()
    return output


class Live:
    def __init__(self, duration_s: int):
        self.release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
        self.prereg = json.loads((C.ROOT / "results/report/phase7_prereg.json").read_text())
        self.git_hash = git_provenance()["git_hash"]
        self.env = EnvRunner(sync_period=1.0, clients=3, do_pingall=True, hard_every=0)
        self.duration_s = duration_s
        self.runner = None
        self._thread = None

    def __enter__(self):
        self.env.start()
        self.env.start_profile_background(
            scenario="normal", normal_rate="2M", server_bg_rate=2.0,
            duration=self.duration_s + 120,
        )
        time.sleep(5)
        return self

    def collector(self, boot_id):
        return Collector(
            self.env.net, interval=1.0, net_lock=self.env.net_lock,
            log_path=os.devnull, pretty_log_path=None, overwrite=True,
            run_meta=D.live_run_meta(boot_id, self.git_hash),
        )

    def start_detector(self, timeline_samples: int = TIMELINE_SAMPLES):
        self.runner = DetectorRunner(
            self.release,
            self.prereg,
            DittoTransport(),
            timeline_samples=timeline_samples,
        )
        self._thread = threading.Thread(
            target=self.runner.run_forever,
            args=(self.collector(self.runner.boot_id),),
            daemon=True,
        )
        self._thread.start()
        return self.runner

    def stop_detector(self):
        if self.runner is not None:
            self.runner.stop_event.set()
            self._thread.join(5)
            self.runner = None
            self._thread = None

    def wait_published(self, state, calm_ticks=3, timeout_s=90.0):
        deadline = time.monotonic() + timeout_s
        consecutive = 0
        while time.monotonic() < deadline:
            # Production intentionally disables the per-tick research
            # timeline.  Readiness must still work there; otherwise every
            # production harness waits the full timeout despite already
            # publishing the requested state.
            if self.runner.timeline.maxlen == 0:
                consecutive = consecutive + 1 if self.runner.published == state else 0
                if consecutive >= calm_ticks:
                    return True
                time.sleep(0.25)
                continue
            timeline = list(self.runner.timeline)[-calm_ticks:]
            if len(timeline) == calm_ticks and all(
                entry["published"] == state for entry in timeline
            ):
                return True
            time.sleep(0.25)
        return False

    def __exit__(self, *exc):
        self.stop_detector()
        self.env.close(cleanup_mn=True)
        return False
