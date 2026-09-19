"""Asynchronous detector runner — Phase 7.3.

The collector thread never calls the network. It validates and scores every
snapshot, writes the complete local audit, then publishes into a one-slot
conflating mailbox. A separate writer thread performs one PATCH without retry.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import requests

from bridge import detector_contract as D
from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL
from ml.intervention_log import InMemoryInterventionLog
from ml.operating_range import OperatingRangeGuard, load_sealed_threshold


log = logging.getLogger("detector_runner")

WRITE_TIMEOUT_S = 2.0
MERGE_PATCH = {"Content-Type": "application/merge-patch+json"}
LATENCY_SAMPLES = 2048
TIMELINE_SAMPLES = 4096
CRASH_LOOP = (5, 60.0)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class StopRunner(Exception):
    """Dừng chủ động Collector.run ở tick kế tiếp."""


class FatalContract(Exception):
    """Vi phạm topology contract: fail-closed và ngừng heartbeat."""


class CrashLoop(FatalContract):
    """Reset liên tục do bug tất định; dừng thay vì tự chữa vô hạn."""


class Mailbox:
    """Mailbox một ô; put không chặn và bản mới đè bản cũ có đếm."""

    def __init__(self):
        self._cond = threading.Condition()
        self._item = None
        self.overwritten = 0

    def put(self, item) -> None:
        with self._cond:
            if self._item is not None:
                self.overwritten += 1
            self._item = item
            self._cond.notify()

    def take(self, timeout: float):
        with self._cond:
            if self._item is None:
                self._cond.wait(timeout)
            item, self._item = self._item, None
            return item


class DittoTransport:
    """PATCH một lần, không retry; document tick sau là state mới hơn."""

    def __init__(self, timeout_s: float = WRITE_TIMEOUT_S):
        self.timeout_s = timeout_s
        self._session = None

    def __call__(self, thing_id: str, body: dict) -> tuple[bool, str]:
        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.patch(
                "%s/things/%s" % (DITTO_BASE_URL, thing_id),
                json=body,
                headers=MERGE_PATCH,
                auth=DITTO_AUTH,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            return False, type(exc).__name__
        return response.status_code in (200, 204), str(response.status_code)


class RotatingJsonl:
    """Audit JSONL cục bộ được xoay vòng theo dung lượng."""

    def __init__(self, path: str, max_bytes: int = 50 * 2**20, backups: int = 3):
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._fh.flush()
        if self._fh.tell() >= self.max_bytes:
            self._rotate()

    def _rotate(self) -> None:
        self._fh.close()
        for index in range(self.backups - 1, 0, -1):
            source = "%s.%d" % (self.path, index)
            if os.path.exists(source):
                os.replace(source, "%s.%d" % (self.path, index + 1))
        os.replace(self.path, self.path + ".1")
        self._fh = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        self._fh.close()


class DetectorRunner:
    def __init__(
        self,
        release,
        prereg_doc,
        transport,
        *,
        intervention_log=None,
        audit=None,
        clock=time.monotonic,
    ):
        self.release = release
        self.threshold = load_sealed_threshold(prereg_doc)
        self.transport = transport
        self.intervention_log = intervention_log or InMemoryInterventionLog()
        self.audit = audit
        self.clock = clock
        self.entities = D.expected_entities(release.model)
        self.expected_version = release.content["collector_version"]
        self.mailbox = Mailbox()
        self._lock = threading.Lock()
        self.failed = 0
        self.sent = 0
        self.restarts = 0
        self.exceptions = 0
        self.last_write_status = ""
        self.on_tick_ms = deque(maxlen=LATENCY_SAMPLES)
        self._exc_times = deque(maxlen=CRASH_LOOP[0] + 1)
        self.write_ms = deque(maxlen=LATENCY_SAMPLES)
        self.sent_seq = deque(maxlen=LATENCY_SAMPLES)
        self.timeline = deque(maxlen=TIMELINE_SAMPLES)
        self.writes = deque(maxlen=TIMELINE_SAMPLES)
        self.stop_event = threading.Event()
        self._writer_thread = None
        self._new_incarnation("start")

    def _new_incarnation(self, why: str) -> None:
        self.scorer, self.fsm = self.release.build(self.intervention_log)
        self.guard = OperatingRangeGuard(self.threshold)
        self.boot_id = D.new_boot_id()
        self.seq = 0
        self.published = None
        self.detected_at = ""
        if why != "start":
            self.restarts += 1
        log.warning("incarnation mới %s (%s)", self.boot_id, why)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self.mailbox.overwritten + self.failed

    def on_tick(self, n, snapshot, t_rel) -> None:
        """Collector callback: bounded local work only, never network I/O."""
        if self.stop_event.is_set():
            raise StopRunner()
        t_in = self.clock()
        try:
            problems = D.check_live_snapshot(
                snapshot, self.entities, self.expected_version
            )
            if any(problem.startswith("A2") for problem in problems):
                raise FatalContract("; ".join(problems))
            t_s0 = self.clock()
            reading = self.scorer.observe(snapshot)
            transition = self.fsm.step(reading)
            t_s1 = self.clock()
            guard_active = self.guard.update(snapshot)
            t1 = self.clock()
            now = utc_iso()
            document = D.build_document(
                self.release,
                transition,
                reading,
                boot_id=self.boot_id,
                seq=self.seq,
                heartbeat_at=now,
                detected_at=self.detected_at or now,
                dropped=self.dropped,
                guard_active=guard_active,
            )
            decision = document["features"]["decision"]["properties"]
            if decision["state"] != self.published:
                self.published = decision["state"]
                self.detected_at = now
                decision["detectedAt"] = now
            t2 = self.clock()
            self.mailbox.put((document, self.seq, t2))
            self.timeline.append(
                {
                    "bootId": self.boot_id,
                    "seq": self.seq,
                    "t_in": t_in,
                    "t1": t1,
                    "t2": t2,
                    "t_source": snapshot.get("t_source"),
                    "fsm": transition.state,
                    "published": decision["state"],
                    "envelope": bool(reading.envelope_suspect),
                    "conservation": bool(reading.cons_alarm),
                    "act_rule": bool(reading.act),
                    "cause": decision["cause"],
                    "score_ms": (t_s1 - t_s0) * 1000.0,
                    "cycle_scan_ms": snapshot.get("cycle_scan_ms"),
                }
            )
            if self.audit is not None:
                self.audit.write(
                    {
                        "bootId": self.boot_id,
                        "seq": self.seq,
                        "tick": n,
                        "t_source": snapshot.get("t_source"),
                        "t_rel": t_rel,
                        "fsm_state": transition.state,
                        "published": decision["state"],
                        "cause": decision["cause"],
                        "guard": guard_active,
                        "reading": reading.status,
                        "problems": problems,
                        "t1_minus_in_ms": round((t1 - t_in) * 1000, 3),
                    }
                )
            self.seq += 1
        except (StopRunner, FatalContract):
            raise
        except Exception:
            self.exceptions += 1
            log.exception("lỗi trong on_tick -> incarnation mới")
            self._exc_times.append(self.clock())
            if (
                len(self._exc_times) > CRASH_LOOP[0]
                and self._exc_times[-1] - self._exc_times[0] < CRASH_LOOP[1]
            ):
                raise CrashLoop(
                    "%d exception trong %.0f s"
                    % (len(self._exc_times), CRASH_LOOP[1])
                )
            self._new_incarnation("exception")
        finally:
            self.on_tick_ms.append((self.clock() - t_in) * 1000)

    def _writer(self) -> None:
        while not self.stop_event.is_set():
            item = self.mailbox.take(timeout=0.2)
            if item is None:
                continue
            document, seq, t2 = item
            ok, status = self.transport(D.DETECTOR_THING_ID, document)
            t3 = self.clock()
            self.writes.append(
                {
                    "bootId": document["features"]["freshness"]["properties"]["bootId"],
                    "seq": seq,
                    "t2": t2,
                    "t3": t3,
                    "ok": ok,
                    "published": document["features"]["decision"]["properties"]["state"],
                }
            )
            with self._lock:
                if ok:
                    self.sent += 1
                    self.write_ms.append((t3 - t2) * 1000)
                    self.sent_seq.append(seq)
                else:
                    self.failed += 1
                if status != self.last_write_status:
                    log.warning("ghi detector Thing: %s", status)
                self.last_write_status = status

    def start_writer(self) -> None:
        self._writer_thread = threading.Thread(
            target=self._writer,
            name="detector-writer",
            daemon=True,
        )
        self._writer_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        if self._writer_thread is not None:
            self._writer_thread.join(timeout)

    def run_forever(self, collector) -> str:
        """Supervise Collector.run; rebuild stream state after collector crash."""
        self.start_writer()
        try:
            while not self.stop_event.is_set():
                try:
                    collector.run(duration=float("inf"), on_tick=self.on_tick)
                except StopRunner:
                    return "stopped"
                except FatalContract as exc:
                    log.error("FAIL-CLOSED, ngừng heartbeat: %s", exc)
                    return "fatal:" + type(exc).__name__
                except Exception:
                    log.exception("collector chết -> incarnation mới")
                    self._new_incarnation("collector_crash")
                    self.stop_event.wait(1.0)
            return "stopped"
        finally:
            self.stop()

    def stats(self) -> dict:
        def p95(values):
            ordered = sorted(values)
            return (
                round(ordered[int(0.95 * (len(ordered) - 1))], 3)
                if ordered
                else None
            )

        with self._lock:
            return {
                "seq": self.seq,
                "sent": self.sent,
                "failed": self.failed,
                "overwritten": self.mailbox.overwritten,
                "restarts": self.restarts,
                "exceptions": self.exceptions,
                "on_tick_p95_ms": p95(self.on_tick_ms),
                "write_p95_ms": p95(self.write_ms),
            }
