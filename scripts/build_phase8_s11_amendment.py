#!/usr/bin/env python3
"""Amendment 1 cua Lesson 8.3: vi sao kich ban `quiet` vo hieu va sua thanh gi.

Chay:  .venv/bin/python scripts/build_phase8_s11_amendment.py
Ra:    results/report/phase8_s11_amendment1.json  (immutable)

Hop dong 8.3 da KHOA truoc khi do dieu kien vo hieu:
  "Neu quiet/no_log = 0 act -> phep do VO HIEU, phai tang nhieu loan, ghi
   amendment va chay lai."
Dieu do da xay ra. File nay ghi lai nguyen nhan co che, sua doi, va nhan lai
verdict cho dung (VO HIEU khac FAIL).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_s11_amendment1.json"
RECEIPTS = {
    "quiet": "results/report/phase8_s11_bw_quiet.json",
    "quiet_udp": "results/report/phase8_s11_bw_quiet_udp.json",
    "flood": "results/report/phase8_s11_bw_flood.json",
}


def load(rel_path: str) -> dict:
    return json.loads((C.ROOT / rel_path).read_text(encoding="utf-8"))["content"]


def arms_summary(content: dict) -> dict:
    return {
        arm: {
            "n": data["n"],
            "act_entries": data["act_entries"],
            "alarm_entries": data["alarm_entries"],
            "published_during_mitigation": data["published_during_mitigation"],
        }
        for arm, data in content["arms"].items()
    }


def main() -> int:
    if OUT.exists():
        print("[P8.3-A1] da niem phong, khong ghi de:", OUT)
        return 1
    quiet = load(RECEIPTS["quiet"])
    quiet_udp = load(RECEIPTS["quiet_udp"])
    flood = load(RECEIPTS["flood"])

    content = {
        "amendment_id": "DT4N-P8.3-A1",
        "lesson": "8.3",
        "contract_sha256": C.sha256_bytes(
            (C.ROOT / "results/report/phase8_contract.json").read_bytes()
        ),
        "trigger": (
            "Dieu kien vo hieu da khoa truoc trong phase8_contract.json"
            "::s11_predictions.invalidation_rule da xay ra."
        ),
        "what_happened": {
            "scenario": "quiet (bw 1.0 Mbps, nen TCP 2 Mbps/client)",
            "arms": arms_summary(quiet),
            "positive_control_act_entries": quiet["arms"]["no_log"]["act_entries"],
            "verdict_label_in_receipt": quiet["c8_verdict"],
            "corrected_verdict": (
                "INVALID (doi chung duong 0 act: khong phan biet duoc "
                "write-ahead hieu qua voi actuator vo hai). Nhan 'FAIL' trong "
                "receipt goc la LOI DAT TEN cua harness, da sua trong "
                "scripts/run_phase8_s11_bw.py::_verdict; KHONG co nghia la "
                "write-ahead that bai."
            ),
        },
        "root_cause": (
            "Nen `normal` cua mininet/traffic.py::start_background_load la TCP "
            "(scenario='normal' -> udp=False). Bop bang thong xuong 1 Mbps chi lam "
            "TCP lui buoc; khong co gi bi drop o qdisc nen envelope khong thay vi "
            "pham. Day chinh la gioi han S1 = 0.30 da khai trong hop dong ban giao "
            "Phase 7: 'envelope bo sot phan lon su co ma TCP hap thu thanh muc "
            "thong luong thap hon'. Ha bw them nua cung khong doi ban chat."
        ),
        "amendment": {
            "new_scenario": "quiet_udp",
            "change": (
                "them mot luong nen UDP h1->srv1 5 Mbps (rl.scenarios.TrafficFlood) "
                "truoc khi can thiep; UDP KHONG lui buoc nen bop xuong 1 Mbps chac "
                "chan sinh qdisc drop -> co tin hieu quan sat duoc"
            ),
            "why_5_mbps": (
                "5 < tran tai hop le tren train 6.181986 Mbps (phase8_prereg.json) "
                "nen detector van `normal` truoc can thiep; va san tai dong deu "
                "g=min(client tx) van ~2 Mbps < nguong guard 4.312610 nen guard "
                "vung van hanh khong bat"
            ),
            "not_changed": [
                "PolicyParams.limit_mbps van 7.0 (1 Mbps la tham so cua PHEP DO)",
                "ba nhanh log_first/log_late/no_log giu nguyen khuon 7.6",
                "hold 20 s, cooldown 8 s, tail 10 s, pha ngau nhien giu nguyen",
            ],
        },
        "result_after_amendment": {
            "scenario": "quiet_udp",
            "arms": arms_summary(quiet_udp),
            "measurement_valid": quiet_udp["measurement_valid"],
            "c8_verdict": quiet_udp["c8_verdict"],
        },
        "flood_scenario": {
            "purpose": "dong an so 9.3 cua Lesson 8.2, KHONG dung lam gate",
            "arms": arms_summary(flood),
            "unknown_93_closed": "A",
            "evidence": (
                "log_first rep0/rep1: 19/19 tick trong khoang giam thieu deu la "
                "unknown(suppressed_intervention) voi envelope=True act_rule=True - "
                "tin hieu tho CO, nhung bi vung uc che nuot dung nhu kha nang A"
            ),
            "exception_found": {
                "round": "log_first rep2",
                "observed": "18 tick `act` khong bi uc che",
                "mechanism": (
                    "ml/fsm.py chi uc che khi TAT CA entity vi pham nam trong vung "
                    "(`local <= zone`). Vung cua can thiep tren h1-s1 la 15/16 "
                    "entity; entity duy nhat ngoai vung la link-s2-s3. Do do chi can "
                    "mot vi pham roi vao link-s2-s3 (duong nen srv1->srv2 di qua "
                    "bottleneck 5 Mbps) la ca tick khong duoc uc che."
                ),
                "impact_on_design": (
                    "Khong pha thiet ke 8.2: o trang thai MITIGATING, nhan ACT "
                    "KHONG sinh hanh dong moi (chi lich moi go). Nhung phai khai "
                    "vao gioi han: duoi flood, ty le tick bi uc che khong phai 100%."
                ),
                "rate": "1/3 round log_first duoi flood",
            },
        },
        "f8_6_confirmed": {
            "claim": "setBandwidth dung lai qdisc -> 1 tick unknown(missing_data)",
            "observed": (
                "29/30 round quiet+quiet_udp co tick dau sau inject la "
                "unknown/missing_data; va trong kich ban flood, ca inject lan revert "
                "deu sinh dung mot tick missing_data"
            ),
            "exception": "1 round (quiet_udp/no_log rep0) tick dau la `normal`: "
                         "lenh co hieu luc sau moc lay mau cua tick do",
        },
        "effect_latency_note": (
            "effect_latency_s do bang cach doc thang link.dt4n_bw trong tien trinh "
            "Mininet, tuc do tre ACTUATOR (post -> tc da doi), KHONG phai do tre xac "
            "nhan qua twin. Do tre qua twin them collector 1 tick + write_2xx + "
            "fanout_sse va se duoc do o 8.4."
        ),
        "deviation_policy": "immutable after creation",
    }

    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    document = json.loads(OUT.read_text(encoding="utf-8"))
    print("[P8.3-A1] content_sha256 =", document["content_sha256"])
    print("[P8.3-A1] quiet     ->", content["what_happened"]["corrected_verdict"][:60])
    print("[P8.3-A1] quiet_udp -> valid=%s C8=%s" % (
        content["result_after_amendment"]["measurement_valid"],
        content["result_after_amendment"]["c8_verdict"]))
    print("[P8.3-A1] an so 9.3 -> kha nang",
          content["flood_scenario"]["unknown_93_closed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
