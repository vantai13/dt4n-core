#!/usr/bin/env python3
"""Luat dinh vi cua controller Phase 8 - HAM THUAN.

Tra loi cau hoi thu ba ma detector khong tra loi: "AI gay ra?"
(detection -> localization -> root cause; detector chi lam ve thu nhat va mot
phan ve thu hai qua evidence.affected).

Khong I/O, khong dong ho, khong random, khong doc file. Moi thu di vao qua tham so.
Nho vay: test bang liet ke (8.1), mo phong duoc (8.2), dung lai bit-exact (8.8/C10).
"""
from __future__ import annotations

from dataclasses import dataclass

# Tien to Thing id; khop bridge/ditto_common.py::NAMESPACE ('org.dt4n') va
# bridge/detector_contract.py::_thing_id. De o day duoi dang hang so vi ham
# nay khong duoc phep import runtime (giu tinh thuan + khong keo theo I/O).
HOST_PREFIX = "org.dt4n:host-"

# Ly do KHONG hanh dong. Hang co ten de audit va test tham chieu duoc,
# thay vi so sanh chuoi tu do rai rac trong code.
NO_CLIENT = "no_client_candidate"
AMBIGUOUS = "ambiguous_multiple_clients"
SINGLE = "single_client_candidate"


@dataclass(frozen=True)
class Localization:
    """Ket qua dinh vi. frozen=True de khong ai lo tay sua sau khi ghi audit."""

    target: str | None           # ten host, vi du "h1"; None nghia la khong hanh dong
    reason: str                  # vi sao chon / vi sao khong
    candidates: tuple[str, ...]  # tap ung vien, de audit dung lai duoc


def client_candidates(affected, roles) -> tuple[str, ...]:
    """Loc tu evidence.affected ra cac host co role='client'.

    affected: iterable Thing id, vi du ["org.dt4n:host-h1", "org.dt4n:link-h1-s1"]
    roles:    dict ten host -> role, doc tu attributes cua snapshot/twin.
              KHONG hardcode {'h1','h2','h3'}: topology tham so hoa so client.
    """
    out = []
    for thing_id in affected or ():
        if not isinstance(thing_id, str) or not thing_id.startswith(HOST_PREFIX):
            continue
        name = thing_id[len(HOST_PREFIX):]
        if roles.get(name) == "client":
            out.append(name)
    return tuple(sorted(set(out)))


def localize(affected, roles) -> Localization:
    """LUAT DINH VI v2 - khong tham so tu do, fail-closed.

    |candidates| == 0  -> khong hanh dong (khong phai flood tu client)
    |candidates| == 1  -> muc tieu la ung vien do
    |candidates| >= 2  -> khong hanh dong (mo ho; bao nguoi)

    Vi sao khong co nguong gap Delta: tren toan bo du lieu da mo (Phase 5 C/F +
    Phase 6R R-set), tai moi tick act tap ung vien co 0, 1 hoac 3 phan tu, va
    truong hop 3 phan tu la cac run tai cao RN-load8M/10M - noi dung phai la
    KHONG hanh dong. Nhanh Delta se la code chua tung chay tren du lieu that,
    ma code chua tung chay thi khong phai bang chung.
    """
    cands = client_candidates(affected, roles)
    if not cands:
        return Localization(None, NO_CLIENT, cands)
    if len(cands) > 1:
        return Localization(None, AMBIGUOUS, cands)
    return Localization(cands[0], SINGLE, cands)


def roles_from_snapshot(snapshot) -> dict:
    """Doc role tu chinh snapshot/twin; khong hardcode ten host.

    Tach khoi localize() de localize() van thuan va van nhan roles tu bat ky
    nguon nao (snapshot offline, twin live, hay bang co dinh trong test).
    """
    out = {}
    for key, thing in (snapshot.get("things") or {}).items():
        if not key.startswith("host-"):
            continue
        attributes = thing.get("attributes") or {}
        out[key[len("host-"):]] = attributes.get("role")
    return out
