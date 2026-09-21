#!/usr/bin/env python3
"""Nghiem thu cung la ma nguon, nen no cung phai co test (Lesson 8.8).

Bon bat bien cua chinh cai cong:
  1. loai verdict thu tu co BON RAO, thieu mot rao thi TU DONG ha xuong FAIL
  2. dung lai bit-exact tren audit rong KHONG duoc PASS (bay khop == tong == 0)
  3. dung lai phai KIEM CHUOI TRUOC; chuoi gay -> khong PASS du du lieu con lai dep
  4. `--strict` phai coi INVALID o mot cong la that bai
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import accept_phase8 as A  # noqa: E402
import replay_phase8_decisions as R  # noqa: E402
from controller.audit import AuditLog  # noqa: E402


# ------------------------------------------------- 1. bon rao cua loai thu tu

def test_bon_rao_cua_pass_with_model_correction_deu_duoc_liet_ke():
    assert A.CORRECTION_GATES == (
        "cause_identified", "model_not_data", "known_answer_test",
        "declared_in_receipt_and_system_card")
    assert A.CORRECTED in A.VERDICTS


def test_ha_verdict_khi_thieu_rao_bang_cach_chay_that(tmp_path):
    """Chay that accept_phase8 voi known-answer test bi an di."""
    import subprocess

    hidden = ROOT / "test/test_phase8_acceptance_fixes.py"
    backup = tmp_path / "kat.py"
    backup.write_text(hidden.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "acc.json"
    try:
        hidden.unlink()
        subprocess.run(
            [sys.executable, "scripts/accept_phase8.py", "--out", str(out)],
            cwd=ROOT, capture_output=True, text=True, check=False)
        content = json.loads(out.read_text(encoding="utf-8"))["content"]
    finally:
        hidden.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    c6a = next(r for r in content["criteria"] if r["id"] == "C6-a")
    assert c6a["verdict"] == A.FAIL, "thieu known-answer test ma van CORRECTED"
    assert c6a["model_correction"]["known_answer_test"] is False
    assert content["acceptance_pass"] is False
    assert any("4 rao" in p for p in content["problems"])


# ------------------------------------------------- 2/3. bay cua C10

def test_audit_rong_KHONG_duoc_pass(tmp_path):
    """khop == tong == 0 va `0 == 0` la True -> PASS GIA. Bay kinh dien."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append({"kind": "inject", "t_wall": 1.0, "actions": []})   # khong phai decision
    result = R.replay(str(path))
    assert result["n_decisions"] == 0
    assert result["c10_pass"] is False


def test_chuoi_gay_thi_khong_dung_lai(tmp_path):
    """Kiem chuoi TRUOC. Dung lai mot audit da bi sua la vo nghia."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for index in range(3):
        log.append({"kind": "note", "t_wall": float(index)})
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["t_wall"] = 999.0                      # sua mot dong giua chung
    lines[1] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = R.replay(str(path))
    assert result["c10_pass"] is False
    assert "chuoi gay" in result["reason"]


def test_dung_lai_that_tren_audit_that():
    """Doi chung duong: tren audit 8.7 that, phai dung lai 100%."""
    import glob

    paths = sorted(glob.glob(str(ROOT / "logs/phase8_stability/flood_*/run_00.jsonl")))
    if not paths:
        import pytest

        pytest.skip("khong co audit 8.7 trong cay lam viec nay")
    result = R.replay(paths[0])
    assert result["n_decisions"] > 100
    assert result["c10_pass"] is True
    assert result["fraction"] == 1.0


# ------------------------------------------------- 4. --strict

def test_strict_coi_INVALID_o_cong_la_that_bai(tmp_path):
    import subprocess

    out = tmp_path / "acc.json"
    proc = subprocess.run(
        [sys.executable, "scripts/accept_phase8.py", "--strict", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, check=False)
    content = json.loads(out.read_text(encoding="utf-8"))["content"]
    gate_invalid = content["n_gate_invalid"]
    assert (proc.returncode == 0) == (gate_invalid == 0 and not content["problems"])


def test_moi_verdict_thuoc_dung_mot_trong_bon_loai(tmp_path):
    import subprocess

    out = tmp_path / "acc.json"
    subprocess.run([sys.executable, "scripts/accept_phase8.py", "--out", str(out)],
                   cwd=ROOT, capture_output=True, text=True, check=False)
    content = json.loads(out.read_text(encoding="utf-8"))["content"]
    assert content["criteria"]
    for row in content["criteria"]:
        assert row["verdict"] in A.VERDICTS, row
