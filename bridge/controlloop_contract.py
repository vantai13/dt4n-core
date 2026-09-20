#!/usr/bin/env python3
"""Hop dong D - Thing `org.dt4n:controlloop`: controller cong bo trang thai.

Vi sao can: controller CUNG CO THE CHET. Neu no chet giua luc dang gioi han
bang thong thi khong ai biet - dashboard van xanh, mang van bi bop. Do la C9,
va de C9 do duoc thi controller phai co freshness RIENG tren twin.

To hop nguy hiem phai nhin thay duoc:
    detector  SONG, bao normal          <- trong rat on
    controller CHET, dang MITIGATING    <- khong ai go gioi han nua
Mot nhan freshness duy nhat se de detector song CHE MAT controller chet.

Khuon giong bridge/detector_contract.py: mot Thing, mot PATCH nguyen tu,
KHONG BAO GIO sinh `null`.
"""
from __future__ import annotations

from bridge.ditto_common import NAMESPACE

CONTROLLOOP_THING_ID = NAMESPACE + ":controlloop"
TTL_TICKS = 3
TICK_INTERVAL_MS = 1000
MODES = ("IDLE", "MITIGATING", "PROBING", "HOLD")


def initial_controlloop_body(policy_id: str) -> dict:
    """KHONG BAO GIO khoi tao la IDLE.

    IDLE nghia la "toi dang chay va khong co gi de lam". Truoc khi controller
    khoi dong lan dau, su that la "toi chua tung chay" - khac han. Nguyen tac
    fail-safe: gia tri mac dinh phai la gia tri AN TOAN NHAT, khong phai gia
    tri THUONG GAP NHAT. Cung khuon initial_detector_body (unknown/never_started).
    """
    return {
        "policyId": policy_id,
        "attributes": {"type": "controller", "role": "closed-loop-controller"},
        "features": {
            "decision": {
                "properties": {
                    "mode": "HOLD",
                    "target": "",
                    "limitMbps": 0.0,
                    "reason": "never_started",
                    "decidedAt": "",
                }
            },
            "schedule": {
                "properties": {
                    "holdRemainingS": 0.0,
                    "probeRemainingS": 0.0,
                    "attempt": 0,
                    "episode": 0,
                }
            },
            "freshness": {
                "properties": {
                    "bootId": "",
                    "seq": -1,
                    "heartbeatAt": "",
                    "ttlTicks": TTL_TICKS,
                    "tickIntervalMs": TICK_INTERVAL_MS,
                    "dropped": 0,
                }
            },
            "provenance": {
                "properties": {
                    "policySha256": "",
                    "preregSha256": "",
                    "simPredictionsSha256": "",
                    "detectorReleaseSha256": "",
                }
            },
        },
    }


def build_document(
    cstate,
    params,
    *,
    boot_id: str,
    seq: int,
    heartbeat_at: str,
    decided_at: str,
    now_mono: float,
    dropped: int,
    provenance: dict,
) -> dict:
    """Merge-patch body cho Thing controlloop; khong bao gio sinh `None`.

    `holdRemainingS` / `probeRemainingS` la KHOANG (giay con lai), KHONG phai
    moc thoi gian. Ba ly do doc lap:
      1. dong ho trinh duyet cua nguoi van hanh khong dong bo voi may chu;
      2. time.time() co the NHAY LUI khi NTP hieu chinh -> "con lai -4 giay";
      3. controller dem bang time.monotonic(), ma monotonic KHONG co y nghia
         lien tien trinh - so cua no vo nghia voi bat ky ai khac.
    Consumer tu dem nguoc bang dong ho cua chinh no; sai so toi da = do tre
    mang (~22 ms), khong phu thuoc lech dong ho.
    """
    if cstate.mode not in MODES:
        raise ValueError("mode khong hop le: %r" % (cstate.mode,))
    remaining = _remaining(cstate.deadline_mono, now_mono)
    probe_remaining = _remaining(cstate.window_end_mono, now_mono)
    limit = params.limit_mbps if (cstate.open_id and cstate.target) else 0.0
    return {
        "features": {
            "decision": {
                "properties": {
                    "mode": cstate.mode,
                    "target": cstate.target or "",      # chuoi rong, KHONG null
                    "limitMbps": float(limit),
                    "reason": cstate.reason or "",
                    "decidedAt": decided_at,
                }
            },
            "schedule": {
                "properties": {
                    "holdRemainingS": remaining,
                    "probeRemainingS": probe_remaining,
                    "attempt": int(cstate.attempt),
                    "episode": int(cstate.episode),
                }
            },
            "freshness": {
                "properties": {
                    "bootId": boot_id,
                    "seq": int(seq),
                    "heartbeatAt": heartbeat_at,
                    "ttlTicks": TTL_TICKS,
                    "tickIntervalMs": TICK_INTERVAL_MS,
                    "dropped": int(dropped),
                }
            },
            "provenance": {"properties": {key: str(value)
                                          for key, value in provenance.items()}},
        }
    }


def _remaining(deadline_mono, now_mono) -> float:
    if deadline_mono is None:
        return 0.0
    return round(max(0.0, float(deadline_mono) - float(now_mono)), 3)


def check_document(document: dict) -> list[str]:
    """Tra danh sach vi pham hop dong D; rong nghia la dat."""
    problems = []
    features = (document or {}).get("features")
    if not isinstance(features, dict):
        return ["D0 thieu features"]
    for name in ("decision", "schedule", "freshness", "provenance"):
        if name not in features:
            problems.append("D1 thieu feature %s" % name)
    _check_no_null(features, problems)
    decision = (features.get("decision") or {}).get("properties") or {}
    if decision.get("mode") not in MODES:
        problems.append("D2 mode khong hop le: %r" % decision.get("mode"))
    schedule = (features.get("schedule") or {}).get("properties") or {}
    for key in ("holdRemainingS", "probeRemainingS"):
        value = schedule.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append("D3 %s phai la so (KHOANG, khong phai moc)" % key)
        elif value < 0:
            problems.append("D3 %s am" % key)
    fresh = (features.get("freshness") or {}).get("properties") or {}
    if not isinstance(fresh.get("seq"), int) or isinstance(fresh.get("seq"), bool):
        problems.append("D4 thieu seq nguyen")
    return problems


def _check_no_null(node, problems, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if value is None:
                problems.append("D1 gia tri null tai %s%s" % (path, key))
            else:
                _check_no_null(value, problems, path + key + ".")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _check_no_null(value, problems, "%s[%d]." % (path, index))
