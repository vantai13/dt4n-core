#!/usr/bin/env python3
"""Quy ket mot tick `act` cho mot can thiep - bang DUNG vi tu ma FSM dung.

Van de bat duoc o 8.7: 7/7 tick "Loai I" roi vao dung t_inject + 1.00 s. Cach
xu ly luc do la "tru tre hien thi 1.5-2.0 s", va no trong giong noi dinh nghia
du ban chat khong phai. Ban vao day thay bang mot vi tu KHONG CO HANG SO NAO:

    InterventionLog.active(source_time) so voi t_source cua SNAPSHOT.

Cuoc dua that khong phai `ghi log vs gui lenh` (M5 da xu ly) ma la `ghi log vs
snapshot DA DANG BAY`: collector lay mau tai t_source, FSM cham no vai tram ms
sau. Neu can thiep duoc ghi vao GIUA hai moc do, snapshot ay bi cham dua tren
mot so can thiep CHUA TON TAI luc no duoc lay mau. He KHONG sai - no da so
dung t_source roi (ml/fsm.py). Cai sai la quy ket tick theo dong ho TUONG.

Mot tick co t_source < t_start la NHAN QUA DI TRUOC: no khong the do can thiep
gay ra, nen no khong phai bang chung cho "uc che le ra phai bat ma khong bat".
"""
from __future__ import annotations

COOLDOWN_S = 8.0     # models/detector-release-1.0.0.json :: fsm_params


def in_intervention_window(t_source, t_start, t_revert, cooldown_s=COOLDOWN_S,
                           max_open_s=120.0):
    """Vi tu DUY NHAT. Sao chep y nguyen bien cua InterventionLog.active()."""
    if t_source is None:
        return False
    end = (t_revert + cooldown_s) if t_revert is not None else (t_start + max_open_s)
    return t_start <= t_source < end


def source_time_index(timeline):
    """(bootId, seq) -> t_source, tu timeline cua DetectorRunner.

    Khoa bang CA bootId: hai lan chay detector co the dung lai day seq.
    """
    return {(entry["bootId"], int(entry["seq"])): entry.get("t_source")
            for entry in timeline if entry.get("seq") is not None}


def classify(rows, paired, zone, tmap, cooldown_s=COOLDOWN_S):
    """Quy ket moi tick `act` -> (type_i, type_ii, unattributed).

    type_i        : t_source THUOC cua so mot can thiep VA moi entity vi pham
                    nam trong vung -> uc che le ra phai bat ma khong bat. GATE.
    type_ii       : t_source thuoc cua so nhung co entity NGOAI vung -> lo hong
                    uc che toan-hoac-khong, quy cho flood/thiet ke, khong phai loi.
    unattributed  : t_source KHONG thuoc cua so nao (thuong la t_source < t_start:
                    nhan qua di truoc) -> khong phai bang chung cho ca hai.
    """
    type_i, type_ii, unattributed = [], [], []
    for row in rows:
        if row.get("kind") != "decision":
            continue
        view = row.get("input") or {}
        if view.get("state") != "act":
            continue
        key = (view.get("bootId"), int(view.get("seq", -1)))
        t_source = tmap.get(key)
        owner = next(
            (p for p in paired
             if in_intervention_window(t_source, p["t_inject"], p["t_revert"],
                                       cooldown_s)),
            None,
        )
        affected = set(view.get("affected") or ())
        item = {
            "t_wall": row.get("t_wall"),
            "t_source": t_source,
            "seq": view.get("seq"),
            "affected": sorted(affected),
            "owner": None if owner is None else owner["key"],
            "t_start": None if owner is None else owner["t_inject"],
            "lead_s": (None if (owner is None or t_source is None)
                       else round(t_source - owner["t_inject"], 3)),
        }
        if owner is None:
            # Vi sao khong thuoc: ghi ra de nguoi doc tu kiem, khong bat tin.
            nearest = min(
                (p for p in paired if p["t_inject"] is not None),
                key=lambda p: abs((t_source or 0.0) - p["t_inject"]),
                default=None,
            )
            if nearest is not None and t_source is not None:
                item["nearest_t_start"] = nearest["t_inject"]
                item["t_source_minus_t_start"] = round(
                    t_source - nearest["t_inject"], 3)
            unattributed.append(item)
        elif affected and affected <= zone:
            type_i.append(item)
        else:
            type_ii.append(item)
    return type_i, type_ii, unattributed
