#!/usr/bin/env python3
"""phase7_manifest.json: SHA moi thu + thu tu commit DANG KY (Lesson 7.7 phan 2, buoc cuoi).

registration_commit_order chung minh bang git (khong phai loi ke): moi file dang ky duoc
THEM vao repo truoc receipt ma no rang buoc.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase7_freeze_set import frozen_files       # noqa: E402

from ml import campaign as C                     # noqa: E402

OUT = C.ROOT / "results/report/phase7_manifest.json"
ORDERED = [   # (file, phai co TRUOC cac file dung sau no trong danh sach)
    "results/report/phase7_prereg.json",
    "results/report/phase7_operating_range_probe.json",
    "results/report/phase7_contract.json",
    "test/fixtures/phase7_live_snapshots.jsonl",
    "results/report/phase7_contract_amendment_1.json",
    "results/report/phase7_s6_v2_prereg.json",
    "results/report/phase7_soak_live_v2.json",
    "results/report/phase7_freeze.json",
    "results/report/phase7_acceptance/index.json",
    "results/report/phase7_verdicts.json",
]
DOCS = sorted(str(p.relative_to(C.ROOT)) for p in (C.ROOT / "docs/phase-7").glob("*.md"))


def first_commit(path: str) -> dict:
    out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H|%cI|%s", "--", path],
                         cwd=C.ROOT, capture_output=True, text=True).stdout.strip().splitlines()
    if not out:
        return {"path": path, "commit": None}
    h, t, s = out[-1].split("|", 2)
    return {"path": path, "commit": h, "committed_at": t, "subject": s}


def main() -> int:
    order = [first_commit(p) for p in ORDERED]
    missing = [o["path"] for o in order if o["commit"] is None]
    times = [o["committed_at"] for o in order if o["commit"]]
    content = {
        "manifest_id": "DT4N-P7-MANIFEST",
        "source_git_hash": subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True,
                                          text=True).stdout.strip(),
        "registration_commit_order": order,
        "order_is_chronological": times == sorted(times),
        "missing_from_git": missing,
        "files_sha256": {p: C.sha256_file(C.ROOT / p)
                         for p in sorted({*ORDERED, *DOCS, *(f for g in frozen_files().values() for f in g)})
                         if (C.ROOT / p).exists()},
        "lfs_note": "data/phase5/raw va data/phase6r/raw la Git LFS: sau `git clone` phai `git lfs pull`; "
                    "neu khong, file la con tro ~131 byte va moi script doc raw se dung o LfsPointerError. "
                    "Receipt Phase 7 KHONG can raw de tai lap verdict (chi can JSON da niem phong).",
        "reproduce": ["git clone <repo> && cd dt4n-core && git lfs pull",
                      "git checkout phase-7-complete",
                      "python3 -m pytest -q test/",
                      "python3 -c 'from measurements.phase7_verdicts import derive'  # + build lai verdict tu receipt, so SHA"],
    }
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
                        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print("chronological=%s missing=%s files=%d" % (content["order_is_chronological"], missing,
                                                      len(content["files_sha256"])))
    return 0 if content["order_is_chronological"] and not missing else 4


if __name__ == "__main__":
    sys.exit(main())
