#!/usr/bin/env python3
"""Khóa phạm vi phép đo jitter trước khi chạy trên raw R-S."""
from __future__ import annotations

import ast
import inspect
import json

from scripts import measure_tick_jitter as J


def test_protocol_is_fixed_to_three_rs_runs_and_1_5_seconds():
    assert J.THRESHOLD == 1.5
    assert J.RS_RUNS == (
        'RS-soak2M-s4001-r1',
        'RS-soak2M-s4002-r2',
        'RS-soak2M-s4003-r3',
    )


def test_delta_reader_uses_only_t_rel(tmp_path):
    path = tmp_path / 'synthetic.jsonl'
    path.write_text('\n'.join(json.dumps({'t_rel': value, 'secret': 'unused'})
                              for value in (0.0, 1.0, 2.6)) + '\n')
    times, deltas = J.times_and_deltas(path)
    assert times == [0.0, 1.0, 2.6]
    assert deltas == [1.0, 1.6]


def test_script_has_no_scorer_model_or_label_dependency():
    source = inspect.getsource(J)
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert 'ml.serve' not in imports
    assert 'ml.model' not in imports
    for forbidden in ('labels_from_events', 'EnvelopeModel', 'OnlineScorer'):
        assert forbidden not in source
