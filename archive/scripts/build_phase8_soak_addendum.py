#!/usr/bin/env python3
"""Sua mot loi DEM trong receipt soak 8.8, tinh lai tu chinh audit da niem phong.

Loi: `run_phase8_soak.py` ban chay lan nay doc `holds_s`/`gaps_s`/
`n_interventions` tu MOT file audit hien tai, trong khi chinh soak do ep xoay
vong (`max_rows` = 500) nen phan lon inject/revert nam o cac file
`soak.jsonl.1`, `.2`, ... Ba truong do bi DEM THIEU.

KHONG anh huong den phan quyet C11: `verify_chain` da di theo thu tu xoay vong
tu dau, va RSS / so luong thread / dem ERROR / so lan xoay vong deu do doc lap
voi cach doc nay.

Script da duoc sua cho cac lan chay sau (`_rotation_order` + `read_rows`).
File nay sua SO LIEU cua lan chay nay, tu hien vat, khong chay lai gi.

Chay: .venv/bin/python scripts/build_phase8_soak_addendum.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.audit import _rotation_order, read_rows, verify_chain  # noqa: E402
from measurements import blind_time  # noqa: E402
from ml import campaign as C  # noqa: E402

SRC = C.ROOT / "results/report/phase8_soak.json"
OUT = C.ROOT / "results/report/phase8_soak_addendum.json"


def main() -> int:
    if OUT.exists():
        print("[8.8/soak-addendum] da co, khong ghi de:", OUT)
        return 1
    if not SRC.exists():
        print("chua co", SRC)
        return 2
    src = json.loads(SRC.read_text(encoding="utf-8"))
    sealed = src["content"]
    audit_path = C.ROOT / sealed["audit"]["path"]
    files = _rotation_order(audit_path)
    rows = []
    for part in files:
        rows += read_rows(part)
    paired = blind_time.pairs(rows)
    n_decisions = sum(1 for r in rows if r.get("kind") == "decision")
    n_actions = sum(1 for r in rows if r.get("kind") in ("inject", "revert"))

    content = {
        "lesson": "8.8",
        "corrects": str(SRC.relative_to(C.ROOT)),
        "corrects_sha256": src["content_sha256"],
        "defect": (
            "harness doc mot file audit hien tai trong khi chinh no ep xoay "
            "vong (max_rows = %s), nen holds_s / gaps_s / n_interventions bi "
            "DEM THIEU." % sealed["audit"]["max_rows_per_file"]),
        "not_affected": [
            "c11_pass va moi thanh phan cua no (RSS, ERROR, thread, exception)",
            "audit.chain: verify_chain da di theo thu tu xoay vong tu dau",
            "n_rotations, chain_spans_rotation",
        ],
        "fixed_in_script": "scripts/run_phase8_soak.py (_rotation_order + read_rows)",
        "files_read": [f.name for f in files],
        "sealed_values": {
            "n_interventions": sealed.get("n_interventions"),
            "holds_s": sealed.get("holds_s"),
            "gaps_s": sealed.get("gaps_s"),
        },
        "corrected_values": {
            "n_rows_all_files": len(rows),
            "n_decisions": n_decisions,
            "n_actions": n_actions,
            "n_interventions": len(paired),
            "holds_s": [round(h, 1) for h in blind_time.holds(paired)],
            "gaps_s": [round(g, 2) for g in blind_time.gaps(paired)],
        },
        "chain_recheck": verify_chain(audit_path),
        "gap_definition": "measurements.blind_time.gaps (mot dinh nghia duy nhat)",
    }
    C.atomic_json(OUT, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print("[8.8/soak-addendum] niem phong: n_interventions %s -> %s; %d dong qua %d file"
          % (sealed.get("n_interventions"), len(paired), len(rows), len(files)))
    print("  holds:", content["corrected_values"]["holds_s"])
    print("  gaps :", content["corrected_values"]["gaps_s"])
    print("  chuoi:", content["chain_recheck"].get("ok"))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
