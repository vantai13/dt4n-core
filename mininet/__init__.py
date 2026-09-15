"""DT4N local Mininet layer package.

This project intentionally keeps its Phase 1 code in a directory named
``mininet``. That collides with the real Mininet Python package, whose modules
are also imported as ``mininet.net``, ``mininet.log``, and so on.

To support commands like ``python3 -m mininet.run_phase1`` while still allowing
imports from the real Mininet library, extend this package search path with the
installed Mininet package directory when it is present on the system.
"""

from __future__ import annotations

import glob
import os
import sys


def _extend_with_system_mininet() -> None:
    local_dir = os.path.dirname(__file__)
    candidates = []

    for entry in sys.path:
        if not entry:
            entry = os.getcwd()
        candidates.append(os.path.join(entry, "mininet"))

    candidates.extend(glob.glob("/usr/lib/python*/dist-packages/mininet"))
    candidates.extend(glob.glob("/usr/local/lib/python*/dist-packages/mininet"))
    candidates.extend(glob.glob("/usr/lib/python*/site-packages/mininet"))
    candidates.extend(glob.glob("/usr/local/lib/python*/site-packages/mininet"))

    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if candidate == os.path.abspath(local_dir):
            continue
        if os.path.isfile(os.path.join(candidate, "log.py")):
            if candidate not in __path__:
                __path__.append(candidate)
            return True
    return False


#: True khi khong tim thay Mininet that va cac stub o `_absent_mininet/` dang
#: duoc dung thay. Test doc co nay de KHONG bao gio doc mot ket qua mang tu
#: mot may khong co mang.
MININET_IS_STUB = False


def _fall_back_to_stubs() -> None:
    """Cho `from mininet.topo import Topo` import DUOC khi khong co Mininet that.

    Ly do o `_absent_mininet/_stub.py`. Tom tat: cac module cua chinh du an
    import Mininet that o MUC MODULE, nen tren mot clone sach khong co Mininet
    -- tuc moi runner CI -- `pytest` dung o buoc THU GOM va khong chay duoc MOT
    test nao. Marker `live` chi bo qua luc CHAY nen khong cuu duoc.

    Stub cho qua im lang doi voi ghi nhat ky, va NO NGAY khi ai do thuc su
    dung mang. Chung chi duoc gan khi Mininet that vang mat.
    """
    global MININET_IS_STUB
    stub_dir = os.path.join(os.path.dirname(__file__), "_absent_mininet")
    if os.path.isdir(stub_dir) and stub_dir not in __path__:
        __path__.append(stub_dir)
        MININET_IS_STUB = True


if not _extend_with_system_mininet():
    _fall_back_to_stubs()
