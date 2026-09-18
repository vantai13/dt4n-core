"""Hinh dang ket qua nghiem thu, co dinh truoc khi mo R-set."""
from __future__ import annotations

FSM_CHANNELS = ("envelope_only", "combined")
INCIDENT_FIELDS = ("detected", "first_tick", "t_detect_ms", "max_k")
S1S4_FIELDS = (
    "n_incidents",
    "n_detected",
    "detection_rate",
    "t_detect_p95_ms",
    "t_detect_max_ms",
    "n_censored_channels_left_envelope",
    "n_censored_no_channel_left_envelope",
)
S2_FIELDS = (
    "n_events",
    "at_risk_ticks",
    "exposure_hours",
    "rate_point_per_hour",
    "rate_upper_per_hour",
    "mtbfa_lower_minutes",
    "alpha_one_sided",
    "sensitivity_raw_consecutive_runs",
)
S10_COL = ("fp_ticks", "undetermined_ticks")
S7_FIELDS = ("act_entries", "reescalations", "pass", "v1_violations")
RESIDUAL_FIELDS = (
    "rho",
    "fault_ticks",
    "residual_fault_fraction",
    "background_ticks",
    "background_alarm_ticks",
    "alarm_ticks_all",
    "argmax_correct_ticks",
    "incremental_ticks",
    "residual_alarms_on_unscored_ticks",
)
F_KEYS = ("F1", "F2", "F3", "F4", "F5", "F6")


def _nulls(keys) -> dict:
    return {key: None for key in keys}


def skeleton(runs_by_group: dict[str, list[str]]) -> dict:
    """Tao skeleton tu matrix thiet ke, khong tu manifest ket qua."""
    rd, ro, rc = (
        runs_by_group["RD"],
        runs_by_group["RO"],
        runs_by_group["RC"],
    )
    rn = runs_by_group["RN"]

    def s10_run():
        return {
            "alarm_ticks": None,
            "raw_alarm_ticks": None,
            **{
                column: _nulls(S10_COL)
                for column in ("col_a", "col_b", "col_c")
            },
        }

    return {
        "S1_S4": {
            channel: {
                "summary": _nulls(S1S4_FIELDS),
                "per_incident": {
                    run_id: _nulls(INCIDENT_FIELDS) for run_id in rd
                },
            }
            for channel in FSM_CHANNELS
        },
        "S2_S3": {channel: _nulls(S2_FIELDS) for channel in FSM_CHANNELS},
        "S7": {
            mode: {
                channel: {
                    run_id: _nulls(S7_FIELDS) for run_id in rd + ro + rc
                }
                for channel in FSM_CHANNELS
            }
            for mode in ("with_log", "no_log")
        },
        "S10": {
            channel: {run_id: s10_run() for run_id in rn}
            for channel in FSM_CHANNELS
        },
        "G2": {
            zone: {
                run_id: {"act_fp_ticks": None, "act_fp_events": None}
                for run_id in rc
            }
            for zone in ("detour", "original")
        },
        "gates": _nulls(("G1", "G2", "G3", "G4", "released")),
        "residual": {
            "per_run": {run_id: _nulls(RESIDUAL_FIELDS) for run_id in rd},
            "refuted": _nulls(F_KEYS),
            "outcome": None,
        },
        "dose": {
            "axis_1": {
                channel: {
                    "points": {
                        run_id: _nulls(
                            ("separation", "separation_sidecar", "detected")
                        )
                        for run_id in rd
                    },
                    "fit": _nulls(
                        ("method", "ed50", "ci95", "n_converged", "n_boot")
                    ),
                }
                for channel in FSM_CHANNELS
            },
            "axis_2": {
                run_id: _nulls(("rho", "residual_detected")) for run_id in rd
            },
        },
        "process": _nulls(
            (
                "n_files_read",
                "n_acceptance_invocations",
                "git_head",
                "python",
                "numpy",
                "pandas",
            )
        ),
    }


def key_paths(obj, prefix: str = "") -> set[str]:
    if not isinstance(obj, dict):
        return set()
    out = set()
    for key, value in obj.items():
        path = prefix + "/" + str(key)
        out.add(path)
        out |= key_paths(value, path)
    return out


def leaves(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from leaves(value)
    else:
        yield obj


def assert_same_shape(skel: dict, filled: dict) -> None:
    extra = key_paths(filled) - key_paths(skel)
    missing = key_paths(skel) - key_paths(filled)
    if extra or missing:
        raise ValueError(
            "hinh dang lech skeleton: thua %s, thieu %s"
            % (sorted(extra)[:5], sorted(missing)[:5])
        )
