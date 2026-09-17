#!/usr/bin/env python3
"""Exhaustive logical comparison of frozen S7 v1 and purpose-derived v2."""
from __future__ import annotations

from itertools import product

import pytest

from ml.oscillation import act_entries, reescalations, s7_v1_violations, s7_v2

N, S, A, U = "normal", "suspect", "act", "unknown"


@pytest.mark.parametrize(
    "sequence", [[A, S, N, A], [S, N, A], [N, S, N, A]]
)
def test_v1_misses_dangerous_reescalation(sequence):
    assert s7_v1_violations(sequence) == 0
    assert not s7_v2(sequence)["pass"]


def test_v1_flags_monotone_deescalation_v2_allows():
    sequence = [N, S, A, U, S, N]
    assert s7_v1_violations(sequence) == 1
    assert s7_v2(sequence)["pass"]


def test_act_reentry_across_blind_tick_is_counted():
    sequence = [N, S, A, U, U, S, A, N]
    assert act_entries(sequence) == 2
    assert not s7_v2(sequence)["pass"]


@pytest.mark.parametrize(
    "sequence,expected",
    [
        ([N, S, A, S, N], True),
        ([N, S, N], True),
        ([N, S, N, S], False),
        ([N, A, N], True),
        ([N, S, A, A, A, N], True),
        ([S, A, S, A], False),
    ],
)
def test_v2_truth_table(sequence, expected):
    assert s7_v2(sequence)["pass"] is expected


def test_v2_is_never_looser_except_monotone_act_to_suspect():
    """Enumerate every non-repeating sequence of length three and four."""
    for length in (3, 4):
        for sequence in product((N, S, A), repeat=length):
            collapsed = [
                state
                for index, state in enumerate(sequence)
                if index == 0 or state != sequence[index - 1]
            ]
            if len(collapsed) != length:
                continue
            if s7_v1_violations(collapsed) and s7_v2(collapsed)["pass"]:
                assert reescalations(collapsed) == 0
                assert act_entries(collapsed) <= 1
                assert any(
                    left == A and right == S
                    for left, right in zip(collapsed, collapsed[1:])
                )
