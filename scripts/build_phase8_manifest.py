#!/usr/bin/env python3
"""phase8_manifest.json: SHA moi thu va thu tu dang ky bang git."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase8_freeze_set import frozen_files  # noqa: E402

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_manifest.json"
R = "results/report/"
MUST_PRECEDE = [
    (R + "phase8_prereg.json", R + "phase8_sim_predictions.json"),
    (R + "phase8_sim_predictions.json", R + "phase8_contract.json"),
    (R + "phase8_contract.json", R + "phase8_ab_c5.json"),
    (R + "phase8_contract.json", R + "phase8_c3.json"),
    (R + "phase8_contract.json", R + "phase8_stability_flood.json"),
    (R + "phase8_target_audit.json", R + "phase8_closure_prereg.json"),
    (R + "phase8_closure_prereg.json", R + "phase8_c1_control.json"),
    (R + "phase8_closure_prereg.json", R + "phase8_suppression_modes.json"),
    (R + "phase8_closure_prereg.json", R + "phase8_chaos_second_flood.json"),
    (R + "phase8_closure_prereg.json", R + "phase8_c10_v3.json"),
]
DOCS = sorted(
    str(path.relative_to(C.ROOT)) for path in (C.ROOT / "docs/phase-8").glob("*.md")
)


def first_commit(path: str):
    output = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H|%cI", "--", path],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip().splitlines()
    if not output:
        return None
    commit, committed_at = output[-1].split("|", 1)
    return {"commit": commit, "committed_at": committed_at}


def main() -> int:
    checks, missing = [], []
    for before, after in MUST_PRECEDE:
        first, second = first_commit(before), first_commit(after)
        if first is None or second is None:
            missing += [
                path
                for path, commit in ((before, first), (after, second))
                if commit is None
            ]
            continue
        checks.append(
            {
                "before": before,
                "after": after,
                "ok": first["committed_at"] <= second["committed_at"],
                "before_commit": first["commit"],
                "after_commit": second["commit"],
            }
        )
    receipts = sorted({filename for pair in MUST_PRECEDE for filename in pair})
    files = sorted(
        {
            *receipts,
            *DOCS,
            "results/report/phase8_acceptance.json",
            "results/evidence/phase8/index.json",
            "results/evidence/phase8/phase8_audits.tar.gz",
            *(filename for group in frozen_files().values() for filename in group),
        }
    )
    content = {
        "manifest_id": "DT4N-P8-MANIFEST",
        "source_git_hash": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=C.ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "release_status": "NOT_COMPLETE_C1_GATE_FAIL",
        "partial_order_checks": checks,
        "partial_order_ok": bool(checks) and all(check["ok"] for check in checks),
        "missing_from_git": sorted(set(missing)),
        "files_sha256": {
            path: C.sha256_file(C.ROOT / path)
            for path in files
            if (C.ROOT / path).exists()
        },
        "reproduce": [
            "git clone <repo> && cd dt4n-core && git lfs pull",
            "git checkout phase-8-frozen-v2",
            "tar -xzf results/evidence/phase8/phase8_audits.tar.gz",
            "python3 -m pytest -q test/",
            "python3 scripts/accept_phase8.py --strict   # rc=1: C1 FAIL da niem phong",
        ],
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(
        "partial_order_ok=%s missing=%s files=%d status=%s"
        % (
            content["partial_order_ok"],
            content["missing_from_git"],
            len(content["files_sha256"]),
            content["release_status"],
        )
    )
    return 0 if content["partial_order_ok"] and not missing else 4


if __name__ == "__main__":
    sys.exit(main())
