#!/usr/bin/env python3
"""Run detector live and pause the active Ditto nginx container for five seconds."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import detector_contract as D  # noqa: E402
from bridge.collector import Collector  # noqa: E402
from bridge.detector_runner import (  # noqa: E402
    DetectorRunner,
    DittoTransport,
    RotatingJsonl,
)
from ml import campaign as C  # noqa: E402
from ml.design import git_provenance  # noqa: E402
from ml.release import DetectorRelease  # noqa: E402
from mininet.env_runner import EnvRunner  # noqa: E402


OUT = C.ROOT / "results/report/phase7_runner_backpressure_live.json"
AUDIT = "logs/phase7_detector_audit.jsonl"


def nginx_container() -> str:
    """Resolve the running Compose nginx service; allow an explicit override."""
    override = os.environ.get("DT4N_DITTO_NGINX_CONTAINER")
    if override:
        return override
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.service=nginx",
            "--format",
            "{{.Names}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(names) != 1:
        raise RuntimeError(
            "cần đúng một nginx Compose đang chạy, nhận %r; đặt "
            "DT4N_DITTO_NGINX_CONTAINER để chọn rõ" % names
        )
    return names[0]


def docker(action: str, container: str) -> None:
    subprocess.run(["docker", action, container], check=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--pause-at", type=float, default=20.0)
    parser.add_argument("--pause-for", type=float, default=5.0)
    args = parser.parse_args()

    if os.path.exists(AUDIT):
        os.remove(AUDIT)
    release = DetectorRelease.load(C.ROOT / "models/detector-release-1.0.0.json")
    prereg = json.loads(
        (C.ROOT / "results/report/phase7_prereg.json").read_text()
    )
    audit = RotatingJsonl(AUDIT)
    runner = DetectorRunner(release, prereg, DittoTransport(), audit=audit)
    environment = EnvRunner(
        sync_period=1.0,
        clients=3,
        do_pingall=True,
        hard_every=0,
    )
    container = nginx_container()
    paused = {}
    try:
        environment.start()
        environment.start_profile_background(
            scenario="normal",
            normal_rate="2M",
            server_bg_rate=2.0,
            duration=int(args.duration) + 30,
        )
        time.sleep(5)
        collector = Collector(
            environment.net,
            interval=1.0,
            net_lock=environment.net_lock,
            log_path=os.devnull,
            pretty_log_path=None,
            overwrite=True,
            run_meta=D.live_run_meta(
                runner.boot_id, git_provenance()["git_hash"]
            ),
        )
        t0 = time.monotonic()

        def chaos():
            time.sleep(args.pause_at)
            paused["start"] = time.monotonic() - t0
            docker("pause", container)
            time.sleep(args.pause_for)
            docker("unpause", container)
            paused["end"] = time.monotonic() - t0
            time.sleep(max(0.0, args.duration - args.pause_at - args.pause_for))
            runner.stop_event.set()

        threading.Thread(target=chaos, name="ditto-chaos", daemon=True).start()
        outcome = runner.run_forever(collector)
    finally:
        try:
            docker("unpause", container)
        except Exception:
            pass
        audit.close()
        environment.close(cleanup_mn=True)

    with open(AUDIT, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    source_times = [row["t_source"] for row in rows]
    deltas = [right - left for left, right in zip(source_times, source_times[1:])]
    content = {
        "outcome": outcome,
        "nginx_container": container,
        "pause_window_s": paused,
        "ticks": len(rows),
        "dt_max_s": round(max(deltas), 6),
        "dt_over_1_5_s": sum(delta > 1.5 for delta in deltas),
        "published_gap_unknown": sum(row["cause"] == "gap" for row in rows),
        "states": {
            state: sum(row["published"] == state for row in rows)
            for state in {row["published"] for row in rows}
        },
        "stats": runner.stats(),
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(json.dumps(content, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
