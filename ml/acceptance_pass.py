"""Mot lan quet sinh ca ba kenh nghiem thu; khong doc file va khong in."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

ALARM_ZONE = frozenset({"suspect", "act"})

CHANNELS = {
    "envelope_only": lambda reading: reading.envelope_suspect,
    "combined": lambda reading: reading.envelope_suspect or reading.cons_alarm,
}


@dataclass
class ChannelTrace:
    states: list = field(default_factory=list)
    event_ticks: list = field(default_factory=list)
    at_risk_ticks: int = 0


@dataclass
class RunTrace:
    run_id: str
    n_snapshots: int = 0
    statuses: dict = field(default_factory=dict)
    channels: dict = field(default_factory=dict)
    residual_alarm_ticks: list = field(default_factory=list)
    residual_judgeable_ticks: int = 0


def run_one(run_id, snapshots, scorer, fsm_factory, residual_threshold: float) -> RunTrace:
    trace = RunTrace(run_id=run_id, n_snapshots=len(snapshots))
    fsms = {name: fsm_factory() for name in CHANNELS}
    if len({id(fsm) for fsm in fsms.values()}) != len(fsms):
        raise AssertionError("hai kenh dung chung mot DetectorFSM")
    for name in CHANNELS:
        trace.channels[name] = ChannelTrace()

    for snapshot in snapshots:
        reading = scorer.observe(snapshot)
        trace.statuses[reading.status] = trace.statuses.get(reading.status, 0) + 1

        residual = bool(
            reading.cons_judgeable
            and reading.cons_r_max is not None
            and reading.cons_r_max > residual_threshold
        )
        if residual != bool(reading.cons_alarm):
            raise AssertionError("cons_alarm lech dinh nghia prereg o tick %s" % reading.tick)
        if reading.cons_judgeable:
            trace.residual_judgeable_ticks += 1
        if residual:
            trace.residual_alarm_ticks.append(reading.tick)

        for name, derive in CHANNELS.items():
            fsm, channel = fsms[name], trace.channels[name]
            derived = dataclasses.replace(reading, suspect=bool(derive(reading)))
            if reading.status == "scored" and fsm.state not in ALARM_ZONE:
                channel.at_risk_ticks += 1
            transition = fsm.step(derived)
            channel.states.append(
                (transition.tick, transition.prev, transition.state, transition.cause)
            )
            if (
                transition.changed
                and transition.state in ALARM_ZONE
                and transition.prev not in ALARM_ZONE
            ):
                channel.event_ticks.append(transition.tick)
    return trace
