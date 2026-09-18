"""Cong phat hanh va cac ham phan quyet cua lan nghiem thu 6R.7."""
from __future__ import annotations

from ml.acceptance_metrics import clusters, fp_ticks_a2, labels_of
from ml.acceptance_stats import DosePoint, bootstrap_ed50

CLAIMED_CHANNEL = "envelope_only"
FIT_FIELDS = ("method", "ed50", "ci95", "n_converged", "n_boot")


def g2_run(trace, meta, channel: str) -> dict:
    """Dem FP tick/event muc act theo dinh nghia amendment 2."""
    labels = labels_of(trace, meta)
    ticks = fp_ticks_a2(trace, labels, channel, "act_level")
    return {"act_fp_ticks": len(ticks), "act_fp_events": clusters(ticks)}


def dose_fit(points: list[DosePoint]) -> dict:
    """Chay bootstrap da dang ky va chieu dung nam truong cua skeleton."""
    if not points:
        return {field: None for field in FIT_FIELDS}
    full = bootstrap_ed50(points)
    return {field: full.get(field) for field in FIT_FIELDS}


def gate_g1(s7_block: dict, gate_runs: list[str]) -> bool:
    """G1: S7 v2 pass tren moi R-D/R-O, with_log va no_log."""
    verdicts = []
    for mode in ("with_log", "no_log"):
        for run_id in gate_runs:
            verdicts.append(s7_block[mode][CLAIMED_CHANNEL][run_id]["pass"])
    if not verdicts or any(value is None for value in verdicts):
        return False
    return all(verdicts)


def gate_g2(g2_block: dict, zone: str = "detour") -> bool:
    """G2: khong co FP event muc act tren R-C khi co InterventionLog."""
    events = [cell["act_fp_events"] for cell in g2_block[zone].values()]
    if not events or any(value is None for value in events):
        return False
    return all(value == 0 for value in events)


def gate_g3(replay_o3: dict) -> bool:
    """G3: S11 bang 0 tren R-O, lay tu receipt 6R.6 v2."""
    runs = replay_o3["runs"]
    return bool(runs) and all(
        run["n_act_entries_in_suppression_window"] == 0 and run["passed"]
        for run in runs.values()
    )


def gate_g4(replay_o1: dict, replay_o2: dict, stability: dict) -> bool:
    """G4: S8, S9 va S12 cung pass theo receipt 6R.6."""
    s12 = stability.get("closed_here", {}).get("S12", {}).get("verdict")
    return bool(replay_o1["passed"]) and bool(replay_o2["passed"]) and s12 == "PASS"


def release_decision(g1: bool, g2: bool, g3: bool, g4: bool) -> dict:
    """Thieu bat ky gate nao thi fail-closed, khong phat hanh."""
    return {
        "G1": g1,
        "G2": g2,
        "G3": g3,
        "G4": g4,
        "released": bool(g1 and g2 and g3 and g4),
    }
