#!/usr/bin/env python3
"""Hop dong B + C: bien Action THUAN thanh Intervention + command dict.

Tach rieng khoi policy.py de policy van THUAN (khong biet gi ve routing, Ditto
hay Mininet) va van mo phong duoc o 8.2.
"""
from __future__ import annotations

from ml.blast_radius import Routing, radius
from ml.intervention_log import Intervention

# Ten hanh dong RIENG cho actuator moi: audit phai phan biet duoc voi
# admin_down cua Phase 7 (vung anh huong va hau qua khac han).
ACTION_NAME = {"inject": "inject:rate_limit", "revert": "revert:rate_limit"}
SUBJECT = "setBandwidth"
THING_PREFIX = "org.dt4n:link-"


def to_intervention(action, routing: Routing, t_start_wall: float) -> Intervention:
    """t_start la WALL CLOCK: FSM so no voi t_source cua snapshot (M8)."""
    if action.kind not in ACTION_NAME:
        raise ValueError("action la thuoc loai khong ghi lai duoc: %r" % action.kind)
    targets = {"links": [action.link], "flows": []}
    return Intervention(
        id=action.intervention_id,
        t_start=float(t_start_wall),
        actor="controller",
        action=ACTION_NAME[action.kind],
        targets=targets,
        # `radius`, KHONG `radius_with_detour`: setBandwidth khong doi topology
        # nen Ryu khong reroute, khong co hanh lang vong. Luat da ghim trong
        # models/detector-release-1.0.0.json::suppression_radius_rule:
        # "radius_with_detour for link-state admin_down interventions;
        #  radius for every other intervention".
        # Dung `flows` thay `links` se lam mu 16/16 entity thay vi 15/16.
        blast_radius=radius(routing, targets),
        routing_sha256=routing.sha256,
    )


def to_command(action) -> dict:
    """Lenh TUYET DOI (lu y dang). correlation id = intervention_id.

    Gui lai lan hai: command_agent tra ket qua cu tu cache (processed_result)
    -> khong cham Mininet. Cache mat khi agent restart -> lenh chay lai ->
    VO HAI vi lenh lu y dang. Dedup chi la TOI UU; LU Y DANG moi la bao dam,
    vi kenh truyen la at-least-once, khong phai exactly-once.
    """
    return {
        "subject": SUBJECT,
        "target": THING_PREFIX + action.link,
        "params": {"bw": float(action.bw_mbps)},   # TUYET DOI, khong tuong doi
        "cid": action.intervention_id,
    }
