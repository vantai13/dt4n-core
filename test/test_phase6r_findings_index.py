#!/usr/bin/env python3
"""Every Phase 6R finding must be cited, by its anchor, AFTER it was recorded.

The pin ledger stops silent SHA drift; this stops silent FINDING drift. A
finding recorded in one lesson and never cited again is how F-6R4-1 became the
S11 failure and how the probe v2 mass balance became an 'unknown mechanism'.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from ml import campaign as C

INDEX = C.ROOT / "results/report/phase6r_findings_index.json"
DOCUMENT = json.loads(INDEX.read_text(encoding="utf-8"))
FINDINGS = DOCUMENT["content"]["findings"]


def _first_commit_time(relative: str) -> int | None:
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ct", "--", relative],
        cwd=C.ROOT, capture_output=True, text=True,
    ).stdout.split()
    return int(out[-1]) if out else None


def _last_commit_time(relative: str) -> int | None:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", relative],
        cwd=C.ROOT, capture_output=True, text=True,
    ).stdout.split()
    return int(out[0]) if out else None


def test_index_hash_is_self_consistent():
    assert DOCUMENT["content_sha256"] == C.sha256_bytes(
        C.canonical_json(DOCUMENT["content"]).encode()
    )


def test_ids_are_unique():
    ids = [f["id"] for f in FINDINGS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("f", FINDINGS, ids=lambda f: f["id"])
def test_finding_is_anchored_in_its_source(f):
    assert f["status"] in DOCUMENT["content"]["statuses"]
    source = C.ROOT / f["source"]
    assert source.exists(), "%s: source missing" % f["id"]
    assert f["anchor"] in source.read_text(encoding="utf-8"), (
        "%s: anchor %r not found in its source" % (f["id"], f["anchor"])
    )


@pytest.mark.parametrize("f", FINDINGS, ids=lambda f: f["id"])
def test_finding_is_cited_later_elsewhere(f):
    """A finding nobody cites after recording it is a finding waiting to be forgotten."""
    cited = [r for r in f["referenced_by"] if r != f["source"]]
    assert cited, "%s is cited nowhere outside its source" % f["id"]
    source_time = _first_commit_time(f["source"])
    for relative in cited:
        target = C.ROOT / relative
        assert target.exists(), "%s: citing document %s missing" % (f["id"], relative)
        assert f["anchor"] in target.read_text(encoding="utf-8"), (
            "%s: %s claims to cite it but the anchor %r is absent"
            % (f["id"], relative, f["anchor"])
        )
        cited_time = _last_commit_time(relative)
        # an uncommitted citing document is newer than anything committed
        if source_time is not None and cited_time is not None:
            assert cited_time >= source_time, (
                "%s: %s was last written before the finding was recorded"
                % (f["id"], relative)
            )
