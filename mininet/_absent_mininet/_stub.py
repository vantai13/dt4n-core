"""Placeholders used ONLY when the real Mininet package is not installed.

Vi sao ton tai: thu muc `mininet/` cua kho nay la GOI CUA CHINH DU AN va trung
ten voi Mininet that. Cac module nhu `mininet/topology_tandem.py` viet
`from mininet.topo import Topo` o MUC MODULE. Tren mot may khong co Mininet he
thong -- moi runner CI -- import do no o thoi diem THU GOM, nen `pytest` dung
lai voi "collect error" TRUOC KHI chay bat ky test nao. Marker `live` khong cuu
duoc: no chi bo qua luc CHAY.

Nguyen tac cua cac placeholder nay:

  · GHI NHAT KY thi cho qua im lang -- no khong phai mot phep do.
  · DUNG MANG thi PHAI no ngay va noi ro vi sao. Mot stub am tham dung mang la
    dung loai "den xanh rong" ma kho nay dang tim cach diet.

Chung chi duoc gan vao `mininet.__path__` khi KHONG tim thay Mininet that
(xem `mininet/__init__.py`), nen tren may tac gia co Mininet that chung khong
bao gio duoc dung toi.
"""
from __future__ import annotations

MESSAGE = (
    "%s can Mininet that, nhung goi Mininet he thong khong duoc cai. "
    "Day la mot stub dung de `pytest` THU GOM duoc bo test tren clone sach; "
    "no khong dung duoc mang. Cai Mininet (`sudo apt-get install mininet`) "
    "roi chay lai, hoac chay bai test nay voi marker `live` tren may co Mininet."
)


def _explode(what: str):
    raise RuntimeError(MESSAGE % what)


class _NeedsRealMininet:
    """Ke thua duoc luc import, no ngay khi ai do thuc su khoi tao."""

    _WHAT = "mininet"

    def __init__(self, *args, **kwargs):
        _explode(type(self)._WHAT)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Giu nguyen ten cua lop con trong thong bao loi.
        cls._WHAT = getattr(cls, "_WHAT", cls.__name__)
