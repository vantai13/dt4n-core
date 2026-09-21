#!/usr/bin/env python3
"""C10 - dung lai BIT-EXACT moi quyet dinh cua controller tu audit (Lesson 8.8).

    doc dong audit  ->  goi lai decide()  ->  ket qua PHAI TRUNG TUNG BIT

Day la cong kho nhat cua Phase 8 va no KHONG VA DUOC O PHUT CHOT: no doi bay
quyet dinh tat dinh trai suot tam lesson (xem docs/phase-8/08-acceptance.md
§2.2). Neu bat ky cai nao trong bay cai do khong duoc lam tu dau, khong co
script nao o day cuu duoc.

Ba chi tiet de sai, ca ba deu duoc chan tuong minh o duoi:
  1. KIEM CHUOI HASH TRUOC khi dung lai. Chuoi gay -> audit khong dang tin ->
     dung lai no la vo nghia. Thu tu nay quan trong.
  2. `n_decisions > 0`. Neu khong co dong `decision` nao thi khop == tong == 0
     va `0 == 0` la True -> PASS GIA. Bay kinh dien.
  3. Doc theo THU TU XOAY VONG va kiem chuoi LIEN qua cac file.

Chay:
  .venv/bin/python scripts/replay_phase8_decisions.py \
      --audit 'logs/phase8_soak/*/soak.jsonl' --out results/report/phase8_c10.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.audit import _rotation_order, read_rows, verify_chain  # noqa: E402
from controller.policy import (  # noqa: E402
    ControllerState, DetectorView, PolicyParams, decide,
)
from ml import campaign as C  # noqa: E402


def _short(path):
    """Duong dan tuong doi voi goc repo khi co the; audit tam thoi thi giu nguyen."""
    try:
        return str(Path(path).relative_to(C.ROOT))
    except ValueError:
        return str(path)


def rotation_order(path: Path):
    """audit.jsonl.1 -> .2 -> ... -> audit.jsonl (cu truoc, moi sau)."""
    return _rotation_order(Path(path))


def view_of(row: dict) -> DetectorView:
    view = row["input"]
    return DetectorView(
        state=view["state"],
        cause=view["cause"],
        affected=tuple(view["affected"]),
        # roles chi duoc ghi khi `changed` HOAC state == "act" (sua o review 8.6):
        # do la chinh xac cac tick ma localize() duoc goi. Tick khac khong dung
        # den roles nen () la dung, khong phai mot phong doan.
        roles=tuple(sorted((row.get("roles") or {}).items())),
        fresh=view["fresh"],
        boot_id=view["bootId"],
        seq=view["seq"],
    )


def replay_file(path, params, out):
    for row in read_rows(path):
        if row.get("kind") != "decision":
            continue
        out["n_decisions"] += 1
        cstate = ControllerState(**row["cstate_before"])
        actions, after = decide(view_of(row), cstate, row["t_mono"], params)
        same_state = asdict(after) == row["cstate_after"]
        same_count = len(actions) == row["n_actions"]
        if same_state and same_count:
            out["n_match"] += 1
        else:
            out["mismatches"].append({
                "file": Path(path).name, "seq": row["seq"],
                "expected_cstate_after": row["cstate_after"],
                "replayed_cstate_after": asdict(after),
                "expected_n_actions": row["n_actions"],
                "replayed_n_actions": len(actions),
            })
        if row.get("params_sha256"):
            out["params_sha256_seen"].add(row["params_sha256"])


def replay(audit_glob, params=None):
    params = params or PolicyParams()
    heads = sorted(glob.glob(audit_glob))
    heads = [p for p in heads if not Path(p).suffix[1:].isdigit()]
    if not heads:
        return {"c10_pass": False, "reason": "khong tim thay audit: %s" % audit_glob}
    out = {"n_decisions": 0, "n_match": 0, "mismatches": [],
           "params_sha256_seen": set(), "files": [], "chains": []}
    for head in heads:
        files = rotation_order(head)
        # (1) CHUOI TRUOC. verify_chain di theo thu tu xoay vong va kiem ca
        #     tinh lien tuc cua seq, nen mot dut o cho noi file bi bat o day.
        chain = verify_chain(head)
        out["chains"].append({"head": Path(head).name,
                              "n_files": len(files), **chain})
        if not chain.get("ok"):
            return {"c10_pass": False,
                    "reason": "chuoi gay o %s dong %s" % (chain.get("file"),
                                                          chain.get("broken_at_line")),
                    "chains": out["chains"]}
        for path in files:
            out["files"].append(_short(path))
            replay_file(path, params, out)
    out["params_sha256_seen"] = sorted(out["params_sha256_seen"])
    out["fraction"] = (out["n_match"] / out["n_decisions"]) if out["n_decisions"] else 0.0
    # (2) n_decisions > 0: chan PASS GIA.
    out["c10_pass"] = out["n_decisions"] > 0 and out["n_match"] == out["n_decisions"]
    out["params_sha256_consistent"] = len(out["params_sha256_seen"]) <= 1
    out["mismatches"] = out["mismatches"][:10]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True,
                        help="glob toi file audit DAU (khong ke .1 .2 ...)")
    parser.add_argument("--out", default="results/report/phase8_c10.json")
    parser.add_argument("--min-decisions", type=int, default=1000,
                        help="C10 tren 5 tick la bang chung rong")
    args = parser.parse_args()

    result = replay(str(C.ROOT / args.audit) if not args.audit.startswith("/")
                    else args.audit)
    result["min_decisions_required"] = args.min_decisions
    result["enough_evidence"] = result.get("n_decisions", 0) >= args.min_decisions
    out = C.ROOT / args.out
    C.atomic_json(out, {
        "content": result,
        "content_sha256": C.sha256_bytes(C.canonical_json(result).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[C10] %s | %d/%d quyet dinh dung lai bit-exact (%.4f) | du bang chung: %s"
          % (result.get("c10_pass"), result.get("n_match", 0),
             result.get("n_decisions", 0), result.get("fraction", 0.0),
             result.get("enough_evidence")))
    if result.get("mismatches"):
        print(json.dumps(result["mismatches"][:2], indent=1)[:1200])
    print("wrote", out)
    return 0 if result.get("c10_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
