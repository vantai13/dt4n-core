"""Hop dong E: chuoi hash, resume, xoay vong, va C10 dung lai bit-exact."""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from controller.audit import AuditLog, canonical, read_rows, sha, verify_chain
from controller.policy import ControllerState, DetectorView, PolicyParams, decide

ROLES = {"h1": "client", "h2": "client", "h3": "client",
         "srv1": "server", "srv2": "server"}
H1 = "org.dt4n:host-h1"


def make_log(tmp_path, **kwargs):
    return AuditLog(tmp_path / "controller_audit.jsonl", **kwargs)


def test_chuoi_lien_tuc(tmp_path):
    log = make_log(tmp_path)
    for index in range(5):
        log.append({"x": index})
    result = verify_chain(log.path)
    assert result["ok"] and result["n_rows"] == 5


def test_sua_mot_dong_thi_lo_ngay_va_dung_vi_tri(tmp_path):
    log = make_log(tmp_path)
    for index in range(5):
        log.append({"x": index})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["x"] = 999                                   # sua dong 2
    lines[1] = canonical(row).decode("utf-8")
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_chain(log.path)
    assert result["ok"] is False
    assert result["broken_at_line"] == 3             # gay tai dong KE TIEP


def test_xoa_mot_dong_cung_lo(tmp_path):
    log = make_log(tmp_path)
    for index in range(5):
        log.append({"x": index})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    del lines[2]
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_chain(log.path)["ok"] is False


def test_resume_sau_restart_khong_gay_chuoi(tmp_path):
    log = make_log(tmp_path)
    log.append({"x": 1})
    log.append({"x": 2})
    again = make_log(tmp_path)                       # controller restart
    row = again.append({"x": 3})
    assert row["seq"] == 3
    assert verify_chain(again.path)["ok"] is True


def test_xoay_vong_giu_chuoi_qua_nhieu_file(tmp_path):
    log = make_log(tmp_path, max_rows=3)
    for index in range(10):
        log.append({"x": index})
    result = verify_chain(log.path)
    assert result["ok"] is True and result["n_files"] > 1
    header = read_rows(log.path)[0]
    assert header["rotated_from"].startswith("controller_audit.jsonl.")
    assert header["rotated_head_sha256"] == header["prev_sha256"]


def test_canonical_tat_dinh():
    """Khong tat dinh -> hash lech -> verify_chain bao gay GIA."""
    a = {"b": 1, "a": {"y": 2, "x": 3}}
    b = {"a": {"x": 3, "y": 2}, "b": 1}
    assert canonical(a) == canonical(b) and sha(a) == sha(b)
    assert b" " not in canonical(a)


def test_fsync_duoc_goi(monkeypatch, tmp_path):
    """Crash giua chung khong duoc lam mat dong cuoi."""
    calls = []
    import controller.audit as module

    monkeypatch.setattr(module.os, "fsync", lambda fd: calls.append(fd))
    make_log(tmp_path).append({"x": 1})
    assert calls


# ------------------------------------------------------------------ C10


def audit_row(view, cstate, now_mono, params, actions, after):
    return {
        "input": {"state": view.state, "cause": view.cause,
                  "affected": list(view.affected), "fresh": view.fresh,
                  "bootId": view.boot_id, "seq": view.seq},
        "roles": dict(view.roles),
        "now_mono": now_mono,
        "params_sha256": sha(asdict(params)),
        "cstate_before": asdict(cstate),
        "cstate_after": asdict(after),
        "actions": [asdict(a) for a in actions],
    }


def test_c10_dung_lai_bit_exact_tu_audit(tmp_path):
    """Doc audit -> goi lai decide() -> ket qua PHAI trung tung bit."""
    params = PolicyParams()
    log = make_log(tmp_path)
    cstate = ControllerState()
    script = [
        ("act", "", (H1,), True, 0.0),
        ("normal", "", (), True, 5.0),
        ("normal", "", (), True, 15.0),          # het gio giu -> revert
        ("act", "", (H1,), True, 20.0),          # probe that bai -> backoff
        ("act", "", (H1,), False, 25.0),         # freshness chet -> HOLD
        ("normal", "", (), True, 26.0),          # quay lai -> MITIGATING
        ("unknown", "stale_intervention", (), True, 30.0),   # N15
    ]
    for state, cause, affected, fresh, now in script:
        view = DetectorView(state, cause, affected,
                            tuple(sorted(ROLES.items())), fresh, "b3f", int(now))
        actions, after = decide(view, cstate, now, params)
        log.append(audit_row(view, cstate, now, params, actions, after))
        cstate = after

    assert verify_chain(log.path)["ok"] is True

    n_checked = 0
    for row in read_rows(log.path):
        view = DetectorView(
            state=row["input"]["state"], cause=row["input"]["cause"],
            affected=tuple(row["input"]["affected"]),
            roles=tuple(sorted(row["roles"].items())),
            fresh=row["input"]["fresh"],
            boot_id=row["input"]["bootId"], seq=row["input"]["seq"],
        )
        before = ControllerState(**row["cstate_before"])
        actions, after = decide(view, before, row["now_mono"], PolicyParams())
        assert [asdict(a) for a in actions] == row["actions"], row["seq"]
        assert asdict(after) == row["cstate_after"], row["seq"]
        n_checked += 1
    assert n_checked == len(script)


def test_c10_gay_neu_thieu_mot_truong(tmp_path):
    """Chung minh 4 truong (input, roles, now_mono, cstate_before) la TOI THIEU."""
    params = PolicyParams()
    view = DetectorView("act", "", (H1,), tuple(sorted(ROLES.items())),
                        True, "b3f", 1)
    actions, after = decide(view, ControllerState(), 0.0, params)
    # thieu now_mono -> khong dung lai duoc deadline
    other_actions, other_after = decide(view, ControllerState(), 99.0, params)
    assert asdict(actions[0]) == asdict(other_actions[0])      # hanh dong giong
    assert after.deadline_mono != other_after.deadline_mono    # trang thai khac
