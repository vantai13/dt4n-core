#!/usr/bin/env python3
"""Chien dich NGHIEM THU Phase 7 tren cau hinh DONG BANG (Lesson 7.7 phan 2, buoc 2).

    Terminal 1: cd dashboard && npm run dev           (phuc vu dashboard/src DA DONG BANG)
    Terminal 2: sudo -E .venv/bin/python scripts/run_phase7_acceptance.py [--steps s12,e2e,s11,contention,soak]

Moi buoc:
  1. KIEM DONG BANG: HEAD == tag phase-7-frozen, worktree sach, SHA moi file == phase7_freeze.json
  2. BAO DAM CONTROLLER: moi harness ket thuc bang `mn -c`, lenh nay giet ca ryu-manager; khong co
     controller o 6653 thi harness TREO (da mat 30 phut o 7.6) -> khoi dong lai truoc MOI buoc
  3. chay harness (CUNG script, CUNG tham so da dung o 7.4-7.7p1)
  4. CAT receipt vao results/report/phase7_acceptance/, KHOI PHUC artifact lich su (git checkout)
Ket thuc: index.json niem phong (commit, lenh, ma thoat, SHA tung receipt).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import campaign as C   # noqa: E402

REPORT = C.ROOT / "results/report"
DEST = REPORT / "phase7_acceptance"
FREEZE = REPORT / "phase7_freeze.json"
TAG = "phase-7-frozen"
CONTROLLER_PORT = 6653
CONTROLLER_LOG = C.ROOT / "logs/phase7_acceptance_ryu.log"
STEPS = {
    "s12": (["scripts/measure_phase7_s12_live.py", "--trials", "20"], ["phase7_s12_live.json"]),
    "e2e": (["scripts/measure_phase7_e2e.py", "--trials", "25"],
            ["phase7_e2e_latency.json", "phase7_e2e_latency.png"]),
    "s11": (["scripts/run_phase7_s11_live.py", "--reps", "4", "--lease"],
            ["phase7_s11_live.json", "phase7_residual_intervention.json"]),
    "contention": (["scripts/run_phase7_contention.py", "--block", "300"], ["phase7_contention.json"]),
    "soak": (["scripts/soak_phase7_live_v2.py"], ["phase7_soak_live_v2.json"]),
}
NEEDS_UI = {"s12", "e2e", "contention", "soak"}


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=C.ROOT, capture_output=True, text=True, check=True).stdout.strip()


def check_frozen() -> str:
    head, tagged = git("rev-parse", "HEAD"), git("rev-list", "-n", "1", TAG)
    if head != tagged:
        raise SystemExit("KHONG DONG BANG: HEAD %s != %s %s" % (head[:8], TAG, tagged[:8]))
    dirty = [l for l in git("status", "--porcelain").splitlines()
             if l.strip() and "results/report/phase7_acceptance/" not in l]
    if dirty:
        raise SystemExit("KHONG DONG BANG: worktree ban %s" % dirty[:5])
    frozen = json.loads(FREEZE.read_text())["content"]["files_sha256"]
    drift = [p for g in frozen.values() for p, sha in g.items() if C.sha256_file(C.ROOT / p) != sha]
    if drift:
        raise SystemExit("KHONG DONG BANG: file troi %s" % drift[:5])
    return head


def ui_up(url="http://127.0.0.1:5173/") -> bool:
    try:
        return urllib.request.urlopen(url, timeout=3).status == 200
    except Exception:
        return False


def controller_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", CONTROLLER_PORT), timeout=1):
            return True
    except OSError:
        return False


def ensure_controller(ryu_manager: str) -> str:
    """'already_up' | 'started'. Controller la dieu kien cua MOI harness, khong phai bien do."""
    if controller_up():
        return "already_up"
    if not ryu_manager or not Path(ryu_manager).exists():
        raise SystemExit("khong co controller o %d va khong tim thay ryu-manager (--ryu-manager / "
                         "DT4N_RYU_MANAGER)" % CONTROLLER_PORT)
    CONTROLLER_LOG.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([ryu_manager, "mininet.controller_static", "--ofp-tcp-listen-port", str(CONTROLLER_PORT)],
                     cwd=C.ROOT, stdout=open(CONTROLLER_LOG, "a"), stderr=subprocess.STDOUT,
                     start_new_session=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if controller_up():
            return "started"
        time.sleep(0.5)
    raise SystemExit("ryu-manager khong len o %d sau 60 s (xem %s)" % (CONTROLLER_PORT, CONTROLLER_LOG))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--ryu-manager", default=os.environ.get("DT4N_RYU_MANAGER") or shutil.which("ryu-manager"))
    args = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    index_path = DEST / "index.json"
    index = json.loads(index_path.read_text())["content"] if index_path.exists() else {"steps": {}}
    for step in args.steps.split(","):
        cmd, outputs = STEPS[step]
        head = check_frozen()                                   # KIEM LAI truoc MOI buoc
        index.setdefault("frozen_commit", head)
        if index["frozen_commit"] != head:
            raise SystemExit("commit doi giua cac buoc: %s != %s" % (head, index["frozen_commit"]))
        if step in NEEDS_UI and not ui_up():
            raise SystemExit("buoc %s can dashboard: chay `npm run dev` truoc" % step)
        controller = ensure_controller(args.ryu_manager)
        t0 = datetime.now(timezone.utc).isoformat(timespec="seconds")
        m0 = time.monotonic()
        rc = subprocess.run([sys.executable, *cmd], cwd=C.ROOT).returncode
        rec = {"cmd": cmd, "rc": rc, "started_utc": t0, "minutes": round((time.monotonic() - m0) / 60, 1),
               "commit": head, "controller": controller, "receipts": {}}
        for name in outputs:
            src = REPORT / name
            if rc == 0 and src.exists():
                shutil.copy2(src, DEST / name)
                rec["receipts"][name] = C.sha256_file(DEST / name)
            subprocess.run(["git", "checkout", "--", str(src.relative_to(C.ROOT))], cwd=C.ROOT,
                           capture_output=True)                  # tra artifact LICH SU ve nguyen trang
        index["steps"][step] = rec
        C.atomic_json(index_path, {"content": index,
                                   "content_sha256": C.sha256_bytes(C.canonical_json(index).encode()),
                                   "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print("[7.7] %-10s rc=%d %.1f phut (controller %s)" % (step, rc, rec["minutes"], controller), flush=True)
        if rc != 0:
            print("[7.7] DUNG: buoc %s loi dung cu/he (rc=%d). Ghi lai, KHONG tu chay tiep." % (step, rc))
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
