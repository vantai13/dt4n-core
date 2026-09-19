"""Ba hợp đồng live của detector — Phase 7.2.

A. Snapshot live phải có gì: ``live_run_meta`` và ``check_live_snapshot``.
B. Thing ``org.dt4n:detector`` ghi gì: ``build_document``.
C. Consumer xác nhận dữ liệu còn tươi thế nào: ``FreshnessTracker``.

Module không tự tính state. Nó sao chép quyết định FSM và bằng chứng Reading,
rồi đối chiếu với ``release.payload`` đã đóng băng như một oracle.
"""
from __future__ import annotations

import math
import time
import uuid

from bridge.collector_version import COLLECTOR_VERSION
from bridge.ditto_common import NAMESPACE
from ml.blast_radius import entity_of


DETECTOR_THING_ID = NAMESPACE + ":detector"
TTL_TICKS = 3
TICK_INTERVAL_MS = 1000
GUARD_OVERRIDABLE = ("normal", "suspect", "act")
GUARD_CAUSE = "out_of_operating_range"


def new_boot_id() -> str:
    """Tạo incarnation id mới cho mỗi lần process khởi động."""
    return uuid.uuid4().hex[:12]


def live_run_meta(boot_id: str, git_hash: str | None = None) -> dict:
    """Tạo run_meta live; version đến từ producer, không đến từ release."""
    return {
        "run_id": "live-" + boot_id,
        "mode": "live",
        "collector_version": COLLECTOR_VERSION,
        "period_sec": TICK_INTERVAL_MS / 1000.0,
        "git_hash": git_hash,
    }


def expected_entities(model) -> set[str]:
    """Suy tập entity model biết trực tiếp từ tên cột artifact."""
    return {entity_of(column) for column in model.columns} - {None}


def check_live_snapshot(
    snapshot: dict, entities: set[str], expected_version: str
) -> list[str]:
    """Trả vi phạm hợp đồng A; danh sách rỗng nghĩa là đạt."""
    problems = []
    t_source = snapshot.get("t_source")
    if (
        isinstance(t_source, bool)
        or not isinstance(t_source, (int, float))
        or not math.isfinite(t_source)
    ):
        problems.append("A1 thiếu t_source hữu hạn")

    things = snapshot.get("things")
    if not isinstance(things, dict):
        return problems + ["A2 thiếu things"]
    have = set(things)
    if entities - have:
        problems.append("A2 thiếu entity: %s" % sorted(entities - have))
    if have - entities:
        problems.append("A2 topology lạ, entity thừa: %s" % sorted(have - entities))

    run = snapshot.get("run")
    if not isinstance(run, dict):
        problems.append("A3 thiếu snapshot['run'] (producer chưa cấp run_meta)")
    elif run.get("collector_version") != expected_version:
        problems.append(
            "A3 collector_version %r != %r"
            % (run.get("collector_version"), expected_version)
        )
    if "tick" not in snapshot:
        problems.append("A4 thiếu tick")
    return problems


def _thing_id(entity: str) -> str:
    return "%s:%s" % (NAMESPACE, entity)


def build_document(
    release,
    transition,
    reading,
    *,
    boot_id: str,
    seq: int,
    heartbeat_at: str,
    detected_at: str,
    dropped: int,
    guard_active: bool,
) -> dict:
    """Dựng merge-patch body cho detector Thing và không phát sinh ``None``."""
    published = transition.state
    cause = transition.cause or ""
    reason = transition.reason or ""
    if guard_active and published in GUARD_OVERRIDABLE:
        published = "unknown"
        cause = GUARD_CAUSE
        reason = "ngoài vùng vận hành đã đăng ký (Phase 7.1); " + reason

    violating = tuple(getattr(reading, "violating", ()) or ())
    affected = sorted(
        {_thing_id(entity) for entity in map(entity_of, violating) if entity}
    )
    unattributed = sum(1 for column in violating if entity_of(column) is None)
    conservation_active = release.content["conservation_mode"] == "active"
    conservation = bool(conservation_active and reading.cons_alarm)
    evidence = {
        "envelopeValid": bool(reading.judgeable),
        "conservationValid": bool(reading.cons_judgeable),
        "envelope": bool(reading.envelope_suspect),
        "conservation": conservation,
        "actRule": bool(reading.act),
        "conservationSwitch": (reading.cons_switch or "") if conservation else "",
        "affected": affected,
        "unattributed": unattributed,
    }
    provenance = {
        "modelVersion": release.model.version,
        "artifactSha256": release.model.content_sha256,
        "releaseVersion": release.version,
        "releaseSha256": release.sha256,
        "conservationSha256": release.conservation.amendment_sha256,
        "collectorVersion": COLLECTOR_VERSION,
    }

    if transition.state != "normal":
        oracle = release.payload(transition, reading, detected_at=detected_at)
        for key in (
            "modelVersion",
            "artifactSha256",
            "releaseVersion",
            "releaseSha256",
            "conservationSha256",
        ):
            if oracle[key] != provenance[key]:
                raise ValueError("lệch oracle ở %s" % key)
        local_evidence = {
            "envelope": evidence["envelope"],
            "conservation": evidence["conservation"],
            "act_rule": evidence["actRule"],
        }
        if oracle["evidence"] != local_evidence:
            raise ValueError(
                "evidence lệch oracle: %r != %r"
                % (local_evidence, oracle["evidence"])
            )

    return {
        "features": {
            "decision": {
                "properties": {
                    "state": published,
                    "cause": cause,
                    "reason": reason,
                    "detectedAt": detected_at,
                }
            },
            "evidence": {"properties": evidence},
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
            "provenance": {"properties": provenance},
        }
    }


def initial_detector_body(policy_id: str) -> dict:
    """Trạng thái bootstrap fail-safe, không bao giờ khởi tạo là normal."""
    return {
        "policyId": policy_id,
        "attributes": {"type": "detector", "role": "anomaly-detector"},
        "features": {
            "decision": {
                "properties": {
                    "state": "unknown",
                    "cause": "never_started",
                    "reason": "detector chưa từng chạy",
                    "detectedAt": "",
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
        },
    }


class FreshnessTracker:
    """Consumer-side TTL bằng clock cục bộ với quy tắc arm rồi confirm."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._last_key = None
        self._confirmed_at = None

    def observe(self, freshness: dict) -> None:
        key = (freshness.get("bootId"), freshness.get("seq"))
        if self._last_key is not None and key != self._last_key:
            self._confirmed_at = self._clock()
        self._last_key = key

    def is_stale(self, freshness: dict) -> bool:
        if self._confirmed_at is None:
            return True
        budget_seconds = (
            freshness.get("ttlTicks", TTL_TICKS)
            * freshness.get("tickIntervalMs", TICK_INTERVAL_MS)
            / 1000.0
        )
        return (self._clock() - self._confirmed_at) > budget_seconds
