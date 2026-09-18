"""Manifest Phase 6R: toan ven, thu tu dang ky, va dung mot lan mo R-set."""
import json
import subprocess

import pytest

from ml import campaign as C

PATH = C.ROOT / "results/report/phase6r_manifest.json"


@pytest.fixture(scope="module")
def manifest():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["content_sha256"] == C.sha256_bytes(
        C.canonical_json(doc["content"]).encode()
    )
    return doc["content"]


def test_every_pinned_file_matches(manifest):
    drift = [
        relative
        for relative, sha256 in manifest["files_sha256"].items()
        if C.sha256_file(C.ROOT / relative) != sha256
    ]
    assert not drift, drift


def test_registration_commits_are_in_logical_order(manifest):
    commits = [item["commit"] for item in manifest["registration_commit_order"]]
    for earlier, later in zip(commits, commits[1:]):
        ok = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", earlier, later],
                cwd=C.ROOT,
            ).returncode
            == 0
        )
        assert ok, (earlier, later)


def test_r_set_opened_exactly_once(manifest):
    assert manifest["r_set_openings"] == 1


def test_acceptance_opened_after_prereg(manifest):
    paths = [item["path"] for item in manifest["registration_commit_order"]]
    assert paths.index("results/report/phase6r_acceptance_prereg.json") < paths.index(
        "results/report/phase6r_acceptance.json"
    ) < paths.index("results/report/phase6r_amendment_8.json")
