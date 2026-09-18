#!/usr/bin/env python3
"""So TROI LECH pin cho MOI tai lieu ghim SHA cua Phase 6R.

Hai khang dinh doc lap:

  (1) XUAT XU  -- pin phai khop byte tai COMMIT LICH SU cua chinh tai lieu do.
                  Khong the lam gia: phai viet lai git history moi qua duoc.
  (2) KHAI BAO -- moi file da pin ma NAY khac HEAD phai duoc mot tai lieu
                  NIEM PHONG SAU DO nhan trach nhiem (planned_changes/changes,
                  hoac re-pin voi SHA khac).

(2) la cai bay (tripwire) bi mat khi test_phase6r_amendment3 doi sang dang
lich su o commit ecfad7b. Troi lech duoc phep; troi lech IM LANG thi khong.

Pham vi la MOI `results/report/phase6r_*.json`, khong chi amendment: prereg va
receipt cung ghim code (`phase6r_stability_prereg.code_sha256`,
`phase6r_stability_v2.implementation_sha256`), va prereg nghiem thu 6R.7 se
ghim toan bo cau hinh dong bang. Neu so chi quet amendment thi dung nhung pin
quan trong nhat lai nam ngoai co che phat hien.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from ml import campaign as C

REPORT = C.ROOT / "results/report"

# Moi tai lieu Phase 6R deu duoc quet. Tai lieu khong ghim gi se bi skip.
PIN_DOCS = "phase6r_*.json"

PIN_KEYS = (
    "code_sha256",
    "code_at_registration_sha256",
    "implementation_sha256",
    "artifacts_sha256",
    "pinned_artifacts_sha256",
    "pinned_receipt_sha256",
    "evidence_file_sha256",
    "upstream_sha256",
)
# Mot so tai lieu ghim code bang cap (duong dan, sha) roi thay vi mot map,
# vi du amendment 7 ghim cong cu chan doan: diagnosis.tool + diagnosis.tool_sha256.
SCALAR_PINS = (("diagnosis", "tool", "tool_sha256"),)
# Khoa the hien mot tai lieu NHAN TRACH NHIEM sua mot duong dan.
CLAIM_KEYS = ("planned_changes", "changes")
# Khoa pin cung la khai bao trach nhiem KHI SHA khac pin cu (da re-pin sau sua).
REPIN_KEYS = ("code_sha256", "implementation_sha256")


def _git(*args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=C.ROOT, capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else ""


def _sealing_commit(relative: str) -> tuple[str | None, int]:
    """Commit cuoi da sua tai lieu nay -- tuc commit NIEM PHONG no, va thoi diem."""
    out = _git("log", "-1", "--format=%H %ct", "--", relative).split()
    return (out[0], int(out[1])) if len(out) == 2 else (None, 0)


def _registration_commit(relative: str) -> str | None:
    """Commit da THEM tai lieu nay -- tuc commit dang ky no."""
    lines = _git("log", "--diff-filter=A", "--format=%H", "--", relative).split()
    return lines[-1] if lines else None


def _resolve(relative: str):
    """Pin cua `evidence_file_sha256` dung ten file tuong doi voi results/report."""
    direct = C.ROOT / relative
    if direct.exists() or "/" in relative:
        return direct
    return REPORT / relative


def _pins_of(content: dict) -> dict[str, str]:
    pins: dict[str, str] = {}
    for key in PIN_KEYS:
        value = content.get(key)
        if isinstance(value, dict):
            pins.update({k: v for k, v in value.items() if isinstance(v, str)})
    for section, path_key, sha_key in SCALAR_PINS:
        block = content.get(section)
        if isinstance(block, dict) and block.get(path_key) and block.get(sha_key):
            pins[block[path_key]] = block[sha_key]
    return pins


def _documents():
    """Moi tai lieu Phase 6R ghim SHA, xep theo thoi diem niem phong."""
    out = []
    for path in sorted(REPORT.glob(PIN_DOCS)):
        relative = str(path.relative_to(C.ROOT))
        document = json.loads(path.read_text(encoding="utf-8"))
        content = document.get("content", document)
        if not isinstance(content, dict):
            continue
        pins = _pins_of(content)
        if not pins:
            continue
        seal, sealed_at = _sealing_commit(relative)
        git_block = content.get("git") or {}
        out.append(
            {
                "name": path.name,
                "relative": relative,
                "content": content,
                "pins": pins,
                # Amendment khai git head cua chinh no; prereg/receipt thi khong,
                # va commit niem phong la moc lich su tuong duong.
                "head": git_block.get("head") or content.get("git_head"),
                "dirty": set(git_block.get("dirty_files") or []),
                "registration": _registration_commit(relative),
                "seal": seal,
                "sealed_at": sealed_at,
            }
        )
    return sorted(out, key=lambda d: (d["sealed_at"], d["name"]))


DOCUMENTS = _documents()
IDS = [d["name"].replace("phase6r_", "").replace(".json", "") for d in DOCUMENTS]


def _blob_sha(commit: str, relative: str) -> str | None:
    result = subprocess.run(
        ["git", "show", "%s:%s" % (commit, relative)],
        cwd=C.ROOT,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return C.sha256_bytes(result.stdout)


def test_0_scope_covers_every_pinning_document():
    """Neu them tai lieu ghim SHA moi (vi du prereg nghiem thu 6R.7) ma khoa pin
    cua no khong nam trong PIN_KEYS, test nay bat duoc."""
    found = {d["name"] for d in DOCUMENTS}
    for required in (
        "phase6r_amendment_%d.json" % n for n in range(1, 8)
    ):
        assert required in found, "%s khong duoc quet" % required
    for required in (
        "phase6r_stability_prereg.json",
        "phase6r_stability.json",
        "phase6r_stability_v2.json",
        "phase6r_equivalence.json",
        "phase6r_slo.json",
    ):
        assert required in found, "%s ghim SHA nhung khong duoc quet" % required
    unscanned = []
    for path in sorted(REPORT.glob(PIN_DOCS)):
        document = json.loads(path.read_text(encoding="utf-8"))
        content = document.get("content", document)
        if not isinstance(content, dict):
            continue
        keys = [
            k
            for k, v in content.items()
            if "sha256" in k and isinstance(v, dict) and path.name not in found
        ]
        if keys:
            unscanned.append((path.name, keys))
    assert not unscanned, "tai lieu ghim SHA nhung khoa khong duoc nhan: %s" % unscanned


@pytest.mark.parametrize("d", DOCUMENTS, ids=IDS)
def test_1_pin_matches_bytes_at_a_historical_commit(d):
    """XUAT XU: khong the noi 'pin cua toi von la vay' sau khi doi code."""
    mismatched = []
    for relative, digest in sorted(d["pins"].items()):
        target = _resolve(relative)
        if not target.is_relative_to(C.ROOT):
            continue
        repo_path = str(target.relative_to(C.ROOT))
        # Moc lich su hop le cho tai lieu nay, theo thu tu uu tien.
        candidates = [c for c in (d["head"], d["seal"], d["registration"]) if c]
        if any(_blob_sha(commit, repo_path) == digest for commit in candidates):
            continue
        # Mot pin co the tro vao file con UNTRACKED tai head da khai (no phai
        # nam trong dirty_files) va duoc commit cung luc dang ky -- da nam
        # trong `candidates`. Con lai la lech thuc su.
        mismatched.append(repo_path)
    assert not mismatched, (
        "%s: pin KHONG khop byte tai bat ky commit lich su nao cua chinh no "
        "(head=%s, seal=%s) -> pin sai hoac history da bi viet lai: %s"
        % (
            d["name"],
            (d["head"] or "-")[:8],
            (d["seal"] or "-")[:8],
            mismatched,
        )
    )


def _claimed_after(sealed_at: int) -> set[str]:
    """Duong dan ma mot tai lieu NIEM PHONG SAU thoi diem nay nhan trach nhiem."""
    claimed: set[str] = set()
    for d in DOCUMENTS:
        if d["sealed_at"] <= sealed_at:
            continue
        for key in CLAIM_KEYS:
            value = d["content"].get(key)
            if isinstance(value, dict):
                claimed |= set(value)
    return claimed


def _repinned_after(sealed_at: int, relative: str, digest: str) -> bool:
    """Mot tai lieu sau da ghim LAI duong dan nay voi SHA KHAC -> da nhan viec sua."""
    for d in DOCUMENTS:
        if d["sealed_at"] <= sealed_at:
            continue
        for key in REPIN_KEYS:
            value = d["content"].get(key)
            if isinstance(value, dict) and value.get(relative) not in (None, digest):
                return True
    return False


@pytest.mark.parametrize("d", DOCUMENTS, ids=IDS)
def test_2_every_drift_is_claimed_by_a_later_document(d):
    """KHAI BAO: troi lech duoc phep, troi lech IM LANG thi khong."""
    claimed = _claimed_after(d["sealed_at"])
    undeclared = []
    for relative, digest in sorted(d["pins"].items()):
        target = _resolve(relative)
        if not target.exists():
            undeclared.append("%s (DA XOA)" % relative)
        elif C.sha256_file(target) != digest:
            if relative in claimed or _repinned_after(d["sealed_at"], relative, digest):
                continue
            undeclared.append(relative)
    assert not undeclared, (
        "%s: nhung file da pin nay khac HEAD ma KHONG tai lieu nao niem phong sau "
        "do nhan trach nhiem: %s\n-> hoac hoan nguyen thay doi, hoac them chung "
        "vao planned_changes cua mot amendment moi." % (d["name"], undeclared)
    )


def test_3_ledger_is_printed_for_the_record(capsys):
    """In so troi lech. Khong assert; de nguoi doc bao cao tra cuu."""
    lines = []
    for d in DOCUMENTS:
        claimed = _claimed_after(d["sealed_at"])
        label = d["name"].replace("phase6r_", "").replace(".json", "")
        for relative, digest in sorted(d["pins"].items()):
            target = _resolve(relative)
            if not target.exists():
                lines.append("%-22s %-42s DA XOA" % (label, relative))
            elif C.sha256_file(target) != digest:
                how = (
                    "KHAI BAO"
                    if relative in claimed
                    else "RE-PIN"
                    if _repinned_after(d["sealed_at"], relative, digest)
                    else "CHUA KHAI"
                )
                lines.append("%-22s %-42s %s" % (label, relative, how))
    body = "\n".join(lines) if lines else "(khong co troi lech)"
    with capsys.disabled():
        print("\n--- SO TROI LECH PIN (Phase 6R) ---")
        print("tai lieu duoc quet: %d" % len(DOCUMENTS))
        print(body)
        print("--- het so ---")
