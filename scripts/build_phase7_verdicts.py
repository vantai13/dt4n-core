#!/usr/bin/env python3
"""Suy phan quyet Phase 7 tu receipt NGHIEM THU da niem phong (Lesson 7.7 phan 2, buoc 3).

Tu choi neu: index/receipt bi sua, receipt khong sinh tu commit phase-7-frozen,
hoac logic 6R da troi. Khong doc raw, khong cham lai, khong ai go tay.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from measurements.phase7_verdicts import derive   # noqa: E402
from ml import campaign as C                       # noqa: E402

R = C.ROOT / "results/report"
ACC = R / "phase7_acceptance"
OUT = R / "phase7_verdicts.json"
FILE_OF = {"s12": "phase7_s12_live.json", "e2e": "phase7_e2e_latency.json", "s11": "phase7_s11_live.json",
           "contention": "phase7_contention.json", "soak": "phase7_soak_live_v2.json"}


def sealed(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if C.sha256_bytes(C.canonical_json(doc["content"]).encode()) != doc["content_sha256"]:
        raise SystemExit("receipt bi sua: %s" % path)
    return doc


def main() -> int:
    if OUT.exists():
        print("[P7-V] da ton tai, khong ghi de")
        return 1
    index = sealed(ACC / "index.json")["content"]
    frozen = subprocess.run(["git", "rev-list", "-n", "1", "phase-7-frozen"], cwd=C.ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    if index["frozen_commit"] != frozen:
        raise SystemExit("receipt KHONG sinh tu phase-7-frozen")
    rc, provenance = {}, {}
    for step, name in FILE_OF.items():
        rec = index["steps"].get(step)
        if not rec or rec["rc"] != 0 or name not in rec["receipts"]:
            continue                                              # thieu -> NO_DATA, khong phai PASS
        if C.sha256_file(ACC / name) != rec["receipts"][name] or rec["commit"] != frozen:
            raise SystemExit("receipt %s khong khop index/commit" % name)
        rc[step] = sealed(ACC / name)["content"]
        provenance[step] = {"file": "phase7_acceptance/" + name, "sha256": rec["receipts"][name],
                            "started_utc": rec["started_utc"]}
    m6 = sealed(R / "phase6r_manifest.json")["content"]["files_sha256"]
    freeze = sealed(R / "phase7_freeze.json")["content"]
    pins_ok = all(C.sha256_file(C.ROOT / p) == m6[p] == sha for p, sha in freeze["files_sha256"]["pinned_6r"].items())
    history = {
        "S6": [{"when": "7.6", "file": "phase7_soak_live.json", "verdict": "FAIL", "delta_mib": 2.77,
                "cause": "bo dem nghien cuu timeline chay mac dinh (tracemalloc 1725 KiB)"},
               {"when": "7.7p1", "file": "phase7_soak_live_v2.json", "prereg": "phase7_s6_v2_prereg.json"}],
        "S11": [{"when": "7.6", "note": "log_late ban dau lech 2 tick do off-by-one harness; chay bo sung "
                                        "phase7_s11_live_offbyone_fix.json"}],
        "S12": [{"when": "6R", "verdict": "DEFERRED", "why": "amendment 4: thuoc tinh tich hop"}],
    }
    content = {"verdict_id": "DT4N-P7-VERDICTS", "frozen_commit": frozen, "receipts": provenance,
               "pins_6r_ok": pins_ok,
               **derive(sealed(R / "phase6r_slo.json")["content"], sealed(R / "phase6r_verdicts.json")["content"],
                        rc, pins_ok, history)}
    C.atomic_json(OUT, {"content": content,
                        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
                        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(json.dumps(content["gates"]), "fails:", content["fails_declared"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
