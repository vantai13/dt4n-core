#!/usr/bin/env python3
"""Huong VAT LY cua tung link -- nguon chan ly duy nhat.

VI SAO FILE NAY TON TAI (`L30`):

    `bridge/collector.py::canonical_link_key` sap xep hai dau link theo BANG
    CHU CAI de dat TEN. Ten can duy nhat -- viec do DUNG.

    Nhung `link_side_a_intf` da MUON thu tu do de quyet dinh CHIEU DO. Bang
    chu cai khong biet gi ve huong dong chay. Ket qua: `sorted(["sSRC","sA"])`
    cho `["sA","sSRC"]`, nen counter cua `uA` duoc doc theo chieu sA -> sSRC,
    la chieu KHONG CO LUU LUONG.

    Do duoc: `rho_uA = 0` o 98.06% mau, `rho_uB = 0` o 97.96% mau, suot ca 30
    run cua chien dich 23.8. Sau link con lai binh thuong (~0.1%) vi bang chu
    cai TINH CO dung voi chung. Khong co logic nao ca -- do la ly do loi song
    sot: no khong sai HE THONG, no sai NGAU NHIEN, nen moi kiem tra tong the
    (trung binh 8 link, tong 8 link) van "trong co ve on".

    Xem: results/LIVE/phase-23/aoi_decomposition.json::T5_partial_correlation
         docs/phase-23/00zzb-amendment-45c.md muc 4
         docs/phase-23/A076-amendment-76.md

NGUYEN TAC: TEN va HUONG la hai khai niem khac nhau. Ten do
`canonical_link_key` cap. Huong do file NAY cap. Khong cai nao duoc suy ra tu
cai kia.
"""
from __future__ import annotations

# (upstream, downstream) -- luu luong chay upstream -> downstream.
# PHAI khop `mininet/run_sync_v7.py::LINK_ENDPOINTS`; rang buoc do duoc ghim
# boi `test/test_link_rho_audit.py::test_direction_map_matches_topology`.
UPSTREAM_OF: dict[str, tuple[str, str]] = {
    "uA": ("sSRC", "sA"),
    "uB": ("sSRC", "sB"),
    "ac": ("sA", "sC"),
    "ad": ("sA", "sD"),
    "bc": ("sB", "sC"),
    "bd": ("sB", "sD"),
    "vC": ("sC", "sDST"),
    "vD": ("sD", "sDST"),
}


# Topology dt4n-core (tam giác): luồng chảy client -> switch -> server.
# PHẢI khớp mininet/topology.py::TriangleTopo.
# Trước khi thêm map này, upstream_node() trả None cho mọi link của
# dt4n-core, nên collector dán nhãn utilDirectionSource =
# "alphabetical_fallback" ở 8/8 link, suốt cả dataset v2.
UPSTREAM_OF_CORE: dict[str, tuple[str, str]] = {
    "h1-s1":   ("h1", "s1"),      # client gửi lên switch biên
    "h2-s1":   ("h2", "s1"),
    "h3-s1":   ("h3", "s1"),
    "s1-s2":   ("s1", "s2"),      # biên -> lõi
    "s1-s3":   ("s1", "s3"),
    "s2-s3":   ("s2", "s3"),      # srv1 -> srv2 qua bottleneck 5 Mbps
    "s2-srv1": ("s2", "srv1"),    # lõi -> server
    "s3-srv2": ("s3", "srv2"),
}
UPSTREAM_OF.update(UPSTREAM_OF_CORE)

def canonical_key(a: str, b: str) -> str:
    """Ban sao cua `bridge.collector.canonical_link_key`.

    CO Y giu doc lap: `twin/` khong duoc import `bridge/` (tang duoi khong
    import tang tren). Rang buoc "hai ban phai khop" duoc ghim bang test, chu
    khong bang import.
    """
    lo, hi = sorted([a, b])
    return "link-%s-%s" % (lo, hi)


def upstream_node(link_or_key: str) -> str | None:
    """Ten node THUONG NGUON, hoac `None` neu link khong nam trong ban do.

    Nhan ca ten logic (`"uA"`) lan canonical key (`"link-sA-sSRC"`).

    Tra `None` -- KHONG nem -- de collector con dung duoc tren topology khac
    (vd `topology3` cu). Nhung khi `None` thi collector PHAI dan nhan
    `utilDirectionSource = "alphabetical_fallback"`, tuc loi tro thanh ON AO
    thay vi im lang.
    """
    if link_or_key in UPSTREAM_OF:
        return UPSTREAM_OF[link_or_key][0]
    for a, b in UPSTREAM_OF.values():
        if canonical_key(a, b) == link_or_key:
            return a
    return None


def alphabetical_side_a_is_correct(link: str) -> bool:
    """Bang chu cai co TINH CO dung cho link nay khong?

    Ham nay ton tai de tai lap duoc `L30` bang mot BIEU THUC CHAY DUOC, chu
    khong phai bang mot doan van trong amendment. Neu ai do doi ten node
    trong tuong lai, test se do va chi thang vao co che.

    >>> [l for l in UPSTREAM_OF if not alphabetical_side_a_is_correct(l)]
    ['uA', 'uB']
    """
    up, down = UPSTREAM_OF[link]
    return up == sorted([up, down])[0]
