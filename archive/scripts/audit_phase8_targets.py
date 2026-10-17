#!/usr/bin/env python3
"""Quet MOI audit controller da co: moi lenh inject nham vao ai? (dong Phase 8)

Hai cau hoi, tra loi bang may thay vi bang mot chuoi van ban trong verdict:
  Q1. Co inject nao vao link KHAC link cua thu pham da biet khong?
  Q2. Duong nguy hiem `probe_target_changed` co tung xay ra live khong, va
      trong WINDOW_S giay sau no co inject nao khong?

Chay (tren may co logs/ that; logs/ bi .gitignore nen clone sach khong co):
  python3 scripts/audit_phase8_targets.py \
      --glob 'logs/phase8_*/**/*.jsonl' --glob 'logs/phase8_*.jsonl' \
      --allow 'phase8_chaos=h1,h2'
"""
from __future__ import annotations

import argparse
import glob
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.audit import _rotation_order, read_rows  # noqa: E402
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_target_audit.json"
DEFAULT_CULPRITS = ("h1",)  # moi chien dich 8.3-8.8 deu flood h1 -> srv1
WINDOW_S = 30.0


def heads(patterns):
    found = set()
    for pattern in patterns:
        for p in glob.glob(str(C.ROOT / pattern), recursive=True):
            if not Path(p).suffix[1:].isdigit():  # bo .1 .2 (doc qua head)
                found.add(Path(p))
    return sorted(found)


def allowed_for(path: Path, overrides: dict) -> set:
    for key, hosts in overrides.items():
        if key in str(path):
            return set(hosts)
    return set(DEFAULT_CULPRITS)


def scan(path: Path, allowed: set) -> dict:
    injects, changes, wrong = [], [], []
    for part in _rotation_order(path):
        for row in read_rows(part):
            reason = (row.get("cstate_after") or {}).get("reason")
            if reason == "probe_target_changed":
                changes.append(row.get("t_mono"))
            if row.get("kind") != "inject":
                continue
            for action in row.get("actions") or []:
                host = action["link"].split("-")[0]
                item = {
                    "t_mono": row.get("now_mono"),
                    "link": action["link"],
                    "reason": action.get("reason"),
                    "id": action.get("intervention_id"),
                }
                injects.append(item)
                if host not in allowed:
                    wrong.append(item)
    after_change = [
        i
        for i in injects
        for t in changes
        if t is not None
        and i["t_mono"] is not None
        and 0.0 <= i["t_mono"] - t <= WINDOW_S
    ]
    return {
        "file": str(path.relative_to(C.ROOT)),
        "sha256": C.sha256_file(path),
        "allowed_targets": sorted(allowed),
        "n_inject": len(injects),
        "links": sorted({i["link"] for i in injects}),
        "n_wrong_target": len(wrong),
        "wrong_target": wrong[:20],
        "n_probe_target_changed": len(changes),
        "n_inject_within_window_after_change": len(after_change),
        "inject_after_change": after_change[:20],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", action="append", required=True)
    ap.add_argument(
        "--allow",
        action="append",
        default=[],
        help="'chuoi_trong_duong_dan=h1,h2' - thu pham hop le cua chien dich do",
    )
    args = ap.parse_args()
    overrides = {}
    for spec in args.allow:
        key, hosts = spec.split("=", 1)
        overrides[key] = [h for h in hosts.split(",") if h]
    files = [scan(p, allowed_for(p, overrides)) for p in heads(args.glob)]
    content = {
        "lesson": "8.9-closure",
        "question": "Q1 nham sai muc tieu? Q2 duong probe_target_changed?",
        "window_s": WINDOW_S,
        "n_files": len(files),
        "n_inject_total": sum(f["n_inject"] for f in files),
        "n_wrong_target_total": sum(f["n_wrong_target"] for f in files),
        "n_probe_target_changed_total": sum(
            f["n_probe_target_changed"] for f in files
        ),
        "n_inject_after_change_total": sum(
            f["n_inject_within_window_after_change"] for f in files
        ),
        "files": files,
    }
    content["evidence_nonempty"] = content["n_inject_total"] > 0
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    print(
        "files=%d inject=%d wrong=%d target_changed=%d inject_after_change=%d"
        % (
            content["n_files"],
            content["n_inject_total"],
            content["n_wrong_target_total"],
            content["n_probe_target_changed_total"],
            content["n_inject_after_change_total"],
        )
    )
    return 0 if content["evidence_nonempty"] else 3


if __name__ == "__main__":
    sys.exit(main())
