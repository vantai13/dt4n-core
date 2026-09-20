#!/usr/bin/env python3
"""Kiem suc khoe Ditto/Mongo TRUOC moi luot do (Lesson 8.7).

Vi sao can: o 8.6, container MongoDB cham tran cgroup 252,4/256 MiB -> truy van
55 s -> Ditto tra 503 -> BON KHOI do bi hong ma khong ai biet cho toi khi phan
tich. Nguong 90% tran cho canh bao TRUOC khi phep do hong.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL, NAMESPACE  # noqa: E402

MONGO_CONTAINER = "dt4n-aoi-smoke-mongodb-1"
LATENCY_LIMIT_MS = 2000.0
MEM_WARN_FRACTION = 0.90


class InfraUnhealthy(RuntimeError):
    """Ha tang khong du khoe de do: luot nay VO HIEU, khong phai FAIL."""


def _parse_mem(text: str):
    """'252.4MiB / 256MiB' -> (252.4, 256.0) tinh bang MiB."""
    def one(value):
        value = value.strip()
        for unit, scale in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1 / 1024.0)):
            if value.endswith(unit):
                return float(value[: -len(unit)]) * scale
        return None

    if "/" not in text:
        return None, None
    used, limit = text.split("/", 1)
    return one(used), one(limit)


def mongo_memory():
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}",
             MONGO_CONTAINER],
            capture_output=True, text=True, timeout=15, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    return _parse_mem(out.strip())


def check(raise_on_fail=True) -> dict:
    started = time.monotonic()
    status, error = None, None
    try:
        response = requests.get(
            "%s/things/%s:detector" % (DITTO_BASE_URL, NAMESPACE),
            auth=DITTO_AUTH, timeout=10)
        status = response.status_code
    except requests.RequestException as exc:
        error = type(exc).__name__
    latency_ms = (time.monotonic() - started) * 1000.0
    used, limit = mongo_memory()
    fraction = (used / limit) if (used and limit) else None
    # Chu y: bo nho cao mot minh KHONG phai hong. Chu ky hong that o 8.6 la
    # LATENCY 55 s + HTTP 503; Mongo van chay o ~90% tran trong trang thai binh
    # thuong (WiredTiger giu cache sat tran). Nen bo nho la CANH BAO SOM, con
    # dieu kien VO HIEU la status/latency.
    healthy = status == 200 and latency_ms <= LATENCY_LIMIT_MS
    memory_warning = fraction is not None and fraction >= MEM_WARN_FRACTION
    report = {
        "healthy": healthy, "http_status": status, "error": error,
        "latency_ms": round(latency_ms, 1),
        "mongo_used_mib": used, "mongo_limit_mib": limit,
        "mongo_fraction": None if fraction is None else round(fraction, 3),
        "memory_warning": bool(memory_warning),
        "checked_at": time.time(),
    }
    if not healthy and raise_on_fail:
        raise InfraUnhealthy(
            "Ditto khong khoe: status=%s latency=%.0fms mongo=%s/%s MiB "
            "-> luot nay VO HIEU, restart roi chay lai"
            % (status, latency_ms, used, limit))
    return report


def main() -> int:
    report = check(raise_on_fail=False)
    print(report)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
