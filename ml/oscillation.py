#!/usr/bin/env python3
"""Frozen S7 v1 and purpose-derived S7 v2 oscillation definitions."""
from __future__ import annotations


SEVERITY = {"normal": 0, "suspect": 1, "act": 2}


def _collapse(sequence):
    return [
        state
        for index, state in enumerate(sequence)
        if index == 0 or state != sequence[index - 1]
    ]


def s7_v1_violations(states) -> int:
    """Frozen amendment-2 definition; do not change or reinterpret it."""
    sequence = _collapse(
        [state for state in states if state not in ("unknown", "warming_up")]
    )
    return sum(
        1
        for left, middle, right in zip(
            sequence, sequence[1:], sequence[2:]
        )
        if left == right and left in ("suspect", "act")
    )


def act_entries(states) -> int:
    """S7a: count entries into act on the raw sequence, including blind gaps."""
    return sum(
        1
        for index, state in enumerate(states)
        if state == "act" and (index == 0 or states[index - 1] != "act")
    )


def reescalations(states) -> int:
    """S7b: count severity increases after the sequence has decreased."""
    sequence = [
        SEVERITY[state]
        for state in _collapse([state for state in states if state in SEVERITY])
    ]
    went_down, count = False, 0
    for left, right in zip(sequence, sequence[1:]):
        if right < left:
            went_down = True
        elif right > left and went_down:
            count += 1
    return count


def s7_v2(states) -> dict:
    entries = act_entries(states)
    escalations = reescalations(states)
    return {
        "act_entries": entries,
        "reescalations": escalations,
        "pass": entries <= 1 and escalations == 0,
    }
