"""Stub cho `mininet.log`.

Ghi nhat ky KHONG phai mot phep do, nen o day cho qua im lang: neu `info()` no
thi mot script chi dang in tien trinh cung lam hong buoc thu gom, ma khong doi
lay duoc tinh an toan nao. Moi thu DUNG MANG van no -- xem _stub.py.
"""
from __future__ import annotations


def setLogLevel(*args, **kwargs) -> None:  # noqa: N802 -- giu dung ten Mininet
    return None


def info(*args, **kwargs) -> None:
    return None


def output(*args, **kwargs) -> None:
    return None


def error(*args, **kwargs) -> None:
    return None


def warn(*args, **kwargs) -> None:
    return None


def debug(*args, **kwargs) -> None:
    return None
