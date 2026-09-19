#!/usr/bin/env python3
"""Dong bang Phase 7 (Lesson 7.7 phan 2, buoc 1). Commit file nay roi tag phase-7-frozen.

Tu choi neu: worktree ban, hoac bat ky file 6R da ghim nao troi khoi phase6r_manifest.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_freeze_set import frozen_files       # noqa: E402

from bridge import detector_contract as D        # noqa: E402
from bridge import detector_runner as DR         # noqa: E402
from ml import campaign as C                     # noqa: E402

OUT = C.ROOT / "results/report/phase7_freeze.json"


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=C.ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    if OUT.exists():
        print("[FREEZE] da ton tai:", OUT)
        return 1
    dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    if dirty:
        print("[FREEZE] TU CHOI: worktree ban:", dirty[:10])
        return 2
    m6 = json.loads((C.ROOT / "results/report/phase6r_manifest.json").read_text())["content"]["files_sha256"]
    groups = frozen_files()
    drift = [p for p in groups["pinned_6r"] if C.sha256_file(C.ROOT / p) != m6[p]]
    if drift:
        print("[FREEZE] TU CHOI: file 6R da ghim bi troi:", drift)
        return 3
    runner_init = inspect.signature(DR.DetectorRunner.__init__).parameters
    content = {
        "freeze_id": "DT4N-P7-FREEZE",
        "parent_commit": git("rev-parse", "HEAD"),
        "rule": "moi receipt nghiem thu phai sinh tu commit chua file nay (tag phase-7-frozen); "
                "orchestrator kiem SHA tung file truoc khi do",
        "pinned_6r_bit_identical": True,
        "files_sha256": {g: {p: C.sha256_file(C.ROOT / p) for p in files} for g, files in groups.items()},
        # doc tu CODE, khong go tay: freeze mo ta dung cai dang chay
        "config": {"timeline_samples_default": runner_init["timeline_samples"].default,
                   "ttl_ticks": D.TTL_TICKS, "write_timeout_s": DR.WRITE_TIMEOUT_S,
                   "operating_range_threshold_mbps": json.loads(
                       (C.ROOT / "results/report/phase7_prereg.json").read_text())["content"]["guard"]["threshold_mbps"]},
    }
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
                        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    n = sum(len(v) for v in content["files_sha256"].values())
    print("[FREEZE] %d file, sha=%s" % (n, json.loads(OUT.read_text())["content_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
