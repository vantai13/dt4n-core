#!/usr/bin/env python3
"""Chan doan HAU KIEM (post-hoc) cho ket qua dong Phase 8. KHONG doi verdict nao.

Doc audit tu archive da niem phong (giai nen vao --root), tra loi 3 cau:
  D1. E1 co bi O NHIEM NEN khong? (client trong `affected` luc detector `normal`, TRUOC flood)
  D2. link-s2-s3 co lech envelope NGAY TU DAU phien khong, theo tung chien dich?
  D3. Neu LATCH theo episode dung nhu prereg 8.1, lan inject DAU TIEN cua moi trial E1 doi ra sao?
      (phat lai vong ho: hop le toi diem phan ky dau tien = lan inject dau tien)
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller.localize import localize  # noqa: E402
from controller.policy import (  # noqa: E402
    ACT,
    ControllerState,
    DetectorView,
    PolicyParams,
    classify,
    decide,
)
from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_closure_diagnostics.json"
CLIENTS = ("host-h1", "host-h2", "host-h3")
HOLDING = ("SUPPRESSED", "UNKNOWN")


def decisions(path):
    rows, roles = [], {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("kind") != "decision" or not row.get("input"):
                continue
            roles = row.get("roles") or roles
            rows.append(dict(row, roles=roles))
    return rows


def short(entity):
    return entity.split(":")[-1]


def d1_contamination(root, culprit_of):
    """Dem nguoi ngoai cuoc trong affected truoc luc detector len suspect/act."""
    out = []
    for path in sorted(glob.glob(str(root / "logs/phase8_c1_control/*/*.jsonl"))):
        pre = []
        for row in decisions(path):
            if row["input"]["state"] in ("suspect", "act"):
                break
            pre.append(row)
        culprit = "host-" + culprit_of[Path(path).stem]
        dirty = sorted(
            {
                short(affected)
                for row in pre
                for affected in row["input"]["affected"]
                if short(affected) in CLIENTS and short(affected) != culprit
            }
        )
        out.append(
            {
                "trial": Path(path).stem,
                "culprit": culprit,
                "n_pre_flood_ticks": len(pre),
                "bystanders_in_affected_while_normal": dirty,
            }
        )
    return out


def d2_s2s3_baseline(root):
    groups = defaultdict(lambda: [0, 0, 0])
    for path in glob.glob(str(root / "logs/phase8_*/**/*.jsonl"), recursive=True):
        if Path(path).suffix[1:].isdigit():
            continue
        key = "/".join(Path(path).relative_to(root).parts[1:3])
        for row in decisions(path):
            current = row["input"]
            if current["state"] == "normal":
                groups[key][0] += 1
                groups[key][1] += any(
                    "link-s2-s3" in affected for affected in current["affected"]
                )
            if (
                current["state"] == "unknown"
                and current.get("cause") == "suppressed_intervention"
            ):
                groups[key][2] += 1
    return {
        key: {
            "normal_ticks": normal,
            "normal_with_s2s3": s2s3,
            "fraction": round(s2s3 / normal, 4) if normal else None,
            "suppressed_ticks": suppressed,
        }
        for key, (normal, s2s3, suppressed) in sorted(groups.items())
    }


def first_inject(rows, episode_latch):
    """Phat lai toi lan inject dau tien, tuy chon LATCH tai canh len cua act."""
    params = PolicyParams()
    cstate = ControllerState(**rows[0]["cstate_before"])
    in_episode, latched = False, None
    for row in rows:
        current = row["input"]
        view = DetectorView(
            current["state"],
            current["cause"],
            tuple(current["affected"]),
            tuple(sorted(row["roles"].items())),
            current["fresh"],
            current["bootId"],
            current["seq"],
        )
        label = classify(view)
        if episode_latch:
            if label == ACT and not in_episode:
                in_episode = True
                latched = localize(view.affected, dict(view.roles)).target
            elif label != ACT and label not in HOLDING:
                in_episode, latched = False, None
            if cstate.mode == "IDLE" and label == ACT and latched is None:
                continue
        actions, cstate = decide(view, cstate, row["t_mono"], params)
        injects = [action.link for action in actions if action.kind == "inject"]
        if injects:
            return injects[0]
    return None


def d3_latch_counterfactual(root):
    out = []
    for path in sorted(glob.glob(str(root / "logs/phase8_c1_control/*/*.jsonl"))):
        rows = decisions(path)
        out.append(
            {
                "trial": Path(path).stem,
                "current_policy": first_inject(rows, False),
                "episode_latch": first_inject(rows, True),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="thu muc da giai nen archive")
    root = Path(parser.parse_args().root)
    e1 = json.loads(
        (C.ROOT / "results/report/phase8_c1_control.json").read_text()
    )["content"]
    culprit_of = {Path(trial["audit"]).stem: trial["culprit"] for trial in e1["trials"]}
    d1 = d1_contamination(root, culprit_of)
    d2 = d2_s2s3_baseline(root)
    d3 = d3_latch_counterfactual(root)
    real = {
        Path(trial["audit"]).stem: (trial.get("inject_links") or [None])[0]
        for trial in e1["trials"]
    }
    content = {
        "lesson": "8.9-diagnostic",
        "kind": "registered post-hoc diagnostic",
        "changes_verdicts": False,
        "archive_sha256": C.sha256_file(
            C.ROOT / "results/evidence/phase8/phase8_audits.tar.gz"
        ),
        "D1_contamination": d1,
        "D2_s2s3_baseline": d2,
        "D3_latch_counterfactual": d3,
        "D3_replay_matches_live": all(
            real.get(result["trial"]) == result["current_policy"] for result in d3
        ),
        "caveat": "D3 la IN-SAMPLE tren chinh du lieu lam lo van de; chi la gia thuyet cho Phase 9",
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    dirty = [
        result["trial"][:2]
        for result in d1
        if result["bystanders_in_affected_while_normal"]
    ]
    flips = sum(
        1 for result in d3 if result["current_policy"] != result["episode_latch"]
    )
    print("D1 trial o nhiem:", dirty)
    print(
        "D3 replay khop live:",
        content["D3_replay_matches_live"],
        "| so trial doi ket qua:",
        flips,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
