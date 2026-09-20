#!/usr/bin/env python3
"""Niem phong hop dong A-E cua Phase 8.3 TRUOC khi do S11 va truoc runner.py.

Chay:  .venv/bin/python scripts/build_phase8_contract.py
Ra:    results/report/phase8_contract.json   (immutable: khong ghi de)

Hop dong phai co SHA vi do la cho duy nhat hai lop gap nhau. Ba thang sau ai
do sua bridge/detector_contract.py -> hash lech -> nghiem thu FAIL ngay, thay
vi phai dua vao tri nho.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge.controlloop_contract import CONTROLLOOP_THING_ID, TTL_TICKS  # noqa: E402
from controller.intervene import ACTION_NAME, SUBJECT  # noqa: E402
from controller.policy import PolicyParams  # noqa: E402
from controller.twin_reader import SSE_PATH  # noqa: E402
from ml import campaign as C  # noqa: E402
from ml.blast_radius import Routing, radius  # noqa: E402
from ml.intervention_log import MAX_OPEN_S  # noqa: E402

OUT = C.ROOT / "results/report/phase8_contract.json"

PINNED = [
    "controller/localize.py",
    "controller/policy.py",
    "controller/sim.py",
    "controller/twin_reader.py",
    "controller/intervene.py",
    "controller/audit.py",
    "bridge/controlloop_contract.py",
    "bridge/detector_contract.py",
    "bridge/freshness.py",
    "bridge/command_agent.py",
    "bridge/collector.py",
    "mininet/env_runner.py",
    "ml/intervention_log.py",
    "ml/blast_radius.py",
    "models/detector-release-1.0.0.json",
    "results/report/phase8_prereg.json",
    "results/report/phase8_sim_predictions.json",
    "results/report/phase7_prereg.json",
]

# Du doan S11 cho setBandwidth - KHOA TRUOC khi chay do.
S11_PREDICTIONS = {
    "quiet/log_first": {"act_entries": 0, "rule": "== 0", "gate": "C8"},
    "quiet/log_late": {"alarm_entries": 1, "rule": ">= 1",
                       "role": "doi chung am: harness du nhay"},
    "quiet/no_log": {"act_entries": 1, "rule": ">= 1",
                     "role": "doi chung duong: actuator that su sinh tin hieu"},
    "first_tick_after_inject": {
        "expect": "unknown/missing_data",
        "why": "F8-6: setBandwidth dung lai qdisc -> bo dem ve 0 -> 1 tick unknown",
    },
    "flood/published_during_mitigation": {
        "expect": "A",
        "why": (
            "UDP 47 Mbps dap vao shaper 7 Mbps -> qdiscDropDelta cua link-h1-s1 "
            "tang vot -> alarming=True -> entity thuoc radius 15/16 -> "
            "unknown(suppressed_intervention)"
        ),
        "alternative_B": "gioi han dua moi thu ve trong bien -> normal sau 3 tick",
    },
    "lease": {"expect": "khong cham", "why": "hold 20 s << MAX_OPEN_S 120 s"},
    "invalidation_rule": (
        "Neu quiet/no_log = 0 act -> phep do VO HIEU (khong phan biet duoc "
        "'write-ahead hieu qua' voi 'actuator vo hai'), phai tang nhieu loan, "
        "ghi amendment va chay lai."
    ),
}


def sha256_of(rel_path: str) -> str:
    return C.sha256_bytes((C.ROOT / rel_path).read_bytes())


def build_content() -> dict:
    routing = Routing.load(C.ROOT / "ditto/routing_table.json")
    zone = radius(routing, {"links": ["h1-s1"], "flows": []})
    params = PolicyParams()
    return {
        "contract_id": "DT4N-P8-CONTRACTS",
        "lesson": "8.3",
        "sealed_before": "scripts/run_phase8_s11_bw.py va controller/runner.py",
        "A_input": {
            "rule": "controller la CONSUMER cua twin, ngang hang voi dashboard",
            "source": "SSE Things, cung endpoint dashboard dung",
            "sse_path": SSE_PATH,
            "forbidden": ["doc bien trang thai trong bo nho cua vong detector",
                          "import detector_runner", "doc .published"],
            "enforced_by": "test/test_phase8_contract.py::test_controller_khong_doc_tat_runner",
            "cost_ms_p95": {"write_2xx": 11.173, "fanout_sse": 11.030,
                            "total": 22.203, "budget_C3_ms": 10000,
                            "fraction": 0.0022},
            "freshness_rule": "R3 kiem TRUOC khi gop delta; seq lui/trung/bootId "
                              "retired -> bo CA ban tin",
            "fields_read": ["decision.state", "decision.cause",
                            "evidence.affected", "freshness.*",
                            "provenance.releaseSha256"],
            "never_read": ["decision.affected (co quan tinh hysteresis, R2)",
                           "evidence.conservation", "evidence.actRule (N11)"],
        },
        "B_intervention": {
            "action_names": ACTION_NAME,
            "targets": {"links": ["<client>-s1"], "flows": []},
            "radius_function": "ml.blast_radius.radius",
            "why_not_detour": (
                "setBandwidth khong doi topology -> Ryu khong reroute -> khong co "
                "hanh lang vong. Luat ghim trong release: radius_with_detour CHI cho "
                "can thiep admin_down."
            ),
            "why_not_flows": "targets bang flows lam mu 16/16 entity thay vi 15/16",
            "blast_radius_h1_s1": sorted(zone),
            "n_entities": len(zone),
            "append_rule": (
                "MOI action do decide() phat ra -> DUNG MOT lan append(). "
                "Gui lai lenh (reconcile) -> KHONG append, chi POST lai voi cung cid; "
                "append lan hai se ValueError vi id tat dinh."
            ),
            "write_ahead": "append() TRUOC khi POST (M5) de FSM kip bit mat",
        },
        "C_command": {
            "subject": SUBJECT,
            "params": "tuyet doi {'bw': <Mbps>}, khong bao gio tuong doi",
            "correlation_id": "= intervention_id (tat dinh, khong ngau nhien)",
            "delivery": "at-least-once",
            "guarantee": (
                "dedup cua command_agent chi la TOI UU (cache LRU mat khi agent "
                "restart); LU Y DANG moi la bao dam dung dan"
            ),
            "effect_confirmation": {
                "channel": "org.dt4n:link-<x>.features.capacity.bwMbps",
                "chain": ["command_agent.py:258 ln.dt4n_bw",
                          "collector.py:403 getattr(link,'dt4n_bw')",
                          "collector.py:639 features['capacity']",
                          "PATCH -> SSE -> TwinReader.observed_bw()"],
                "not": "ma HTTP 202 (timeout=0 nghia la Ditto da nhan thu, "
                       "khong phai viec da xong)",
                "n13_safe": "capacity khong nam trong 71 cot cua envelope-1.0.0",
            },
            "env_runner_change": "send_command(cmd, cid=None); khong truyen -> uuid4 nhu cu",
        },
        "D_output": {
            "thing_id": CONTROLLOOP_THING_ID,
            "initial_state": "HOLD / never_started (fail-safe, KHONG BAO GIO IDLE)",
            "modes": ["IDLE", "MITIGATING", "PROBING", "HOLD"],
            "schedule_is_interval_not_timestamp": {
                "fields": ["holdRemainingS", "probeRemainingS"],
                "why": ["dong ho trinh duyet khong dong bo",
                        "time.time() co the nhay lui khi NTP hieu chinh",
                        "monotonic khong co y nghia lien tien trinh"],
            },
            "ttl_ticks": TTL_TICKS,
            "why": "detector song co the CHE MAT controller chet; C9 can freshness rieng",
        },
        "E_audit": {
            "format": "JSONL append-only, hash chain (tamper-evident)",
            "fields_required_for_C10": ["input", "roles", "now_mono",
                                        "params_sha256", "cstate_before",
                                        "cstate_after", "actions"],
            "canonical": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True)",
            "durability": "fsync moi dong",
            "rotation": "chuoi lien tuc qua nhieu file qua rotated_head_sha256",
        },
        "policy_params": params.__dict__,
        "lease_max_open_s": MAX_OPEN_S,
        "s11_predictions": S11_PREDICTIONS,
        "s11_measurement_note": (
            "Hai kich ban. QUIET: tai binh thuong 2 Mbps, bop xuong 1 Mbps de "
            "CHAC CHAN sinh drop (o 7 Mbps > 2 Mbps se khong co gi bi drop, "
            "nhanh no_log cung 0 act -> phep do vo hieu). 1 Mbps la tham so cua "
            "PHEP DO, khong phai cua policy: PolicyParams.limit_mbps van la 7.0. "
            "FLOOD: flood 47 Mbps dang chay, bop xuong 7.0 dung tham so that - "
            "dung de dong an so 9.3, KHONG dung lam gate C8 vi da co act do flood "
            "nen khong quy ket nhan qua duoc."
        ),
        "pinned_sha256": {path: sha256_of(path) for path in PINNED},
        "deviation_policy": "immutable after creation",
    }


def main() -> int:
    if OUT.exists():
        print("[P8.3] da niem phong, khong ghi de:", OUT)
        return 1
    content = build_content()
    C.atomic_json(
        OUT,
        {
            "content": content,
            "content_sha256": C.sha256_bytes(C.canonical_json(content).encode("utf-8")),
            "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )
    document = json.loads(OUT.read_text(encoding="utf-8"))
    print("[P8.3] content_sha256 =", document["content_sha256"])
    print("[P8.3] pinned files  =", len(content["pinned_sha256"]))
    print("[P8.3] blast radius  =", content["B_intervention"]["n_entities"], "entity")
    print("[P8.3] du doan S11 da khoa:",
          json.dumps(content["s11_predictions"]["quiet/log_first"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
