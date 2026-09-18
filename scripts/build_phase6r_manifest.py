#!/usr/bin/env python3
"""Manifest dong Phase 6R: ghim SHA bang chung va thu tu commit dang ky."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_manifest.json"

REGISTRATION_FILES = [
    "results/report/phase6r_slo.json",
    "results/report/phase6r_amendment_1.json",
    "results/report/phase6r_amendment_2.json",
    "results/report/phase6r_amendment_3.json",
    "results/report/phase6r_amendment_4.json",
    "results/report/phase6r_amendment_5.json",
    "results/report/phase6r_amendment_6.json",
    "results/report/phase6r_stability_prereg.json",
    "results/report/phase6r_amendment_7.json",
    "results/report/phase6r_acceptance_prereg.json",
    "results/report/phase6r_acceptance.json",
    "results/report/phase6r_verdicts.json",
    "results/report/phase6r_amendment_8.json",
]

EXTRA_FILES = [
    "models/envelope-1.0.0.json",
    "models/detector-release-1.0.0.json",
    "ml/model.py",
    "ml/serve.py",
    "ml/serve_fast.py",
    "ml/fsm.py",
    "ml/conservation.py",
    "ml/intervention_log.py",
    "ml/blast_radius.py",
    "ml/payload.py",
    "ml/release.py",
    "ml/snapshot_contract.py",
    "requirements.txt",
    "requirements-phase6r.lock.v2.txt",
    "docs/phase-6r/08-acceptance.md",
    "docs/phase-6r/09-phase7-handoff.md",
    "docs/phase-6r/10-amendment-ledger.md",
    "docs/phase-6r/model-card-v2.md",
]


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=C.ROOT, text=True).strip()


def evidence_files():
    receipts = sorted(
        str(path.relative_to(C.ROOT))
        for path in REPORT.glob("phase6r_*")
        if path.is_file() and path.name != OUT.name
    )
    return sorted(set(receipts) | set(EXTRA_FILES))


def registration_history():
    out = []
    for relative in REGISTRATION_FILES:
        lines = _git(
            "log",
            "--diff-filter=A",
            "--format=%H%x09%cI%x09%s",
            "--",
            relative,
        ).splitlines()
        if not lines:
            raise RuntimeError("file dang ky chua tung duoc commit: " + relative)
        commit, stamp, subject = lines[-1].split("\t", 2)
        out.append(
            {
                "path": relative,
                "commit": commit,
                "committed_at": stamp,
                "subject": subject,
            }
        )
    return out


def internal_hash(relative):
    if not relative.endswith(".json"):
        return None
    doc = json.loads((C.ROOT / relative).read_text(encoding="utf-8"))
    if "content" not in doc or "content_sha256" not in doc:
        return None
    return (
        C.sha256_bytes(C.canonical_json(doc["content"]).encode())
        == doc["content_sha256"]
    )


def main():
    if OUT.exists():
        print("[6R-M] da ton tai")
        return 1
    files = evidence_files()
    missing = [relative for relative in files if not (C.ROOT / relative).is_file()]
    if missing:
        raise SystemExit("thieu file: %s" % missing)
    dirty = [relative for relative in files if _git("status", "--porcelain", "--", relative)]
    if dirty:
        raise SystemExit("commit truoc: %s" % dirty)
    checks = {
        relative: valid
        for relative in files
        if (valid := internal_hash(relative)) is not None
    }
    if not all(checks.values()):
        raise SystemExit(
            "hash noi bo sai: %s"
            % [relative for relative, valid in checks.items() if not valid]
        )
    invocations = [
        json.loads(line)
        for line in (REPORT / "phase6r_acceptance_runs.log").read_text().splitlines()
        if line.strip()
    ]
    content = {
        "manifest_id": "DT4N-P6R-MANIFEST-v1",
        "source_git_hash": _git("log", "-1", "--format=%H", "--", *files),
        "files_sha256": {
            relative: C.sha256_file(C.ROOT / relative) for relative in files
        },
        "internal_json_hash_checks": checks,
        "registration_commit_order": registration_history(),
        "r_set_openings": sum(item["mode"] == "acceptance" for item in invocations),
        "rehearsals": sum(item["mode"] == "rehearsal" for item in invocations),
        "tags_required": ["phase-6r-frozen", "phase-6r-opened"],
        "lfs_note": "raw R-campaign nam tren Git LFS; files_sha256 ghim POINTER, phase6r_rcampaign_manifest ghim noi dung raw",
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        },
    )
    print(
        "[6R-M] %d file, content_sha256=%s"
        % (len(files), json.loads(OUT.read_text())["content_sha256"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
