#!/usr/bin/env python3
"""Ghi golden fixture từ Collector live thật (cần sudo, Mininet và Ditto)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge import detector_contract as D  # noqa: E402
from bridge.collector import Collector  # noqa: E402
from ml.design import git_provenance  # noqa: E402
from mininet.env_runner import EnvRunner  # noqa: E402


OUT = Path("test/fixtures/phase7_live_snapshots.jsonl")


def main() -> int:
    runner = EnvRunner(sync_period=1.0, clients=3, do_pingall=True, hard_every=0)
    try:
        runner.start()
        runner.start_profile_background(
            scenario="normal",
            normal_rate="2M",
            server_bg_rate=2.0,
            duration=60,
        )
        time.sleep(5)
        boot_id = D.new_boot_id()
        meta = D.live_run_meta(boot_id, git_provenance()["git_hash"])
        Collector(
            runner.net,
            interval=1.0,
            net_lock=runner.net_lock,
            log_path=str(OUT),
            pretty_log_path=None,
            overwrite=True,
            run_meta=meta,
        ).run(duration=15)
    finally:
        runner.close(cleanup_mn=True)
    print("[P7.2] đã ghi", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
