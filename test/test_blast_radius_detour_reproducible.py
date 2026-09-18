#!/usr/bin/env python3
"""Test tai lap: ban kinh detour KHONG duoc phu thuoc PYTHONHASHSEED.

`_alternate_switch_path` duyet BFS tren `_switch_graph`, ma cac lang gieng
duoc luu trong `set`. Khi co NHIEU duong ngan nhat bang nhau, thu tu duyet
mot `set` khong sap xep se phu thuoc hash randomization cua Python -> ban
kinh khac nhau giua cac lan chay -> receipt khong tai lap duoc. `sorted()`
trong `_alternate_switch_path` khoa thu tu do lai, va test nay khoa hanh vi
do lai truoc khi Phase 7 mo rong topology.
"""
from __future__ import annotations

import json
import subprocess
import sys

from ml import campaign as C

CODE = (
    "import json;"
    "from ml.blast_radius import Routing, radius_with_detour, _alternate_switch_path;"
    "from ml import campaign as C;"
    "r=Routing.load(C.ROOT/'ditto/routing_table.json');"
    "print(json.dumps({"
    "'radius': sorted(radius_with_detour(r, {'links': ['s1-s2'], 'flows': []})),"
    "'path': _alternate_switch_path(r, 's1-s2')}))"
)
SEEDS = ("0", "1", "42", "12345", "random")


def _run(seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", CODE],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin", "PYTHONPATH": str(C.ROOT)},
    )
    return result.stdout.strip()


def test_detour_radius_is_deterministic_across_hash_seeds():
    outputs = {seed: _run(seed) for seed in SEEDS}
    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "ban kinh detour phu thuoc hash seed -> receipt khong tai lap duoc: %s"
        % outputs
    )


def test_detour_corridor_is_the_expected_triangle_path():
    """Ghi lai hanh lang detour ma amendment 7 dua vao."""
    observed = json.loads(_run("0"))
    assert observed["path"] == ["s1", "s3", "s2"], observed["path"]
    added = set(observed["radius"]) - {
        "link-s1-s3", "link-s2-s3", "switch-s3"
    }
    assert {"link-s1-s3", "link-s2-s3", "switch-s3"} <= set(observed["radius"]), (
        "hanh lang detour thieu entity: %s" % observed["radius"]
    )
    assert added, "ban kinh goc bi mat"
