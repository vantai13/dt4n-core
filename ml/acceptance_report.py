"""Loi thuan tuy dien skeleton nghiem thu 6R.7; khong I/O va khong in."""
from __future__ import annotations

from ml.acceptance_gates import (
    CLAIMED_CHANNEL,
    dose_fit,
    g2_run,
    gate_g1,
    gate_g2,
    gate_g3,
    gate_g4,
    release_decision,
)
from ml.acceptance_metrics import (
    amendment1_verdicts,
    incident,
    residual_run,
    s1_s4,
    s2_s3,
    s7,
    s10,
)
from ml.acceptance_skeleton import FSM_CHANNELS
from ml.acceptance_stats import DosePoint

RESIDUAL_DETECT_FRACTION = 0.50


def key(channel: str, mode: str) -> str:
    return "%s@%s" % (channel, mode)


def fill(
    groups: dict,
    traces: dict,
    metas: dict,
    extras: dict,
    external: dict,
    process: dict,
    *,
    cooldown_ticks: int,
) -> dict:
    """Dien toan bo skeleton tu RunTrace va du lieu da nap san."""
    rd, ro, rc, rn, rs = (groups[name] for name in ("RD", "RO", "RC", "RN", "RS"))

    incidents = {
        channel: {
            run_id: incident(
                traces[run_id], metas[run_id], key(channel, "with_log")
            )
            for run_id in rd
        }
        for channel in FSM_CHANNELS
    }
    s1_s4_block = {
        channel: {
            "summary": s1_s4(incidents[channel]),
            "per_incident": incidents[channel],
        }
        for channel in FSM_CHANNELS
    }

    rs_traces = [traces[run_id] for run_id in rs]
    s2_s3_block = {
        channel: s2_s3(rs_traces, key(channel, "no_log"))
        for channel in FSM_CHANNELS
    }

    s7_runs = list(rd) + list(ro) + list(rc)
    s7_block = {
        mode: {
            channel: {
                run_id: s7(
                    traces[run_id],
                    metas[run_id],
                    key(channel, mode),
                    cooldown_ticks,
                )
                for run_id in s7_runs
            }
            for channel in FSM_CHANNELS
        }
        for mode in ("with_log", "no_log")
    }

    s10_block = {
        channel: {
            run_id: s10(traces[run_id], key(channel, "no_log"))
            for run_id in rn
        }
        for channel in FSM_CHANNELS
    }

    g2_block = {
        "detour": {
            run_id: g2_run(
                traces[run_id],
                metas[run_id],
                key(CLAIMED_CHANNEL, "with_log"),
            )
            for run_id in rc
        },
        "original": {
            run_id: g2_run(
                traces[run_id],
                metas[run_id],
                key(CLAIMED_CHANNEL, "original"),
            )
            for run_id in rc
        },
    }

    per_run = {
        run_id: residual_run(traces[run_id], metas[run_id]) for run_id in rd
    }
    verdicts = amendment1_verdicts(
        per_run,
        s2_combined_upper=s2_s3_block["combined"]["rate_upper_per_hour"],
    )
    residual_block = {
        "per_run": per_run,
        "refuted": verdicts["refuted"],
        "outcome": verdicts["outcome"],
    }

    axis_1 = {}
    for channel in FSM_CHANNELS:
        points, cells = [], {}
        for run_id in rd:
            detected = incidents[channel][run_id]["detected"]
            separation = extras[run_id]["separation"]
            cells[run_id] = {
                "separation": separation,
                "separation_sidecar": extras[run_id]["separation_sidecar"],
                "detected": detected,
            }
            points.append(DosePoint(run_id, separation, detected))
        axis_1[channel] = {"points": cells, "fit": dose_fit(points)}

    axis_2 = {
        run_id: {
            "rho": per_run[run_id]["rho"],
            "residual_detected": (
                per_run[run_id]["residual_fault_fraction"] or 0.0
            )
            >= RESIDUAL_DETECT_FRACTION,
        }
        for run_id in rd
    }

    gates = release_decision(
        gate_g1(s7_block, list(rd) + list(ro)),
        gate_g2(g2_block, zone="detour"),
        gate_g3(external["replay_o3"]),
        gate_g4(
            external["replay_o1"], external["replay_o2"], external["stability"]
        ),
    )

    return {
        "S1_S4": s1_s4_block,
        "S2_S3": s2_s3_block,
        "S7": s7_block,
        "S10": s10_block,
        "G2": g2_block,
        "gates": gates,
        "residual": residual_block,
        "dose": {"axis_1": axis_1, "axis_2": axis_2},
        "process": process,
    }
