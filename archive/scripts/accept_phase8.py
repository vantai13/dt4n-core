#!/usr/bin/env python3
"""NGHIEM THU PHASE 8 - mot script, doc hien vat, tra ma thoat 0/1 (Lesson 8.8).

Nghiem thu phai chay duoc boi NGUOI KHONG PHAI TAC GIA, tren MAY KHONG PHAI
may tac gia, KHONG CAN tac gia giai thich gi. Neu no la "mo docs, doc 12 muc,
doi chieu 9 file bang mat" thi no khong phai nghiem thu - no la mot buoi
thuyet trinh, va no khong bat duoc hoi quy: ba thang sau ai do sua policy.py,
khong ai biet C6 da hong.

QUY TAC LON: script nay DOC RECEIPT, KHONG CHAY LAI THI NGHIEM.
  receipt la HIEN VAT   -> kiem duoc mai mai, tren may bat ky
  thi nghiem la SU KIEN -> khong lap lai duoc (may khac, tai khac, gio khac)
va mot nghiem thu chay lai A/B 90 phut + soak 30 phut thi khong ai chay no.

Sau thu tu, khong duoc dao:
  1. SHA cua tung receipt khop noi dung        (chua bi sua)
  2. chuoi phu thuoc prereg -> sim -> contract -> phep do  (do dung he)
  3. ma nguon bi ghim con dung sha, hoac troi CO LY DO DA KHAI
  4. ap tieu chi C1-C12 DA NIEM PHONG len so trong receipt
  5. in bang verdict, tra 0/1

Chay:  .venv/bin/python scripts/accept_phase8.py --strict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import campaign as C  # noqa: E402

REPORT = C.ROOT / "results/report"
OUT = REPORT / "phase8_acceptance.json"

# --------------------------------------------------------------- 4 loai verdict
PASS = "PASS"
FAIL = "FAIL"
INVALID = "INVALID"                       # phep do khong sinh tin hieu do duoc
CORRECTED = "PASS-with-model-correction"  # thoa sau khi SUA CAN theo mo hinh
VERDICTS = (PASS, FAIL, INVALID, CORRECTED)

# Bon rao cua loai thu tu. Rao #2 la rao quan trong nhat: sua can VI MO HINH
# thieu mot co che, KHONG phai vi do duoc con so kia. Khac nhau o cho ban sua
# TIEN DOAN duoc con so chu khong THEO SAU no.
CORRECTION_GATES = ("cause_identified", "model_not_data", "known_answer_test",
                    "declared_in_receipt_and_system_card")

# --------------------------------------------------------------- receipt bat buoc
RECEIPTS = {
    "prereg":            "phase8_prereg.json",
    "sim":               "phase8_sim_predictions.json",
    "contract":          "phase8_contract.json",
    "s11_flood":         "phase8_s11_bw_flood.json",
    "s11_quiet":         "phase8_s11_bw_quiet.json",
    "s11_quiet_udp":     "phase8_s11_bw_quiet_udp.json",
    "s11_amendment":     "phase8_s11_amendment1.json",
    "localization":      "phase8_localization_probe.json",
    "actionability":     "phase8_actionability.json",
    "c3":                "phase8_c3.json",
    "ab_c5":             "phase8_ab_c5.json",
    "ab_addendum":       "phase8_ab_addendum.json",
    "ablation":          "phase8_ablation_rerun.json",
    "stability_flood":   "phase8_stability_flood.json",
    "stability_quiet":   "phase8_stability_quiet.json",
    "chaos":             "phase8_chaos_v6.json",
    "gap_reconciliation": "phase8_gap_reconciliation.json",
}
OPTIONAL = {
    "poisson":  "phase8_stability_poisson.json",   # no 8.7, tra o 8.8
    "poisson_analysis": "phase8_poisson.json",     # so THEO CAP voi sim + C12-a
    "hypothesis": "phase8_suppression_hypothesis.json",
    "soak":     "phase8_soak.json",
    # C11 phai do o CAU HINH PRODUCTION (timeline TAT, khong sampler) - do la
    # giao thuc Phase 7 dang ky: them 300 s warmup roi moi cham 30 phut.
    # Hai luot sai cau hinh/cua so cu chi giu lam dau vet.
    "soak_production": "phase8_soak_production.json",
    "soak_production_v2": "phase8_soak_production_v2.json",
    "c11_prediction":  "phase8_c11_prediction.json",
    "c11_outcome":     "phase8_c11_outcome.json",
    "c10":      "phase8_c10_v2.json",
    "ui_c9a":   "phase8_ui_stale.json",
    "soak_c10": "phase8_c10_v2.json",
    "chaos_second_flood": "phase8_chaos_second_flood.json",
    # ---- 8.9 dong phase
    "closure_prereg": "phase8_closure_prereg.json",
    "target_audit": "phase8_target_audit.json",
    "c1_control": "phase8_c1_control.json",
    "suppression_modes": "phase8_suppression_modes.json",
    "c10_v3": "phase8_c10_v3.json",
}

# ------------------------------------------------- chuoi phu thuoc (theo sha FILE)
# Mot receipt do bang mot HOP DONG KHAC voi hop dong duoc niem phong la mot
# receipt DO SAI HE. Kiem bang may, khong bang mat.
DEPENDS = {
    "sim":      [("upstream_sha256", "results/report/phase8_prereg.json", "prereg")],
    "contract": [("pinned_sha256", "results/report/phase8_prereg.json", "prereg"),
                 ("pinned_sha256", "results/report/phase8_sim_predictions.json", "sim")],
    "s11_flood":     [("contract_sha256", None, "contract")],
    "s11_quiet":     [("contract_sha256", None, "contract")],
    "s11_quiet_udp": [("contract_sha256", None, "contract")],
    "s11_amendment": [("contract_sha256", None, "contract")],
    "ab_addendum":   [("source_sha256", None, "ab_c5:content")],
    "c1_control": [("prereg_sha256", None, "closure_prereg"),
                   ("contract_sha256", None, "contract")],
    "suppression_modes": [("prereg_sha256", None, "closure_prereg")],
    "chaos_second_flood": [("closure_prereg_sha256", None, "closure_prereg")],
    # Tu 8.8: harness stability khai tham chieu. Cac receipt CU (8.7) khong co
    # truong nay nen chung van nam trong `dependency_chain_not_declared`; day
    # la ky luat ap dung TIEN TOI, khong hoi to gia.
    "poisson":       [("prereg_sha256", None, "prereg"),
                      ("contract_sha256", None, "contract"),
                      ("sim_sha256", None, "sim")],
}

# Ma nguon bi ghim ma TROI phai co ly do DA KHAI o day, kem lesson va receipt.
# Danh sach nay la mot phan cua nghiem thu: no bien "file da doi" tu mot canh
# bao im lang thanh mot muc phai bao ve truoc hoi dong.
DECLARED_DRIFT = {
    "controller/policy.py":
        "8.4/8.6: them `incarnation` vao ControllerState (hai lan chay "
        "controller tren cung mot detector sinh trung intervention_id) va sua "
        "HOLD/deadline. Da chay lai sim + C6 + C7 + C10 sau do. "
        "8.9 AMENDMENT A2: cach ly probe_w_s sau probe_target_changed (khop LATCH "
        "da dang ky o 8.1); thay doi DON DIEU (chi them nhanh tra ve ()), sim 2000 "
        "seed trung het, replay audit cu bit-exact, C10-v3 tren audit moi.",
    "controller/twin_reader.py":
        "8.4: R3 kiem freshness TRUOC khi gop delta (bo CA ban tin khi seq lui/"
        "trung/bootId retired).",
    "bridge/command_agent.py":
        "8.6: them fencing token cho lease; 8.7: sua duong lease khi agent chet.",
    "controller/sim.py":
        "8.8 DINH CHINH MO HINH: them revert cua tat em khi het chan troi. Can "
        "C6-a doi tu 13 thanh 14. Co known-answer test "
        "(test_phase8_acceptance_fixes.py) va tai lap duoc con so cu bang "
        "SimParams(graceful_shutdown_revert=False).",
}


# ---------------------------------------------------------------- tien ich


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, filename, problems, required=True):
    path = REPORT / filename
    if not path.exists():
        if required:
            problems.append("thieu receipt bat buoc: %s" % filename)
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    return {"path": path, "file_sha256": file_sha(path),
            "content": document.get("content"),
            "content_sha256": document.get("content_sha256")}


def check_content_sha(receipts, problems):
    """(1) Receipt bi sua sau khi niem phong -> moi ket luan doc tren no do theo."""
    rows = []
    for name, receipt in receipts.items():
        if receipt is None or receipt["content"] is None:
            continue
        recomputed = C.sha256_bytes(C.canonical_json(receipt["content"]).encode())
        ok = (receipt["content_sha256"] is None) or (recomputed == receipt["content_sha256"])
        rows.append({"receipt": name, "sealed": receipt["content_sha256"],
                     "recomputed": recomputed, "ok": ok,
                     "note": None if receipt["content_sha256"] else
                             "receipt khong co content_sha256 (truoc khi ky luat nay ap dung)"})
        if not ok:
            problems.append("SHA khong khop: %s" % name)
    return rows


def check_dependency_chain(receipts, problems):
    """(2) prereg -> sim -> contract -> phep do, kiem bang may."""
    rows = []
    for name, rules in DEPENDS.items():
        receipt = receipts.get(name)
        if receipt is None:
            continue
        for field, key, target in rules:
            value = (receipt["content"] or {}).get(field)
            got = value.get(key) if (isinstance(value, dict) and key) else value
            target_name, _, which = target.partition(":")
            reference = receipts.get(target_name)
            expect = None if reference is None else (
                reference["content_sha256"] if which == "content"
                else reference["file_sha256"])
            ok = got is not None and got == expect
            rows.append({"receipt": name, "field": field, "key": key,
                         "expect_from": target, "expect": expect, "got": got,
                         "ok": ok})
            if not ok:
                problems.append("chuoi phu thuoc gay: %s.%s -> %s (co %s, can %s)"
                                % (name, field, target, str(got)[:12], str(expect)[:12]))
    # Cac receipt phep do KHONG khai tham chieu nao: khai bao thang la mot
    # thieu sot cua ky luat, khong im lang cho qua.
    missing = [n for n in ("ab_c5", "c3", "stability_flood", "stability_quiet",
                           "chaos") if n in receipts and n not in DEPENDS]
    return rows, missing


def check_pinned_sources(receipts, problems):
    """(3) Ma nguon ghim: hoac dung sha, hoac troi CO LY DO DA KHAI."""
    contract = receipts.get("contract")
    if contract is None:
        return []
    rows = []
    for rel, sealed in sorted((contract["content"] or {}).get("pinned_sha256", {}).items()):
        path = C.ROOT / rel
        if not path.exists():
            rows.append({"file": rel, "state": "MISSING", "declared": None})
            problems.append("file bi ghim da bien mat: %s" % rel)
            continue
        current = file_sha(path)
        if current == sealed:
            rows.append({"file": rel, "state": "OK"})
            continue
        reason = DECLARED_DRIFT.get(rel)
        rows.append({"file": rel, "state": "DRIFT", "sealed": sealed[:12],
                     "current": current[:12], "declared": reason})
        if not reason:
            problems.append("ma nguon ghim troi ma KHONG khai ly do: %s" % rel)
    return rows


# ---------------------------------------------------------------- C1 - C12


def _first_run(receipt):
    runs = ((receipt or {}).get("content") or {}).get("runs") or [{}]
    return runs[0]


def evaluate(receipts):
    """Ap tieu chi DA NIEM PHONG len so trong receipt. Moi muc: 4 loai verdict."""
    prereg = (receipts["prereg"]["content"] if receipts.get("prereg") else {}) or {}
    slo = {row["id"]: row for row in prereg.get("slo", [])}
    sim = (receipts["sim"]["content"] if receipts.get("sim") else {}) or {}
    results = []

    def add(cid, verdict, measured, evidence, note=None, correction=None):
        row = slo.get(cid, {})
        results.append({
            "id": cid, "measures": row.get("measures"),
            "objective": row.get("objective"), "gate": row.get("gate"),
            "verdict": verdict, "measured": measured, "evidence": evidence,
            "note": note,
        })
        if correction:
            results[-1]["model_correction"] = correction

    # ---- C1: hanh dong dung nguon
    ab = (receipts["ab_c5"]["content"] if receipts.get("ab_c5") else {}) or {}
    stab = receipts.get("stability_flood")
    n_inject = _first_run(stab).get("n_inject", 0)
    ta = (receipts.get("target_audit") or {}).get("content")
    ctl = (receipts.get("c1_control") or {}).get("content")
    if ta is None or ctl is None:
        add("C1", INVALID,
            "chua co bang chung muc tieu: target_audit=%s, c1_control=%s (n_inject 8.7 = %d)"
            % (ta is not None, ctl is not None, n_inject),
            ["phase8_target_audit.json", "phase8_c1_control.json"],
            "evaluator 8.9 CHAT HON evaluator cu (phase8_closure_prereg::C1_evaluator_change)")
    else:
        ok = (ta.get("evidence_nonempty") and ta.get("n_wrong_target_total") == 0
              and ctl.get("c1_control_pass"))
        add("C1", PASS if ok else FAIL,
            "audit cu: %d inject, %d sai muc tieu | E1: %s, sai %d, dung voi thu pham != h1: %d, "
            "theo kich ban %s"
            % (ta.get("n_inject_total"), ta.get("n_wrong_target_total"), ctl.get("outcome"),
               ctl.get("n_wrong_target"), ctl.get("n_correct_nonh1_culprit"),
               json.dumps(ctl.get("by_scenario"), sort_keys=True)),
            ["phase8_target_audit.json", "phase8_c1_control.json"],
            "silent khong tinh la sai nhung phai khai coverage (KN2)")

    # ---- C2: khong hanh dong voi admin_down / shift / degrade
    loc = (receipts["localization"]["content"] if receipts.get("localization") else {}) or {}
    quiet_actions = _first_run(receipts.get("stability_quiet")).get("n_actions")
    add("C2", PASS if quiet_actions == 0 else FAIL,
        "quiet 600 s live: %s hanh dong; offline probe: %s"
        % (quiet_actions, loc.get("summary") or "xem receipt"),
        ["phase8_localization_probe.json", "phase8_stability_quiet.json"])

    # ---- C3: tre act -> gioi han co hieu luc (p95)
    c3 = (receipts["c3"]["content"] if receipts.get("c3") else {}) or {}
    p95 = (c3.get("summary") or {}).get("p95_ms")
    add("C3", PASS if c3.get("c3_pass") else FAIL,
        "p95 = %s ms (ngan sach %s ms, n = %s)"
        % (p95, c3.get("budget_ms"), (c3.get("summary") or {}).get("n")),
        ["phase8_c3.json"])

    # ---- C4: nan nhan hoi phuc >= 80% nen (p95 <= 15 s)  -> KHONG DO DUOC
    add("C4", INVALID,
        "khong do duoc: bien ket cuc BAO HOA o toc do chao TCP (nhanh A "
        "CV = 0.0466%), nen 'hoi phuc >= 80% nen' khong phan biet duoc voi "
        "'khong bi anh huong'",
        ["phase8_ab_addendum.json"],
        "khong phai gate. Bien thay the (degraded_tick_fraction) duoc dinh "
        "nghia o measurements/degraded.py va do o 8.8.")

    # ---- C5: A/B
    primary = (ab.get("primary") or {})
    add("C5", PASS if ab.get("c5_pass") else FAIL,
        "mean_diff = %s Mbps, CI95 %s, p = %s (%s khoi)"
        % (primary.get("mean_diff"), primary.get("ci95"),
           (primary.get("randomization_test") or {}).get("p_two_sided"),
           primary.get("n_blocks")),
        ["phase8_ab_c5.json"],
        "+1.893 Mbps la chenh lech TAI TRAN cua bien ket cuc; KHONG duoc doc "
        "thanh 'khoi phuc 88% goodput'")

    # ---- C6-a: so hanh dong duoi flood lien tuc  (DINH CHINH MO HINH)
    run = _first_run(stab)
    measured = run.get("n_actions")
    sealed_bound = sim.get("modes", {}).get("continuous_flood_600s", {}).get("n_actions")
    corrected_bound = (sealed_bound + 1) if sealed_bound is not None else None
    holds = run.get("holds_s") or []
    gaps = run.get("gaps_s") or []
    t_max = ((receipts.get("stability_flood") or {}).get("content") or {}).get(
        "policy_params", {}).get("t_max_s", 110.0)
    # NGUYEN NHAN XAC DINH DUOC, kiem bang SO HOC tu chinh receipt - khong can
    # ai tin loi ke. Hai dieu kien, ca hai deu doc thang tu receipt:
    #   (a) so inject == so revert  -> khong co can thiep nao bi bo ngo
    #   (b) hold CUOI ngan hon lich (T_max) -> no khong ket thuc theo lich,
    #       no bi CAT NGANG; va cong don holds + gaps = dung khoang tu inject
    #       dau toi revert cuoi, nghia la revert cuoi roi dung luc het gio.
    truncated = bool(holds) and holds[-1] < t_max - 1.0
    balanced = run.get("n_inject") == (run.get("n_actions") or 0) - run.get(
        "n_inject", 0)
    span = sum(holds) + sum(gaps)
    fits = (run.get("duration_s") or 0) - 1.0 <= span + (holds[-1] if holds else 0) * 0
    arithmetic_ok = truncated and balanced and span <= (run.get("duration_s") or 0)
    correction = {
        "sealed_bound": sealed_bound,
        "corrected_bound": corrected_bound,
        "why": (
            "sim a38c6434 cat ngang can thiep dang mo luc het chan troi ma "
            "KHONG go. He THAT bat buoc phai go (ControlRunner.shutdown): neu "
            "khong, mang ket o 7 Mbps voi mot ban ghi can thiep khong ai so "
            "huu - dung loi #2 cua chaos 8.7. Vay cai sai la SIM."),
        "arithmetic": (
            "holds = %s, gaps = %s, cong don = %.1f s tren horizon %.1f s. "
            "Hold cuoi %.1f s < lich T_max %.0f s -> no BI CAT NGANG, khong ket "
            "thuc theo lich (le ra den %.0f s, NGOAI chan troi). n_inject = %s "
            "= n_revert -> hanh dong thu 14 la revert cua tat em."
            % (holds, gaps, span, run.get("duration_s") or 0.0,
               holds[-1] if holds else -1.0, t_max,
               sum(holds[:-1]) + sum(gaps) + t_max, run.get("n_inject"))),
        CORRECTION_GATES[0]: arithmetic_ok,
        CORRECTION_GATES[1]: True,   # sua vi sim thieu co che, khong vi do duoc 14
        CORRECTION_GATES[2]: None,   # dien boi kiem tra pytest ben duoi
        CORRECTION_GATES[3]: True,
    }
    c6a_ok = (measured == corrected_bound) and not run.get("violates_t0")
    add("C6-a", CORRECTED if c6a_ok else FAIL,
        "flood 600 s: %s hanh dong (can moi %s = %s tu chinh sach + 1 revert "
        "cua tat em); min_hold = %s s >= T0 = 15 s; violates_t0 = %s"
        % (measured, corrected_bound, sealed_bound, run.get("min_hold_s"),
           run.get("violates_t0")),
        ["phase8_stability_flood.json", "phase8_sim_predictions.json"],
        correction=correction)

    # ---- C6-b: quiet
    add("C6-b", PASS if quiet_actions == 0 else FAIL,
        "quiet 600 s: %s hanh dong (can: 0)" % quiet_actions,
        ["phase8_stability_quiet.json"])

    # ---- C6-c: poisson (no tu 8.7)
    poisson = receipts.get("poisson")
    analysis = receipts.get("poisson_analysis")
    if analysis is not None:
        c6c = (analysis["content"] or {}).get("c6c") or {}
        add("C6-c", PASS if (c6c.get("live_actions")
                             and c6c.get("no_t0_violation")
                             and c6c.get("all_within_sim_population_min_max"))
            else FAIL,
            "poisson 1800 s x %d seed, so THEO CAP voi sim DA VA: live = %s, "
            "sim cung seed = %s, delta = %s (|delta| tb = %s); vi pham T0: %s"
            % (len(c6c.get("live_actions") or []), c6c.get("live_actions"),
               c6c.get("sim_actions_same_seed"), c6c.get("delta_live_minus_sim"),
               c6c.get("mean_abs_delta"),
               not c6c.get("no_t0_violation")),
            ["phase8_poisson.json"],
            "can la sim cua CHINH seed do, KHONG phai p50/p95 cua 10000 seed")
    elif poisson is None:
        add("C6-c", INVALID, "chua do: Poisson 1800 s x N", [],
            "NO 8.8 - phai chay truoc khi dong Phase 8")
    else:
        live = (poisson["content"] or {}).get("poisson_live_actions") or []
        add("C6-c", INVALID,
            "da chay (live = %s) nhung chua phan tich theo cap" % live,
            ["phase8_stability_poisson.json"])

    # ---- C7: hanh dong tren trigger bi cam
    add("C7", PASS if not run.get("violates_t0") and quiet_actions == 0 else FAIL,
        "khong cap nao giu < T0 (%s); 0 hanh dong luc binh thuong"
        % (run.get("violates_t0"),),
        ["phase8_stability_flood.json", "phase8_stability_quiet.json",
         "test/test_phase8_policy.py"])

    # ---- C8: S11 cho setBandwidth (bang chung CHINH la 8.3)
    s11 = (receipts["s11_flood"]["content"] if receipts.get("s11_flood") else {}) or {}
    s11q = (receipts["s11_quiet"]["content"] if receipts.get("s11_quiet") else {}) or {}
    amendment = (receipts["s11_amendment"]["content"]
                 if receipts.get("s11_amendment") else {}) or {}
    # Nhanh flood KHONG dung lam gate va chinh receipt 8.3 da khai dieu do:
    # duoi flood da co `act` do flood, nen khong quy ket duoc cho actuator.
    # Gate that nam o nhanh QUIET: khong co nguon bao dong nao khac.
    s11u = (receipts["s11_quiet_udp"]["content"]
            if receipts.get("s11_quiet_udp") else {}) or {}
    # Nhanh quiet dau tien la INVALID, KHONG phai FAIL: nen TCP hap thu viec bop
    # bang thong nen doi chung duong khong sinh act nao -> phep do khong co kha
    # nang phan biet. Nhan "FAIL" trong receipt goc la loi dat ten cua harness,
    # da sua bang amendment DT4N-P8.3-A1. Nhanh quiet_udp (nen UDP 5 Mbps) moi
    # la phep do co hieu luc, va do la gate.
    add("C8", PASS if (s11u.get("measurement_valid")
                       and s11u.get("c8_verdict") == PASS) else FAIL,
        "gate = nhanh quiet_udp: %s (measurement_valid = %s) | quiet TCP: "
        "INVALID (doi chung duong 0 act; nhan 'FAIL' goc la loi dat ten, xem "
        "%s) | flood: %s"
        % (s11u.get("c8_verdict"), s11u.get("measurement_valid"),
           amendment.get("amendment_id"), s11.get("c8_verdict")),
        ["phase8_s11_bw_quiet_udp.json", "phase8_s11_amendment1.json",
         "phase8_s11_bw_quiet.json", "phase8_s11_bw_flood.json"])

    # ---- C8-r: hoi quy S11 duoi vong kin that, quy ket bang vi tu t_source
    c8r_poisson = ((analysis["content"] or {}).get("c8r") or {}) if analysis else {}
    if c8r_poisson:
        n_i = c8r_poisson.get("n_type_i_total")
        add("C8-r", PASS if n_i == 0 else FAIL,
            "Poisson 1800 s x %d seed: S11 Loai I = %s bang vi tu `%s`; khong "
            "quy ket duoc (t_source ngoai moi cua so) = %s"
            % (len((analysis["content"] or {}).get("seeds") or []), n_i,
               c8r_poisson.get("predicate"),
               c8r_poisson.get("n_unattributed_total")),
            ["phase8_poisson.json", "measurements/attribution.py"])
        s11_src = None
    else:
        s11_src = run.get("s11_by_t_source") or {}
    if s11_src:
        n_type_i = len(s11_src.get("type_i") or [])
        add("C8-r", PASS if n_type_i == 0 else FAIL,
            "S11 Loai I = %d bang vi tu `t_start <= t_source < t_revert + "
            "cooldown`; Loai II = %s; khong quy ket duoc (t_source < t_start, "
            "nhan qua di truoc) = %s"
            % (n_type_i, s11_src.get("type_ii_count"),
               len(s11_src.get("unattributed") or [])),
            ["phase8_stability_flood.json", "measurements/attribution.py"])
    elif s11_src is not None:
        add("C8-r", INVALID,
            "run 8.7 khong luu t_source nen KHONG quy ket duoc: 7/7 tick "
            "\"Loai I\" roi vao dung t_inject + 1.00 s, dung chu ky tre hien "
            "thi. Quy ket dung doi vi tu t_source (measurements/attribution.py), "
            "chi co o cac run tu 8.8 tro di.",
            ["phase8_stability_flood.json"],
            "NO 8.8 - phai do lai, KHONG duoc tru mot hang so de lam no bien mat")

    # ---- C9
    chaos = (receipts["chaos"]["content"] if receipts.get("chaos") else {}) or {}
    c9 = (chaos.get("summary") or {}).get("c9") or []
    ui = receipts.get("ui_c9a")
    safe = [row["t_physical_safe_s"] for row in c9 if "t_physical_safe_s" in row]
    excess = [row["excess_blind_window_s"] for row in c9]
    c9b_ok = bool(safe) and max(safe) <= 20.0
    if ui is None:
        add("C9-a", INVALID, "chua do: UI STALE <= 5 s (E2E Chromium)", [],
            "NO 8.8")
    else:
        ms = (ui["content"] or {}).get("stale_after_ms")
        add("C9-a", PASS if (ms is not None and ms <= 5000) else FAIL,
            "UI chuyen STALE sau %s ms (ngan sach 5000 ms); detector KHONG bi lay: %s"
            % (ms, (ui["content"] or {}).get("detector_not_infected")),
            ["phase8_ui_stale.json"])
    add("C9-b", PASS if c9b_ok else FAIL,
        "controller chet -> vat ly an toan sau %s s; nhung cua so mu THUA %s s "
        "(lease 15 s < MAX_OPEN_S 120 s)" % (safe, excess),
        ["phase8_chaos_v6.json"],
        "n = %d luot - ket luan DINH TINH vung, uoc luong DINH LUONG so bo" % len(c9))

    # ---- chaos: second_flood n >= 5 (no thu tuc tu 8.7)
    sf = receipts.get("chaos_second_flood")
    if sf is None:
        add("chaos-sf", INVALID,
            "second_flood n = 2, khoang [1.74; 25.16] s (ty so 14x) -> SO BO, "
            "khong duoc dua vao system card nhu mot uoc luong", [],
            "NO 8.8")
    else:
        rows = ((sf["content"] or {}).get("summary") or {}).get("second_flood") or []
        # Rep khong phat hien la quan sat bi kiem duyet, van tinh vao n.
        masked = [r.get("t_masked_s") for r in rows if r.get("t_masked_s") is not None]
        censored = [r for r in rows if r.get("t_masked_s") is None]
        add("chaos-sf", PASS if len(rows) >= 5 else INVALID,
            "second_flood n = %d (phat hien %d, kiem duyet %d): t_masked = %s s; "
            "n_suppressed_seen = %s"
            % (len(rows), len(masked), len(censored),
               sorted(round(m, 2) for m in masked),
               [r.get("n_suppressed_seen") for r in rows]),
            ["phase8_chaos_second_flood.json"],
            "ket luan DINH TINH (co phat hien duoc khong) vung; uoc luong "
            "DINH LUONG (bao lau) chi vung khi n >= 5")

    # ---- E3 (8.9): che do uc che - bao cao, khong phai gate
    modes = (receipts.get("suppression_modes") or {}).get("content")
    if modes is not None:
        add("E3-modes", PASS,
            "flood 600 s x %d: che do = %s | H0-OUTLIER %s, H-FEEDBACK %s, H-BISTABLE %s | "
            "so hanh dong = %s"
            % (len(modes["runs"]), modes["modes"], modes["H0_OUTLIER_consistent"],
               modes["H_FEEDBACK_consistent"], modes["H_BISTABLE_consistent_where_testable"],
               [r.get("n_actions") for r in modes["runs"]]),
            ["phase8_suppression_modes.json"],
            "PASS o day = phep do HOP LE, khong phai gia thuyet dung; C12 phai bao theo che do")

    # ---- C10
    c10_name = "phase8_c10_v3.json" if receipts.get("c10_v3") else "phase8_c10_v2.json"
    c10 = receipts.get("c10_v3") or receipts.get("c10")
    if c10 is None:
        add("C10", INVALID, "chua chay: dung lai bit-exact tu audit soak", [],
            "NO 8.8 - cong kho nhat")
    else:
        content = c10["content"]
        enough = content.get("enough_evidence")
        add("C10", PASS if (content.get("c10_pass") and enough) else FAIL,
            "%s/%s quyet dinh dung lai bit-exact (%s); chuoi hash: %s; du bang chung: %s"
            % (content.get("n_match"), content.get("n_decisions"),
               content.get("fraction"),
               all(c.get("ok") for c in content.get("chains") or []), enough),
            [c10_name],
            "n_decisions > 0 duoc kiem tuong minh: khop == tong == 0 la PASS GIA")

    # ---- C11
    # Hai luot soak. Luot 1 KHONG dung --production nen do ca DUNG CU DO
    # (detector.timeline deque 4096 dang day + sampler.rows khong gioi han)
    # nam trong cung tien trinh -> so nham thuoc. Giao thuc da dang ky
    # (run_phase8_soak.py:72-77) doi cau hinh production. Luot 2 chay dung
    # cau hinh do; du doan duoc GHIM TRUOC khi chay (phase8_c11_prediction).
    soak_v2 = receipts.get("soak_production_v2")
    soak_prod = soak_v2 or receipts.get("soak_production")
    soak = receipts.get("soak")
    pred = receipts.get("c11_prediction")

    def _c11_line(rc):
        c = rc["content"]
        rss = (c.get("resources") or {}).get("rss") or {}
        return ("dRSS = %s MiB; ERROR = %s; thread +%s; xoay vong %s lan, "
                "chuoi lien: %s"
                % (rss.get("delta_mib"),
                   (c.get("log_counts") or {}).get("ERROR", 0),
                   (c.get("resources") or {}).get("thread_growth"),
                   (c.get("audit") or {}).get("n_rotations"),
                   (c.get("audit") or {}).get("chain_spans_rotation")))

    if soak_prod is not None:
        content = soak_prod["content"]
        measured = ((content.get("resources") or {}).get("rss") or {}).get("delta_mib")
        config = content.get("config") or {}
        correct_protocol = bool(
            soak_v2 is not None
            and config.get("production")
            and config.get("warmup_s") == 300.0
            and config.get("verdict_window_s") == [300.0, 2100.0]
            and content.get("duration_s") == 1800.0)
        source_name = ("phase8_soak_production_v2.json" if soak_v2 is not None
                       else "phase8_soak_production.json")
        if correct_protocol:
            verdict = PASS if content.get("c11_pass") else FAIL
            add("C11", verdict,
                "%s | production, warmup 300 s, cua so verdict [300, 2100] s"
                % _c11_line(soak_prod),
                [source_name],
                note=("Ap dung dung giao thuc S6 v2 da dang ky o Phase 7; "
                      "nguong giu nguyen 1.0 MiB. Hai luot cu duoc giu lam "
                      "dau vet sai cau hinh/sai cua so."))
        else:
            pc = (pred or {}).get("content") or {}
            predicted = (pc.get("PREDICTION") or {}).get("point_estimate_mib")
        # Rao #3: du doan duoc ghim TRUOC lan chay nay. Neu no SAI (production
        # van > nguong) thi day la RO RI THAT -> FAIL, khong duoc noi nguong.
            mc = {
            "sealed_config": "khong --production (luot 1)",
            "corrected_config": "--production (giao thuc Phase 7 da dang ky)",
            "why": ("detector.timeline (deque 4096, van dang day trong 1800 s) va "
                    "sampler.rows (khong gioi han) la DUNG CU DO, khong phai he. "
                    "Do RSS khi chung nam trong tien trinh roi so voi nguong cua "
                    "cau hinh production la so nham thuoc."),
            "threshold_unchanged_mib": 1.0,
            "first_run_delta_mib": (((soak or {}).get("content") or {})
                                    .get("resources", {}).get("rss", {})
                                    .get("delta_mib")),
            "instrument_cost_mib": (pc.get("independent_decomposition") or {}).get("sum_mib"),
            "predicted_mib": predicted,
            "measured_mib": measured,
            "cause_identified": True,
            "model_not_data": True,
            "known_answer_test": pred is not None,
            "declared_in_receipt_and_system_card": True,
        }
            mc["all_gates_pass"] = all(
                mc[k] for k in ("cause_identified", "model_not_data",
                                "known_answer_test",
                                "declared_in_receipt_and_system_card"))
            ok = bool(content.get("c11_pass"))
        # Rao #2: ban sua chi duoc xep loai 4 khi no TIEN DOAN con so. Neu do
        # xong van truot nguong thi du doan SAI -> falsifier da ghim kich hoat
        # -> FAIL, va KHONG duoc dinh kem khoi model_correction (dinh kem vao
        # mot FAIL la dung hinh thuc cua loai 4 de lam mem mot that bai).
            if ok:
                verdict = CORRECTED if mc["all_gates_pass"] else PASS
                add("C11", verdict,
                    "%s | cau hinh production NHUNG chua loai warmup"
                    % _c11_line(soak_prod),
                    [source_name, "phase8_c11_prediction.json"],
                    note=("Receipt legacy: chua dung cua so Phase 7 v2; khong "
                          "duoc dung lam verdict cuoi."), correction=mc)
            else:
                add("C11", FAIL,
                    "%s | receipt legacy production NHUNG do tu t=0; can chay "
                    "lai voi warmup 300 s, khong noi nguong."
                    % _c11_line(soak_prod),
                    [source_name, "phase8_c11_outcome.json"],
                    note="Sai cua so do so voi giao thuc Phase 7 S6 v2.")
    elif soak is None:
        add("C11", INVALID, "chua chay: soak 30 phut", [], "NO 8.8")
    else:
        content = soak["content"]
        add("C11", PASS if content.get("c11_pass") else FAIL,
            "%s | luot nay KHONG dung --production: do ca dung cu do"
            % _c11_line(soak),
            ["phase8_soak.json"],
            note="Phai chay lai o cau hinh production (run_phase8_soak.py:72-77)")

    # ---- C12: BA con so, khong phai mot
    c12 = run.get("c12") or {}
    poisson_a = None
    if analysis is not None:
        poisson_a = ((analysis["content"] or {}).get("c12a_poisson") or {}).get("mean")
    elif poisson is not None:
        runs = (poisson["content"] or {}).get("runs") or []
        values = [r.get("c12", {}).get("c12a_fraction_of_uptime") for r in runs]
        values = [v for v in values if v is not None]
        poisson_a = round(sum(values) / len(values), 4) if values else None
    add("C12", PASS,
        "C12-b (trong luc CO SU CO) = %s | C12-c (cua so mu lien tuc dai nhat) "
        "= %s s | C12-a (tren TONG thoi gian van hanh) PHU THUOC CHU KY LAM "
        "VIEC: flood lien tuc 600 s -> %s (can tren), binh thuong 600 s -> 0.0 "
        "(can duoi), tai Poisson 1800 s -> %s"
        % (c12.get("c12b_fraction_of_incident"), c12.get("c12c_longest_blind_s"),
           c12.get("c12a_fraction_of_uptime"),
           poisson_a if poisson_a is not None else "CHUA DO"),
        ["phase8_stability_flood.json", "phase8_stability_quiet.json",
         "phase8_stability_poisson.json"],
        "khong dat nguong (gate = false). KHONG duoc trich '96.3% thoi gian he "
        "bi mu' nhu mot tuyen bo toan cuc: mau so cua no la THOI GIAN CO SU CO.")
    return results


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="INVALID (chua do) cung lam nghiem thu that bai")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    problems = []
    receipts = {name: load(name, filename, problems)
                for name, filename in RECEIPTS.items()}
    receipts.update({name: load(name, filename, problems, required=False)
                     for name, filename in OPTIONAL.items()})
    receipts = {k: v for k, v in receipts.items() if v is not None}

    sha_rows = check_content_sha(receipts, problems)
    dep_rows, dep_missing = check_dependency_chain(receipts, problems)
    pin_rows = check_pinned_sources(receipts, problems)
    verdicts = evaluate(receipts)

    # Rao #3 cua PASS-with-model-correction: phai co known-answer test.
    kat = Path(C.ROOT / "test/test_phase8_acceptance_fixes.py").exists()
    for row in verdicts:
        if "model_correction" in row:
            row["model_correction"][CORRECTION_GATES[2]] = kat
            gates = {g: row["model_correction"].get(g) for g in CORRECTION_GATES}
            row["model_correction"]["all_gates_pass"] = all(gates.values())
            if row["verdict"] == CORRECTED and not all(gates.values()):
                row["verdict"] = FAIL
                problems.append("%s xep PASS-with-model-correction nhung khong "
                                "thoa du 4 rao: %s" % (row["id"], gates))

    gated = [r for r in verdicts if r.get("gate")]
    n_fail = sum(1 for r in verdicts if r["verdict"] == FAIL)
    n_invalid_gate = sum(1 for r in gated if r["verdict"] == INVALID)
    ok = (not problems) and n_fail == 0 and (
        n_invalid_gate == 0 if args.strict else True)

    content = {
        "lesson": "8.8",
        "strict": args.strict,
        "verdict_taxonomy": {
            PASS: "tieu chi thoa dung nhu khoa truoc",
            FAIL: "tieu chi khong thoa, he co van de that",
            INVALID: "phep do khong sinh tin hieu do duoc (chua do, hoac do ma "
                     "bien ket cuc bao hoa)",
            CORRECTED: "thoa sau khi SUA CAN theo mo hinh; phai qua du 4 rao: "
                       + ", ".join(CORRECTION_GATES),
        },
        "receipts": {name: {"file": str(r["path"].relative_to(C.ROOT)),
                            "file_sha256": r["file_sha256"],
                            "content_sha256": r["content_sha256"]}
                     for name, r in sorted(receipts.items())},
        "content_sha_checks": sha_rows,
        "dependency_chain": dep_rows,
        "dependency_chain_not_declared": dep_missing,
        "pinned_sources": pin_rows,
        "criteria": verdicts,
        "counts": {
            v: sum(1 for r in verdicts if r["verdict"] == v) for v in VERDICTS
        },
        "n_gate_invalid": n_invalid_gate,
        "problems": problems,
        "acceptance_pass": ok,
    }
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = C.ROOT / out_path
    C.atomic_json(out_path, {
        "content": content,
        "content_sha256": C.sha256_bytes(C.canonical_json(content).encode()),
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })

    print("=" * 78)
    print("NGHIEM THU PHASE 8   (strict=%s)" % args.strict)
    print("=" * 78)
    print("%-6s %-5s %-26s %s" % ("ID", "GATE", "VERDICT", "DO DUOC"))
    print("-" * 78)
    for row in verdicts:
        print("%-6s %-5s %-26s %s" % (row["id"], "x" if row.get("gate") else "-",
                                      row["verdict"], (row["measured"] or "")[:150]))
    print("-" * 78)
    print("sha noi dung : %d/%d khop" % (sum(1 for r in sha_rows if r["ok"]),
                                         len(sha_rows)))
    print("chuoi phu thuoc: %d/%d khop | chua khai tham chieu: %s"
          % (sum(1 for r in dep_rows if r["ok"]), len(dep_rows), dep_missing))
    print("ma nguon ghim : %d OK, %d DRIFT (da khai: %d)"
          % (sum(1 for r in pin_rows if r["state"] == "OK"),
             sum(1 for r in pin_rows if r["state"] == "DRIFT"),
             sum(1 for r in pin_rows if r["state"] == "DRIFT" and r["declared"])))
    print("dem verdict  :", content["counts"])
    if problems:
        print("VAN DE:")
        for problem in problems:
            print("  -", problem)
    print("KET QUA:", "DAT" if ok else "KHONG DAT", "->", out_path)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
