#!/usr/bin/env python3
"""Niem phong thiet ke Phase 8.1 (vong kin) truoc khi viet bat ky runtime nao.

Chay:  .venv/bin/python scripts/build_phase8_prereg.py
Ra:    results/report/phase8_prereg.json   (immutable: khong ghi de)

Moi con so trong file nay deu co owner va deu duoc sinh lai tu receipt cua hai
probe 8.1, khong go tay.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

OUT = C.ROOT / "results/report/phase8_prereg.json"
ACTIONABILITY = "results/report/phase8_actionability.json"
LOCALIZATION = "results/report/phase8_localization_probe.json"
RELEASE = "models/detector-release-1.0.0.json"
PREREG7 = "results/report/phase7_prereg.json"
RULE = "controller/localize.py"

# L = tran tai hop le quan sat duoc tren train, LAM TRON LEN den Mbps nguyen.
LIMIT_MBPS = 7.0


def sha256_of(rel_path: str) -> str:
    return C.sha256_bytes((C.ROOT / rel_path).read_bytes())


def load(rel_path: str) -> dict:
    return json.loads((C.ROOT / rel_path).read_text(encoding="utf-8"))


CONTROLLABILITY = [
    {
        "actuator": "disableLink s1-s2",
        "physical_effect": "Ryu tinh lai duong, traffic di s1-s3-s2",
        "helps_victim": False,
        "why": "duong vong xuyen link bottleneck 5 Mbps (mininet/topology.py:72); "
               "flood di theo, nghen nang hon",
    },
    {
        "actuator": "disableLink s2-srv1",
        "physical_effect": "co lap srv1",
        "helps_victim": False,
        "why": "srv1 chi co mot canh trong ditto/topology_spec.json (['srv1','s2']); "
               "khong co LB/DNS/NAT nao doi dich 10.0.0.4 -> 10.0.0.5",
    },
    {
        "actuator": "disableSwitch s1",
        "physical_effect": "tat switch goc cua ca ba client",
        "helps_victim": False,
        "why": "h1,h2,h3 deu treo vao s1 (topology_spec.json); pha huy toan bo dich vu",
    },
    {
        "actuator": "disableHost h1 / enableHost h1",
        "physical_effect": "tat han thu pham",
        "helps_victim": True,
        "why": "co hieu luc nhung pha huy: h1 con traffic hop le 2 Mbps; khong dao nguoc em",
    },
    {
        "actuator": "enableLink / enableSwitch",
        "physical_effect": "khoi phuc thu da tat",
        "helps_victim": False,
        "why": "khong phai cong cu giam thieu; chi la duong lui cua cac lenh tren",
    },
    {
        "actuator": "setBandwidth h1-s1 bw=L",
        "physical_effect": "gioi han toc do tai cong vao cua thu pham",
        "helps_victim": True,
        "why": "cat flood tai nguon, giu lai L Mbps cho traffic hop le, dao nguoc duoc "
               "bang mot lenh setBandwidth khac; twin quan sat duoc qua dt4n_bw "
               "(bridge/command_agent.py:258 ghi, bridge/collector.py:403 doc)",
    },
]

SLO = [
    ("C1", "hanh dong dung nguon", "100% (n >= 10 live)", True, "8.6"),
    ("C2", "khong hanh dong voi admin_down/shift/degrade", "0 lan", True, "8.1 offline + 8.7 live"),
    ("C3", "tre act -> thu pham bi gioi han (p95)", "<= 10000 ms", True, "8.6"),
    ("C4", "nan nhan hoi phuc >= 80% nen (p95)", "<= 15 s", False, "8.6"),
    ("C5", "A/B goodput nan nhan (co - khong controller)", "CI95 > 0", True, "8.6"),
    ("C6", "so hanh dong / 10 phut (khong dao dong)", "<= can sim; 0 luc binh thuong", True, "8.7"),
    ("C7", "hanh dong tren trigger bi cam", "0", True, "8.2 + 8.7"),
    ("C8", "S11 cho setBandwidth: controller khong tu kich hoat detector", "0", True, "8.3"),
    ("C9", "controller chet -> UI STALE va gioi han tu go", "<= 5 s / <= TTL", True, "8.7"),
    ("C10", "quyet dinh dung lai bit-exact tu audit", "100%", True, "8.8"),
    ("C11", "on dinh 30 phut: RSS, 0 ERROR", "<= 1 MiB; 0", True, "8.7"),
    ("C12", "ty le thoi gian mu (vung uc che)", "bao cao, khong dat nguong", False, "8.7"),
]

PROHIBITIONS = {
    "R1": "chi hanh dong khi decision.state == 'act' (state DA CONG BO, sau guard)",
    "R2": "dung evidence.affected cua chinh tick do, KHONG dung decision.affected",
    "R3": "kiem freshness bang MonotonicFreshness truoc moi lenh",
    "R4": "ghi releaseVersion/releaseSha256 vao audit cua moi quyet dinh",
    "N10": "khong hanh dong khi suspect",
    "N11": "khong hanh dong dua tren evidence.conservation hay actRule",
    "N12": "khong hanh dong khi freshness het TTL",
    "N13": "khong tinh lai state/feature/nguong cua detector",
    "N14": "tick suspect chi-residual sau can thiep khong phai bug",
    "N15": "cause == 'stale_intervention' -> revert can thiep dang mo, khong tao moi",
    "N16": "cause == 'out_of_operating_range' -> khong hanh dong",
}

LIMITATIONS = [
    "degrade tren s1-s2 khong bao gio vao act (0 tick tren F-degrade-s1-s2-s3003-r1 va "
    "ca 5 run RD-degrade-s1-s2-*): controller tuan thu hop dong SE KHONG BAO GIO phan ung "
    "voi loai su co nay. Day la gioi han S1=0.30 hien ra o tang hanh dong, khong phai loi controller.",
    "nan nhan bi bo doi KHONG duoc detector phat hien (h3 tut 2.15 -> 0.01 Mbps trong "
    "F-flood-h1_to_srv1-s3005-r1 ma khong vao affected). He thay thu pham, khong thay hau qua.",
    "vung uc che = 15/16 entity cua model trong moi khoang giam thiep; chi link-s2-s3 con "
    "nhin thay. Mot su co thu hai trong khoang do bi che hoan toan.",
    "rate limit o link truy nhap cung bop traffic hop le cua chinh thu pham; flood la UDP "
    "(rl/scenarios.py::TrafficFlood dung iperf -u) nen hang doi day va lossPct cua "
    "link-h1-s1 se tang - phai do lai S11 cho actuator moi o 8.3.",
    "n = 4 run flood trong du lieu da mo (2 Phase 5 + 2 Phase 6R). Mong. C1 that den tu A/B live 8.6.",
    "luat v2 im lang khi co >= 2 ung vien (fail-closed). Chu dich, nhung la gioi han: hai thu "
    "pham dong thoi se khong duoc xu ly tu dong.",
]


def build_content() -> dict:
    action = load(ACTIONABILITY)
    localization = load(LOCALIZATION)
    numbers = localization["train_numbers"]
    return {
        "prereg_id": "DT4N-P8-CLOSED-LOOP-MITIGATION",
        "lesson": "8.1",
        "knowledge_state": (
            "Thiet ke, actuator, luat dinh vi v2, ba kha nang KN1-KN3 va bang C1-C12 lay "
            "nguyen tu huong dan Lesson 8.1. Du lieu Phase 5 (8 train + 10 C/F) va Phase 6R "
            "R-set deu DA MO tu Phase 6R/7, nen ket qua offline o day la in-sample doi voi "
            "thiet ke da nhin thay chung."
        ),
        "protocol_deviation": {
            "occurred": True,
            "detail": (
                "Hai probe 8.1-A va 8.1-B da chay TRUOC khi seal file nay, va ket qua tren "
                "R-set Phase 6R da duoc doc truoc khi ghi KN. Khong the tuyen bo blind prereg. "
                "Bu lai: luat khong co tham so tu do nao duoc chinh sau khi nhin so, "
                "va moi con so lay tu train deu di qua tuong lua train-only."
            ),
        },
        "problem_renaming": {
            "from": "Closed-loop failover (twin chuyen huong traffic)",
            "to": "Closed-loop mitigation (twin gioi han toc do tai nguon)",
            "reason": (
                "failover tang du lieu DA co san trong vong trong: "
                "mininet/controller_static.py::port_status_handler cap nhat down_edges roi goi "
                "next_hop_table(excluded_edges=...) trong vai mili-giay. Vong ngoai (twin, giay) "
                "chi them gia tri o tang CHINH SACH. Chi so PART V doi tu 'traffic chuyen huong "
                "< 10 s' thanh 'giam thieu co hieu luc < 10 s' (C3), kem ly do nay."
            ),
        },
        "controllability_table": CONTROLLABILITY,
        "actuator": {
            "command": "setBandwidth",
            "target_link": "<client bi chi mat>-s1",
            "limit_mbps": LIMIT_MBPS,
            "limit_derivation": (
                "tran tai hop le cao nhat tung quan sat tren dung 8 run train = %.6f Mbps, "
                "lam tron len Mbps nguyen" % numbers["limit_ceiling_mbps"]
            ),
            "limit_owner": numbers["limit_owner"],
            "reversibility": "setBandwidth ve bw goc (20 Mbps, mininet/topology.py:88)",
            "observability_channel": "link-<x>-s1.features.capacity.bwMbps (khong nam trong "
                                     "71 cot dac trung cua envelope-1.0.0 -> doc no khong vi pham N13)",
        },
        "localization_rule": {
            "version": "v2",
            "file": RULE,
            "sha256": sha256_of(RULE),
            "free_parameters": 0,
            "statement": [
                "candidates = {host in evidence.affected | attributes.role == 'client'}",
                "|candidates| == 0 -> NO_ACTION(no_client_candidate)",
                "|candidates| == 1 -> TARGET = candidate do",
                "|candidates| >= 2 -> NO_ACTION(ambiguous_multiple_clients)  # fail-closed",
            ],
            "latch": (
                "sau khi chon TARGET, controller sang MITIGATING va KHONG danh gia lai luat "
                "cho toi khi episode ket thuc"
            ),
            "latch_justification": {
                "runs_where_per_tick_would_differ": action["summary"]["latch_vs_per_tick_differs"],
                "mechanism": "recovery burst: sau khi flood tat, TCP cua nan nhan xa backlog "
                             "(h3 len 18.4 Mbps o tick 46) va nan nhan vao affected; danh gia "
                             "moi tick se bop bang thong dung nan nhan dang hoi phuc",
            },
        },
        "dormant_extension_delta_gap": {
            "status": "CHUA KICH HOAT",
            "delta_mbps": numbers["delta_mbps"],
            "delta_mbps_exact": numbers["delta_mbps_exact"],
            "owner": numbers["delta_owner"],
            "decision": "GIU du 8 run train, KHONG loai N-vary-s1008-r2",
            "reason": (
                "loai s1008 -> Delta = %.6f -> luat gap ban nham o run binh thuong %s"
                % (
                    localization["delta_if_s1008_dropped"],
                    localization["gap_rule_false_fire_runs_if_s1008_dropped"],
                )
            ),
            "why_not_used_now": (
                "tai moi tick act tren du lieu da mo, |candidates| chi bang 0, 1 hoac 3; "
                "truong hop 3 la RN-load8M/10M noi cau tra loi dung la KHONG hanh dong. "
                "Nhanh Delta se la code chua tung chay. Neu sau nay |candidates| >= 2 xay ra "
                "that trong live, phai do lai Delta truoc khi bat."
            ),
        },
        "preconditions": [
            "decision.state == 'act' (R1, N10)",
            "freshness con han (R3, N12)",
            "cause not in {stale_intervention, out_of_operating_range} (N15, N16)",
            "controller dang o IDLE (chua co can thiep mo)",
        ],
        "prohibitions": PROHIBITIONS,
        "outcome_declared": {
            "branches": {
                "KN1": "100% flood -> dung nguon VA 100% khong-flood -> khong hanh dong "
                       "=> dong vong TU DONG",
                "KN2": "dung nguon nhung co khong-flood bi hanh dong => thu hep dieu kien "
                       "trien khai",
                "KN3": "khong dinh vi duoc => vong BAN TU DONG, controller de xuat, nguoi duyet",
            },
            "observed_offline": localization["outcome"],
            "confusion_matrix": localization["confusion_matrix"],
            "n_runs_probed": action["summary"]["n_runs"],
            "caveat": "offline, in-sample, n_flood = 4. C1 that do o 8.6 live.",
        },
        "slo": [
            {"id": i, "measures": m, "objective": o, "gate": g, "measured_at_lesson": l}
            for i, m, o, g, l in SLO
        ],
        "suppression_zone": localization["suppression_zone"],
        "known_limitations": LIMITATIONS,
        "upstream_sha256": {
            RELEASE: sha256_of(RELEASE),
            PREREG7: sha256_of(PREREG7),
            ACTIONABILITY: sha256_of(ACTIONABILITY),
            LOCALIZATION: sha256_of(LOCALIZATION),
            "scripts/probe_phase8_actionability.py": sha256_of(
                "scripts/probe_phase8_actionability.py"
            ),
            "scripts/probe_phase8_localization.py": sha256_of(
                "scripts/probe_phase8_localization.py"
            ),
            "scripts/phase8_replay.py": sha256_of("scripts/phase8_replay.py"),
        },
        "deviation_policy": "immutable after creation; moi thay doi phai la amendment rieng",
    }


def main() -> int:
    if OUT.exists():
        print("[P8.1] da niem phong, khong ghi de:", OUT)
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
    print("[P8.1] content_sha256 =", document["content_sha256"])
    print("[P8.1] actuator =", content["actuator"]["command"],
          "L =", content["actuator"]["limit_mbps"], "Mbps, owner =",
          content["actuator"]["limit_owner"])
    print("[P8.1] rule =", content["localization_rule"]["version"],
          "free_parameters =", content["localization_rule"]["free_parameters"],
          "sha256 =", content["localization_rule"]["sha256"][:12])
    print("[P8.1] outcome =", content["outcome_declared"]["observed_offline"],
          content["outcome_declared"]["confusion_matrix"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
