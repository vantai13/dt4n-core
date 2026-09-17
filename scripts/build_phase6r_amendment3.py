#!/usr/bin/env python3
"""Pre-register purpose-derived S7 v2 and Phase 8 release gates."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_amendment_3.json"
R_CAMPAIGN_DIR = C.ROOT / "data/phase6r"
CODE = ("ml/oscillation.py", "test/test_oscillation.py", "ml/fsm.py")
ARTIFACTS = (
    "results/report/phase6r_slo.json",
    "results/report/phase6r_amendment_2.json",
    "results/report/phase6r_fsm.json",
)
ALLOWED_DIRTY = {
    "scripts/build_phase6r_amendment3.py",
    "test/test_phase6r_amendment3.py",
    "results/report/phase6r_amendment_3.json",
}


def git_state() -> dict:
    output = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    dirty = sorted(line[3:] for line in output.splitlines() if line)
    illegal = [
        path
        for path in dirty
        if path not in ALLOWED_DIRTY
        and not path.startswith("logs/")
        and path != "results/report/feature_audit.csv"
    ]
    if illegal:
        raise RuntimeError("commit truoc khi dang ky: %s" % illegal)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"head": head, "dirty_files": dirty}


def build_content() -> dict:
    if R_CAMPAIGN_DIR.exists():
        raise RuntimeError("R-campaign da thu: qua muon de dang ky")
    amendment2 = json.loads(
        (REPORT / "phase6r_amendment_2.json").read_text(encoding="utf-8")
    )
    fsm = json.loads(
        (REPORT / "phase6r_fsm.json").read_text(encoding="utf-8")
    )
    if fsm["content"]["prediction_checks"]["P4_s7_violations"] is not False:
        raise RuntimeError("trang thai P4 khong nhu da ghi")
    return {
        "amendment_id": "DT4N-P6R-AMENDMENT-3",
        "amends": {
            "amendment_2_sha256": amendment2["content_sha256"],
            "fsm_receipt_sha256": fsm["content_sha256"],
        },
        "git": git_state(),
        "artifacts_sha256": {
            path: C.sha256_file(C.ROOT / path) for path in ARTIFACTS
        },
        "code_sha256": {path: C.sha256_file(C.ROOT / path) for path in CODE},
        "record_kept": {
            "amendment_2_P4": "KHONG DAT tren replay tap test; ket qua nay KHONG bi cham lai boi dinh nghia moi",
            "fsm_release_status_before_this": "chua phat hanh cho Phase 8",
        },
        "timing_and_knowledge": {
            "noticed_after": "P4 khong dat (2 run shift, no_log: suspect->act->[unknown]->suspect->normal)",
            "justification_source": "bang chan ly LOGIC tren moi chuoi 3-4 trang thai (test/test_oscillation.py), khong dung du lieu",
            "posthoc_exploratory_on_spent_test": "v2 dat 16/16 (8 run x 2 che do); KHONG phai bang chung, chi de minh bach",
            "r_campaign_collected": False,
        },
        "s7_v2": {
            "module": "ml.oscillation.s7_v2",
            "window": "giu nguyen amendment 2: [inject+1, revert+cooldown_ticks]",
            "S7a": "so lan VAO act <= 1, dem tren chuoi THO (unknown CO trong chuoi) -> rui ro cap quyen hanh dong hai lan",
            "S7b": "muc nghiem trong normal<suspect<act, bo unknown/warming_up, gop lap: KHONG tang sau khi da giam",
            "defects_of_v1_by_logic": {
                "false_negative": [
                    "act,suspect,normal,act",
                    "suspect,normal,act",
                    "normal,suspect,normal,act",
                ],
                "false_positive": ["suspect,act,suspect (ha cap don dieu)"],
            },
            "only_loosening_vs_v1": "ha cap don dieu co buoc act->suspect; moi thay doi khac la CHAT hon",
        },
        "phase8_release_gates": {
            "G1": "S7 v2 dat tren MOI su co cua R-D va R-O, ca co va khong InterventionLog",
            "G2": "act-level FP events == 0 tren R-C khi co InterventionLog (lien quan F-6R4-1)",
            "G3": "S11 == 0 tren R-O",
            "G4": "S8, S9, S12 giu nguyen tieu chi 6R.1",
            "rule": "thieu bat ky cong nao -> FSM khong phat hanh; khong co cong thay the",
        },
        "finding_F_6R4_1_plan": {
            "what": "bang chung sau revert nam ngoai vung routing (link-s2-s3 khi bat lai s1-s2/s1-s3)",
            "measure_on": "R-C va R-O: moi tick alarm trong cua so cooldown, liet ke entity vi pham ngoai vung",
            "status": "MO TA; khong doi dinh nghia vung, khong doi luat uc che trong 6R",
            "hypothesis_to_test_later": "lien ket qua tai nguyen dung chung (CPU/kernel Mininet) ngoai routing",
        },
        "variants_closed": {
            "registered": ["conservation_residual (amendment 1)"],
            "not_registered_and_not_evaluated_in_6R": [
                "V1 envelope co dieu kien",
                "V2 envelope tren phan du",
            ],
            "why": "PHASE_6R.md de xuat V1/V2 nhung 6R.1 chua dang ky chi tiet; amendment 1 chon residual co co che vat ly. Dong nhanh re truoc khi thu R-campaign de khong phat sinh bien the sau khi thay so.",
        },
        "r_campaign_design_authority": {
            "counts": "phase6r_slo.json r_campaign (R-S 3, R-N 6, R-D 10, R-C 4, R-O 4), KHONG phai con so 15 trong PHASE_6R.md",
            "R-D_factors": "amendment 1 r_d_design_correction (theo rho), thay factor da niem phong o 6R.1",
            "dataset": "manifest rieng, collector v3-qdisc-ratevalid, khong tron voi Phase 5",
            "intervention_logging": "moi revert cua harness sinh mot ban ghi InterventionLog luc chay (actor=harness)",
        },
        "unchanged": [
            "FSMParams",
            "luat FSM",
            "luat uc che",
            "dinh nghia vung",
            "dinh nghia su kien FP",
            "S4, S8, S9, S11, S12",
        ],
        "forbidden": [
            "dung s7_v2 de doi trang thai P4 cua amendment 2",
            "doi s7_v2 sau khi thu R-O/R-D",
            "bo S7a vi no chat khi co unknown",
        ],
        "deviation_policy": "bat bien sau commit",
    }


def main() -> int:
    if OUT.exists():
        print("[6R-A3] da ton tai")
        return 1
    content = build_content()
    document = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content": content,
        "content_sha256": C.sha256_bytes(
            C.canonical_json(content).encode("utf-8")
        ),
    }
    C.atomic_json(OUT, document)
    print("[6R-A3] content_sha256 =", document["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
