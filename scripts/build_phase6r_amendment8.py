#!/usr/bin/env python3
"""Amendment 8: quyet dinh phat hanh sau khi R-set da mo; khong doi nguong."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from ml import campaign as C

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase6r_amendment_8.json"
ALLOWED_DIRTY = {
    "scripts/build_phase6r_amendment8.py",
    "results/report/phase6r_amendment_8.json",
}


def sealed(name):
    doc = json.loads((REPORT / name).read_text(encoding="utf-8"))
    if C.sha256_bytes(C.canonical_json(doc["content"]).encode()) != doc["content_sha256"]:
        raise RuntimeError("receipt drift: " + name)
    return doc


def git_state():
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    dirty = sorted(line[3:] for line in out.splitlines() if line)
    illegal = [path for path in dirty if path not in ALLOWED_DIRTY and not path.startswith("logs/")]
    if illegal:
        raise RuntimeError("commit truoc amendment 8: %s" % illegal)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=C.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {"head": head, "dirty_files": dirty}


def main():
    if OUT.exists():
        print("[6R-A8] da ton tai")
        return 1
    a1 = sealed("phase6r_amendment_1.json")
    a7 = sealed("phase6r_amendment_7.json")
    acc = sealed("phase6r_acceptance.json")
    verdicts = sealed("phase6r_verdicts.json")
    if acc["content"]["residual"]["outcome"] != "all_pass":
        raise RuntimeError("amendment 8 duoc viet cho outcome all_pass; outcome khac")

    content = {
        "amendment_id": "DT4N-P6R-AMENDMENT-8",
        "amends": {
            "amendment_1_content_sha256": a1["content_sha256"],
            "amendment_7_content_sha256": a7["content_sha256"],
            "acceptance_content_sha256": acc["content_sha256"],
            "verdicts_content_sha256": verdicts["content_sha256"],
        },
        "git": git_state(),
        "knowledge_state": {
            "r_set_acceptance_opened": True,
            "statement": "viet SAU khi mo R-set. Moi dieu duoi day la quyet dinh trien khai, KHONG doi phan quyet SLO nao va KHONG doi nguong nao.",
        },
        "trigger": {
            "amendment_1_rule": a1["content"]["outcomes"]["all_pass"],
            "observed_outcome": "all_pass",
            "conflict": "suspect = excess OR residual lam TTD p95 = %.0f ms > S4 3000 ms"
            % verdicts["content"]["slo"]["S4"]["combined_value_ms"],
        },
        "decision": {
            "choice": "C_release_as_labelled_slow_channel",
            "release": "detector-release-1.0.0 = envelope-1.0.0 + conservation-1.0.0, conservation_mode=active",
            "suspect_rule": "excess OR residual (dung nhu amendment 1)",
            "act_rule": "khong doi: dual rule envelope-1.0.0; residual KHONG BAO GIO dan toi act",
            "payload_additions": [
                "releaseVersion",
                "releaseSha256",
                "conservationSha256",
                "evidence",
            ],
            "evidence_semantics": "sao chep co tu Reading cua CHINH tick do; khong tinh lai",
            "S4_statement": "S4 PASS chi cho kenh envelope (kenh dang ky). Kenh residual co TTD ~10-11 s tren R-D va duoc cong bo la kenh cham; KHONG goi la PASS.",
            "alternatives_rejected": {
                "A_keep_shadow": "bo qua luat all_pass da dang ky; mu voi nghen s1-s2 (0/5 envelope)",
                "B_merge_unlabelled": "dung luat nhung nguoi van hanh khong phan biet bao nhanh/bao cham",
            },
        },
        "operating_scope": {
            "accepted_load": "2 Mbps/client (moi nhom co cong cua R-campaign)",
            "calibrated_load": "1-4 Mbps/client va vary (train Phase 5)",
            "observed_not_accepted": "6 Mbps: 0 alarm/59 tick moi run; 8 va 10 Mbps: 59/59 tick alarm",
            "phase7_obligation": {
                "what": "guard vung van hanh: tai vuot nguong -> unknown(cause=out_of_operating_range), khong phai suspect",
                "threshold_source_rule": "CHOT NGAY BAY GIO: nguong lay tu du lieu TRAIN Phase 5 (max host txRate quan sat duoc), KHONG lay tu R-N",
                "why": "R-N la tap nghiem thu da mo; chon nguong tu R-N la hieu chinh tren tap nghiem thu",
                "status": "chua cai dat trong 6R; Phase 7 phai dang ky prereg truoc khi code",
            },
        },
        "registered_posthoc_diagnostic": {
            "id": "D-6R7-1 residual onset",
            "question": "vi sao residual s1-s2 bat o tick 30-31 bat ke rho 1.25-2.0",
            "tool": "scripts/diag_phase6r_residual_onset.py",
            "reads": "3 run RD s1-s2 rho>=1.25 (R-set DA MO), che do shadow",
            "outputs_allowed_to_change": [],
            "prediction_accumulation": "neu co che la tich luy hang doi thi r_max tang dan tu tick 21 va rho lon hon cat R som hon",
            "prediction_step": "neu r_max phang roi nhay gan tick 30 thi co che khong phai tich luy don thuan",
            "label": "POST-HOC MO TA; khong dung cho bat ky nguong, phan quyet hay lua chon nao",
        },
        "planned_changes": {
            "ml/release.py": "MOI: nap release, dung scorer+FSM dung cau hinh, payload co evidence",
            "scripts/build_detector_release.py": "MOI: sinh models/detector-release-1.0.0.json",
            "models/detector-release-1.0.0.json": "MOI: goi phat hanh ghim SHA cac thanh phan",
            "test/test_detector_release.py": "MOI: tuong duong active == combined da nghiem thu",
            "scripts/diag_phase6r_residual_onset.py": "MOI: chan doan mo ta D-6R7-1",
        },
        "unchanged": {
            "E": 8.968806422101116,
            "K": 31,
            "R": a1["content"]["calibration"]["R"],
            "fsm_params": {
                "n_suspect": 1,
                "n_act": 2,
                "release_m": 3,
                "cooldown_s": 8.0,
            },
            "all_slo_targets": True,
            "acceptance_receipt": "khong sinh lai, khong cham lai",
            "existing_code": "khong sua mot byte file .py nao da bi ghim",
        },
        "new_risks": {
            "slow_channel": "canh bao tu residual den tre ~10 s; controller Phase 8 KHONG duoc coi no nhu tin hieu act",
            "residual_not_suppressible": "Reading.violating chi chua cot envelope; alarm chi-residual khong bi InterventionLog uc che",
        },
        "deviation_policy": "immutable after commit",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        },
    )
    print("[6R-A8] content_sha256 =", json.loads(OUT.read_text())["content_sha256"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
