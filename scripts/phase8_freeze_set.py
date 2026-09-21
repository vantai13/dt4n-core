"""Tap file DONG BANG cua Phase 8 (8.9). Mot nguon su that cho freeze + manifest."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase7_freeze_set import HARNESS as P7_HARNESS  # noqa: E402
from phase7_freeze_set import PINNED_6R, dashboard_src  # noqa: E402
from phase7_freeze_set import RUNTIME as P7_RUNTIME  # noqa: E402
from phase7_freeze_set import SEALED as P7_SEALED  # noqa: E402

CONTROLLER = sorted(
    str(path.relative_to(ROOT)) for path in (ROOT / "controller").glob("*.py")
)
RUNTIME = sorted(set(P7_RUNTIME + CONTROLLER + ["bridge/controlloop_contract.py"]))
SEALED = P7_SEALED + [
    "results/report/phase8_prereg.json",
    "results/report/phase8_sim_predictions.json",
    "results/report/phase8_contract.json",
    "results/report/phase8_s11_amendment1.json",
    "results/report/phase8_closure_prereg.json",
]
HARNESS = sorted(
    set(
        P7_HARNESS
        + [
            "scripts/phase8_ab_common.py",
            "scripts/run_phase8_ab.py",
            "scripts/run_phase8_stability.py",
            "scripts/run_phase8_chaos.py",
            "scripts/run_phase8_soak.py",
            "scripts/run_phase8_c1_control.py",
            "scripts/measure_phase8_c3.py",
            "scripts/measure_phase8_ui_stale.py",
            "scripts/replay_phase8_decisions.py",
            "scripts/audit_phase8_targets.py",
            "scripts/analyze_phase8_suppression_modes.py",
            "scripts/build_phase8_gap_reconciliation.py",
            "scripts/accept_phase8.py",
            "scripts/phase8_infra_health.py",
            "scripts/archive_phase8_evidence.py",
            "measurements/blind_time.py",
            "measurements/attribution.py",
            "measurements/degraded.py",
            "measurements/ab_stats.py",
        ]
    )
)


def frozen_files() -> dict[str, list[str]]:
    groups = {
        "runtime": RUNTIME + dashboard_src(),
        "pinned_6r": PINNED_6R,
        "sealed": SEALED,
        "harness": HARNESS,
    }
    return {
        key: [filename for filename in values if (ROOT / filename).exists()]
        for key, values in groups.items()
    }


def missing() -> list[str]:
    groups = {"runtime": RUNTIME, "sealed": SEALED, "harness": HARNESS}
    return [
        filename
        for values in groups.values()
        for filename in values
        if not (ROOT / filename).exists()
    ]


if __name__ == "__main__":
    print("thieu:", missing() or "khong")
    print({key: len(values) for key, values in frozen_files().items()})
