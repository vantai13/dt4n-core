#!/usr/bin/env python3
"""Probe hai chiều cho guard vùng vận hành Phase 7.1."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402
from ml import operating_range as O  # noqa: E402


PREREG = C.ROOT / "results/report/phase7_prereg.json"
OUT = C.ROOT / "results/report/phase7_operating_range_probe.json"


def runs(relative_dir: str, prefixes: tuple[str, ...]) -> list[Path]:
    directory = C.ROOT / relative_dir
    return sorted(path for path in directory.glob("*.jsonl") if path.name.startswith(prefixes))


def main() -> int:
    if OUT.exists():
        print("[P7.1] kết quả probe đã tồn tại, không ghi đè:", OUT)
        return 1
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    must_fire = runs("data/phase6r/raw", ("RN-load8M", "RN-load10M"))
    must_not_mask = (
        runs("data/phase6r/raw", ("RD-", "RC-"))
        + runs("data/phase5/raw", ("F-",))
    )
    report_only = (
        runs("data/phase6r/raw", ("RN-load6M", "RS-", "RO-"))
        + runs("data/phase5/raw", ("C-",))
    )

    try:
        fire = [O.feasibility(prereg, path) for path in must_fire]
        mask = [O.feasibility(prereg, path) for path in must_not_mask]
        other = [O.feasibility(prereg, path) for path in report_only]
    except O.LfsPointerError as exc:
        print("[P7.1] DỪNG:", exc)
        return 2

    p1 = bool(fire) and all(
        result["frac_guard_active"] is not None
        and result["frac_guard_active"] >= 0.90
        for result in fire
    )
    p2 = bool(mask) and all(result["n_guard_active"] == 0 for result in mask)
    outcome = "KN1" if p1 and p2 else ("KN2" if p1 else "KN3")
    content = {
        "prereg_content_sha256": prereg["content_sha256"],
        "threshold_mbps": O.load_sealed_threshold(prereg),
        "P1_must_fire": {"pass": p1, "runs": fire},
        "P2_must_not_mask": {"pass": p2, "runs": mask},
        "report_only": other,
        "outcome": outcome,
        "prediction": prereg["content"]["predictions"]["expected_outcome"],
        "prediction_correct": outcome == prereg["content"]["predictions"]["expected_outcome"],
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    for result in fire + mask + other:
        print(
            "%-42s median g=%7s  guard %3s/%-3s"
            % (
                result["run_id"],
                result["g_median_mbps"],
                result["n_guard_active"],
                result["n_judgeable"],
            )
        )
    print("[P7.1] P1=%s P2=%s -> %s (dự đoán %s)" % (p1, p2, outcome, content["prediction"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
