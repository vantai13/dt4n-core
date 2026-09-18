"""Guard vùng vận hành — Phase 7.1.

Module này định nghĩa đại lượng đo từ snapshot, ngưỡng chỉ suy ra từ tám
run train Phase 5, guard có hysteresis, và phép probe chỉ được dùng ngưỡng
đã niêm phong trong preregistration.
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path

from ml import campaign as C


QUANTITY_ID = "min_client_txRate_mbps"
TRAIN_DIR = "data/phase5/raw"
TRAIN_RUN_IDS = (
    "N-load1M-s1001-r1", "N-load1M-s1002-r2",
    "N-load2M-s1003-r1", "N-load2M-s1004-r2",
    "N-load4M-s1005-r1", "N-load4M-s1006-r2",
    "N-vary-s1007-r1", "N-vary-s1008-r2",
)
EXIT_TICKS = 3
LFS_MAGIC = "version https://git-lfs"


class FirewallError(ValueError):
    """Ngưỡng được yêu cầu từ dữ liệu không thuộc tập train đã đăng ký."""


class LfsPointerError(RuntimeError):
    """File vẫn là Git LFS pointer, chưa có dữ liệu thật."""


def client_tx_mbps(snapshot: dict):
    """Trả txRate (Mbps) của mọi client; thiếu/không hợp lệ thì trả None."""
    values = []
    for thing in (snapshot.get("things") or {}).values():
        attrs = thing.get("attributes") or {}
        if attrs.get("type") != "host" or attrs.get("role") != "client":
            continue
        traffic = (thing.get("features") or {}).get("traffic") or {}
        if traffic.get("rateValid") is not True:
            return None
        value = traffic.get("txRate")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None
        values.append(value * 8.0 / 1e6)
    return values or None


def g(snapshot: dict):
    """Sàn tải đồng đều: txRate của client chậm nhất, tính bằng Mbps."""
    values = client_tx_mbps(snapshot)
    return None if values is None else min(values)


def read_run(path) -> list[dict]:
    """Đọc một run và dừng rõ ràng nếu nó vẫn chỉ là LFS pointer."""
    path = Path(path)
    with open(path, encoding="utf-8", errors="ignore") as handle:
        if handle.read(len(LFS_MAGIC)) == LFS_MAGIC:
            raise LfsPointerError(
                "%s là con trỏ LFS; chạy `git lfs pull` trước" % path
            )
    return C.read_snapshots(path)


def _assert_train_path(path) -> str:
    resolved = Path(path).resolve()
    train_dir = (C.ROOT / TRAIN_DIR).resolve()
    if resolved.parent != train_dir or not resolved.name.endswith(".jsonl"):
        raise FirewallError(
            "ngưỡng chỉ được tính từ %s, nhận: %s" % (TRAIN_DIR, path)
        )
    run_id = resolved.name[: -len(".jsonl")]
    if run_id not in TRAIN_RUN_IDS:
        raise FirewallError("%s không nằm trong 8 run train đã đăng ký" % run_id)
    return run_id


def threshold_from_train(paths) -> dict:
    """Tính T=max(g) từ đủ và đúng tám run train, kèm owner truy vết."""
    paths = list(paths)
    run_ids = [_assert_train_path(path) for path in paths]
    if sorted(run_ids) != sorted(TRAIN_RUN_IDS):
        raise FirewallError("phải dùng đủ và đúng 8 run train, không chọn lọc")

    best = -1.0
    owner = None
    n_rows = 0
    n_none = 0
    per_run = {}
    for run_id, path in zip(run_ids, paths):
        run_max = None
        for snapshot in read_run(path):
            value = g(snapshot)
            n_rows += 1
            if value is None:
                n_none += 1
                continue
            run_max = value if run_max is None else max(run_max, value)
            if value > best:
                best = value
                owner = {"run_id": run_id, "tick": snapshot.get("tick")}
        per_run[run_id] = None if run_max is None else round(run_max, 6)

    if owner is None:
        raise ValueError("không có tick train nào judgeable")
    return {
        "quantity": QUANTITY_ID,
        "threshold_mbps": best,
        "owner": owner,
        "n_rows": n_rows,
        "n_unjudgeable": n_none,
        "per_run_max_mbps": per_run,
    }


class OperatingRangeGuard:
    """Vào sau một tick g>T; ra sau ``exit_ticks`` tick liên tiếp g<=T."""

    def __init__(self, threshold_mbps: float, exit_ticks: int = EXIT_TICKS):
        if not math.isfinite(threshold_mbps):
            raise ValueError("ngưỡng phải hữu hạn")
        if isinstance(exit_ticks, bool) or not isinstance(exit_ticks, int) or exit_ticks < 1:
            raise ValueError("exit_ticks phải là số nguyên dương")
        self.threshold = float(threshold_mbps)
        self.exit_ticks = exit_ticks
        self.active = False
        self._calm = 0

    def update(self, snapshot: dict) -> bool:
        value = g(snapshot)
        if value is None:
            return self.active
        if value > self.threshold:
            self.active = True
            self._calm = 0
        elif self.active:
            self._calm += 1
            if self._calm >= self.exit_ticks:
                self.active = False
                self._calm = 0
        return self.active


def load_sealed_threshold(prereg_doc: dict) -> float:
    """Đọc ngưỡng duy nhất từ nội dung prereg có hash hợp lệ."""
    content = prereg_doc["content"]
    digest = C.sha256_bytes(C.canonical_json(content).encode("utf-8"))
    if digest != prereg_doc["content_sha256"]:
        raise FirewallError("prereg đã bị sửa sau khi niêm phong")
    return float(content["guard"]["threshold_mbps"])


def feasibility(prereg_doc: dict, run_path) -> dict:
    """Chạy guard đã niêm phong trên một run; không nhận/trả ngưỡng mới."""
    guard = OperatingRangeGuard(load_sealed_threshold(prereg_doc))
    snapshots = read_run(run_path)
    n_judgeable = 0
    n_active = 0
    values = []
    for snapshot in snapshots:
        value = g(snapshot)
        active = guard.update(snapshot)
        if value is None:
            continue
        n_judgeable += 1
        n_active += int(active)
        values.append(round(value, 4))
    return {
        "run_id": Path(run_path).name[: -len(".jsonl")],
        "n_ticks": len(snapshots),
        "n_judgeable": n_judgeable,
        "n_guard_active": n_active,
        "frac_guard_active": n_active / n_judgeable if n_judgeable else None,
        "g_median_mbps": round(statistics.median(values), 4) if values else None,
        "g_values_mbps": values,
    }
