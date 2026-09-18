"""Mot lan quet sinh moi kenh nghiem thu; khong doc file va khong in.

v2 ghi moi tick thanh mot ``TickRow``. Moi metric la ham thuan cua ``RunTrace``;
khong metric nao duoc phep quay lai doc snapshot.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable

from ml.blast_radius import radius, radius_with_detour
from ml.flatten import flatten_snapshot
from ml.intervention_log import InMemoryInterventionLog, Intervention

ALARM_ZONE = frozenset({"suspect", "act"})

DERIVE = {
    "envelope_only": lambda reading: reading.envelope_suspect,
    "combined": lambda reading: reading.envelope_suspect or reading.cons_alarm,
}


def _num(value):
    """Chuyen None/NaN/bool thanh None: khong do duoc khac khong co bang chung."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value == value else None


def physical_evidence(snapshot: dict, loss_threshold: float):
    """Bang chung tri-state tren moi link, cung tick: True/False/None."""
    row = flatten_snapshot(snapshot)
    links = {key.split(".", 1)[0] for key in row if key.startswith("link-")}
    undetermined = False
    for link in links:
        loss = _num(row.get(link + ".traffic.lossPct"))
        drop = _num(row.get(link + ".traffic.qdiscDropDelta"))
        up = _num(row.get(link + ".status.state_up"))
        if (
            (loss is not None and loss > loss_threshold)
            or (drop is not None and drop > 0)
            or (up is not None and up == 0)
        ):
            return True
        if loss is None or drop is None or up is None:
            undetermined = True
    return None if undetermined else False


def build_log(meta: dict, routing, *, zone: str) -> InMemoryInterventionLog:
    """Tinh lai zone tu routing + targets; khong tin ban duy nhat trong sidecar."""
    if zone not in ("detour", "original"):
        raise ValueError(zone)
    radius_fn = radius_with_detour if zone == "detour" else radius
    log = InMemoryInterventionLog()
    for item in meta.get("interventions", []):
        if item["routing_sha256"] != routing.sha256:
            raise ValueError("routing SHA lech sidecar: %s" % item["id"])
        log.append(
            Intervention(
                id=item["id"],
                t_start=float(item["t_start"]),
                actor=item["actor"],
                action=item["action"],
                targets=item["targets"],
                blast_radius=radius_fn(routing, item["targets"]),
                routing_sha256=item["routing_sha256"],
            )
        )
    return log


@dataclass(frozen=True)
class FsmSpec:
    derive: str
    factory: Callable[[], object]


@dataclass
class TickRow:
    tick: int | None
    t_source: float | None
    t_available: float | None
    status: str
    k: int | None
    excess: float | None
    act: bool
    envelope_suspect: bool
    cons_alarm: bool
    cons_judgeable: bool
    cons_r_max: float | None
    cons_switch: str | None
    ev_strict: bool | None
    ev_sensitive: bool | None
    raw: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    at_risk: dict = field(default_factory=dict)
    probe: dict = field(default_factory=dict)


@dataclass
class RunTrace:
    run_id: str
    rows: list = field(default_factory=list)
    channels: tuple = ()


def run_one(
    run_id,
    snapshots,
    scorer,
    specs: dict[str, FsmSpec],
    residual_threshold: float,
    probes: dict | None = None,
) -> RunTrace:
    """Quet mot lan; ``probes`` lay them gia tri tu cung snapshot da flatten."""
    probes = probes or {}
    fsms = {name: spec.factory() for name, spec in specs.items()}
    if len({id(fsm) for fsm in fsms.values()}) != len(fsms):
        raise AssertionError("hai kenh dung chung mot DetectorFSM")
    trace = RunTrace(run_id=run_id, channels=tuple(specs))
    for snapshot in snapshots:
        reading = scorer.observe(snapshot)
        residual = bool(
            reading.cons_judgeable
            and reading.cons_r_max is not None
            and reading.cons_r_max > residual_threshold
        )
        if residual != bool(reading.cons_alarm):
            raise AssertionError(
                "cons_alarm lech dinh nghia prereg o tick %s" % reading.tick
            )
        row = TickRow(
            reading.tick,
            reading.t_source,
            _num(snapshot.get("t_cycle_end")),
            reading.status,
            reading.k,
            reading.excess,
            bool(reading.act),
            bool(reading.envelope_suspect),
            bool(reading.cons_alarm),
            bool(reading.cons_judgeable),
            reading.cons_r_max,
            reading.cons_switch,
            physical_evidence(snapshot, 1.0),
            physical_evidence(snapshot, 0.0),
        )
        if probes:
            flat = flatten_snapshot(snapshot)
            row.probe = {name: probe(flat) for name, probe in probes.items()}
        for name, spec in specs.items():
            fsm = fsms[name]
            alarm = bool(DERIVE[spec.derive](reading))
            row.raw[name] = reading.status == "scored" and (alarm or bool(reading.act))
            row.at_risk[name] = (
                reading.status == "scored" and fsm.state not in ALARM_ZONE
            )
            transition = fsm.step(dataclasses.replace(reading, suspect=alarm))
            row.state[name] = (
                transition.prev,
                transition.state,
                transition.changed,
                transition.cause,
            )
        trace.rows.append(row)
    return trace


GROUP_MODES = {
    "RD": ("with_log", "no_log"),
    "RO": ("with_log", "no_log"),
    "RC": ("with_log", "original", "no_log"),
    "RS": ("no_log",),
    "RN": ("no_log",),
}


def specs_for(group: str, meta: dict, routing, fsm_factory) -> dict[str, FsmSpec]:
    """Tao FSM doc lap; ten mode phan anh dung viec co hay khong co log."""
    logs = {}
    for mode in GROUP_MODES[group]:
        if mode == "no_log":
            logs[mode] = None
        elif mode == "original":
            logs[mode] = build_log(meta, routing, zone="original")
        elif mode == "with_log":
            # Corridor thay the chi la cau hinh dong bang cho link-state
            # admin_down. R-D giu link up, nen dung radius goc.
            configured_zone = "detour" if group in ("RO", "RC") else "original"
            logs[mode] = build_log(meta, routing, zone=configured_zone)
        else:
            raise ValueError("mode chua dang ky: %s" % mode)
    return {
        "%s@%s" % (channel, mode): FsmSpec(
            channel, lambda log=log: fsm_factory(log)
        )
        for channel in DERIVE
        for mode, log in logs.items()
    }
