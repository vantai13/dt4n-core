#!/usr/bin/env python3
"""Phan quyet SLO Phase 7 — HAM THUAN. Khong doc raw, khong cham lai, khong ai go tay.

Quy tac phat hanh = amendment 3 cua 6R (KHONG phai "moi SLO PASS"):
    released = G1 and G2 and G3 and G4
    G1, G2  : mang sang tu 6R (tap R dung mot lan; logic ml/*.py trung bit)
    G3      : 6R G3 (S11 offline tren R-O)  AND  S11 LIVE (amendment 4: "phai do S11 live")
    G4      : S8 AND S9 AND S12 LIVE        (amendment 3; S12 bi hoan sang Phase 7)
S1 FAIL cua 6R KHONG phai cong phat hanh: no la gioi han da khai, giu nguyen FAIL.
"""
from __future__ import annotations

import operator

OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq}
ORDER = ["S1", "S2", "S3", "S4", "S4b", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"]
CARRIED = {"S1", "S2", "S3", "S4b", "S7", "S8", "S9", "S13"}
RULE = "phan quyet = so da niem phong so voi slo.target; khong nguoi nao go tay"


def judge(target: dict, value) -> str:
    if value is None:
        return "NO_DATA"
    return "PASS" if OPS[target["op"]](value, target["value"]) else "FAIL"


def _v6(v6r: dict, sid: str) -> dict:
    row = v6r["slo"].get(sid, {})
    return {"verdict": row.get("verdict"),
            "value": row.get("value", row.get("value_ms")), "from": row.get("from")}


def live_values(rc: dict) -> dict:
    """Moi so live lay tu DUNG MOT truong cua receipt da niem phong."""
    s12, e2e, s11, ct, soak = (rc.get(k) for k in ("s12", "e2e", "s11", "contention", "soak"))
    out = {}
    if s12:
        out["S12"] = {"value": s12["kill_to_stale"]["max_ms"] if s12["ok"] == s12["trials"] else None,
                      "field": "kill_to_stale.max_ms (moi trial, khong phai p95)",
                      "extra": {"p95_ms": s12["kill_to_stale"]["p95_ms"], "trials": s12["trials"],
                                "all_clear_while_stale": s12["all_clear_while_stale"],
                                "first_load_dead_detector": s12["first_load_dead_detector"]}}
    if e2e:
        out["S4"] = {"value": e2e["budgets"]["s4_like_from_cmd"]["p95_ms"],
                     "field": "budgets.s4_like_from_cmd.p95_ms (cung dinh nghia 6R: inject cmd -> san sang)",
                     "extra": {"n": e2e["n_detected"], "event": e2e.get("event")}}
    if ct:
        out["S5"] = {"value": ct["S5_live_p95_ms_worst_block"], "field": "S5_live_p95_ms_worst_block (ABBA)",
                     "extra": {"cycle_scan_p95_ms_mean": ct["cycle_scan_p95_ms_mean"]}}
    if soak:
        out["S6"] = {"value": soak["S6_v2"]["delta_mib"],
                     "field": "S6_v2.delta_mib (prereg DT4N-P7-S6-V2: bo warmup 300 s)",
                     "extra": {"v1_protocol_same_run_mib": soak["v1_protocol_same_run"]["delta_mib"],
                               "errors": soak["errors"]}}
    if s11:
        lf = s11["arms"]["log_first"]
        out["S11"] = {"value": lf["act_entries"] if lf["n"] >= 3 else None,
                      "field": "arms.log_first.act_entries (n >= 3 can thiep that)",
                      "extra": {"n": lf["n"], "controls": {k: s11["arms"][k] for k in ("log_late", "no_log")},
                                "lease_pass": s11["verdict"]["lease_pass"]}}
    return out


def derive(slo_doc: dict, v6r: dict, rc: dict, pins_ok: bool, history: dict | None = None) -> dict:
    slo = {s["id"]: s for s in slo_doc["slo"]}
    live = live_values(rc)
    rows = {}
    for sid in ORDER:
        s, old = slo[sid], _v6(v6r, sid)
        row = {"sli": s["sli"], "target": s["target"], "phase6r": old}
        if sid == "S10":
            row.update(final="REPORT_ONLY", basis="khong co nguong; hanh vi moi: guard 7.1 KN1 -> "
                                                   "unknown(out_of_operating_range) tren 6-10 Mbps")
        elif sid in CARRIED:
            row.update(final=old["verdict"] if pins_ok else "INVALID",
                       basis="mang sang 6R: ml/*.py + models trung bit voi phase6r_manifest"
                             if pins_ok else "logic 6R da troi -> khong mang sang duoc")
        else:
            lv = live.get(sid)
            verdict = judge(s["target"], lv["value"]) if lv else "NO_DATA"
            if sid == "S11" and old["verdict"] != "PASS":
                verdict = "FAIL"                                  # G3 can CA offline lan live
            row.update(phase7=lv, final=verdict, basis="do LIVE tren commit dong bang")
        if history and sid in history:
            row["history"] = history[sid]
        rows[sid] = row

    def ok(sid):
        return rows[sid]["final"] == "PASS"

    g6 = v6r["gates"]
    gates = {"G1": bool(g6["G1"]), "G2": bool(g6["G2"]),
             "G3": bool(g6["G3"]) and ok("S11"),
             "G4": ok("S8") and ok("S9") and ok("S12")}
    gates["released"] = all(gates.values())
    budgets = {}
    if rc.get("e2e"):
        b = rc["e2e"]["budgets"]
        budgets = {k: {"p95_ms": b[k]["p95_ms"], "target_ms": t, "meets": b[k]["p95_ms"] <= t}
                   for k, t in (("e2e_from_event", 5000), ("twin_ui", 1000))}
    return {"rule": RULE, "release_rule": "amendment 3: released = G1 & G2 & G3 & G4 (khong phai moi SLO PASS)",
            "slo": rows, "gates": gates, "budgets_master_plan": budgets,
            "fails_declared": [sid for sid in ORDER if rows[sid]["final"] == "FAIL"]}
