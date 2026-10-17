#!/usr/bin/env python3
"""Ditto giả điều khiển được cho E2E dashboard Phase 7.4."""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dashboard/dist"


def dashboard_namespace() -> str:
    """Dùng đúng namespace đã được Vite nạp khi build dashboard."""
    if os.environ.get("VITE_DITTO_NAMESPACE"):
        return os.environ["VITE_DITTO_NAMESPACE"]
    env_file = ROOT / "dashboard/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("VITE_DITTO_NAMESPACE="):
                return line.split("=", 1)[1].strip()
    return "org.dt4n"


NS = dashboard_namespace()


def topology_things() -> list[dict]:
    spec = json.loads((ROOT / "ditto/topology_spec.json").read_text())
    ok = {
        "status": {"properties": {"state": "up"}},
        "health": {"properties": {"state": "ok"}},
    }
    things = [
        {
            "thingId": f"{NS}:host-{host['name']}",
            "attributes": {"type": "host", "role": host["role"]},
            "features": ok,
        }
        for host in spec["hosts"]
    ]
    things += [
        {
            "thingId": f"{NS}:switch-{switch if isinstance(switch, str) else switch['name']}",
            "attributes": {"type": "switch"},
            "features": ok,
        }
        for switch in spec["switches"]
    ]
    for link in spec["links"]:
        endpoint_a, endpoint_b = (
            (link[0], link[1])
            if isinstance(link, list)
            else (link["a"], link["b"])
        )
        things.append({
            "thingId": f"{NS}:link-{endpoint_a}-{endpoint_b}",
            "attributes": {
                "type": "link",
                "endpointA": endpoint_a,
                "endpointB": endpoint_b,
            },
            "features": ok,
        })
    return things


def detector_doc(
    boot: str,
    seq: int,
    state: str = "normal",
    affected=(),
    actRule=False,
) -> dict:
    return {
        "thingId": f"{NS}:detector",
        "attributes": {"type": "detector"},
        "features": {
            "decision": {"properties": {
                "state": state, "cause": "", "reason": "", "detectedAt": "",
            }},
            "evidence": {"properties": {
                "envelopeValid": True,
                "conservationValid": True,
                "envelope": actRule,
                "conservation": False,
                "actRule": actRule,
                "conservationSwitch": "",
                "affected": list(affected),
                "unattributed": 0,
            }},
            "freshness": {"properties": {
                "bootId": boot,
                "seq": seq,
                "heartbeatAt": "",
                "ttlTicks": 3,
                "tickIntervalMs": 1000,
                "dropped": 0,
            }},
        },
    }


def controlloop_doc(
    boot: str,
    seq: int,
    mode: str = "IDLE",
    target: str = "",
    limit_mbps: float = 0.0,
    hold_remaining_s: float = 0.0,
    probe_remaining_s: float = 0.0,
    reason: str = "",
) -> dict:
    """Thing controlloop (hop dong D, Phase 8.3) cho E2E cua 8.5."""
    return {
        "thingId": f"{NS}:controlloop",
        "attributes": {"type": "controller", "role": "closed-loop-controller"},
        "features": {
            "decision": {"properties": {
                "mode": mode, "target": target, "limitMbps": limit_mbps,
                "reason": reason, "decidedAt": "",
            }},
            "schedule": {"properties": {
                "holdRemainingS": hold_remaining_s,
                "probeRemainingS": probe_remaining_s,
                "attempt": 0, "episode": 1,
            }},
            "freshness": {"properties": {
                "bootId": boot, "seq": seq, "heartbeatAt": "",
                "ttlTicks": 3, "tickIntervalMs": 1000, "dropped": 0,
            }},
        },
    }


class FakeDitto:
    def __init__(self, port: int = 0):
        self.things = topology_things()
        self.search_detector = detector_doc("", -1, "unknown")
        # Phase 8.5: nguon song THU HAI, nhip tim DOC LAP voi detector.
        self.search_control = controlloop_doc("", -1, "HOLD", reason="never_started")
        self.control_boot = "ctlboot1"
        self.control_seq = 0
        self.control_mode = "IDLE"
        self.control_reason = ""
        self.control_target = ""
        self.control_limit = 0.0
        self.control_hold_s = 0.0
        self.control_probe_s = 0.0
        self.control_beating = threading.Event()
        self.boot = "boot1"
        self.seq = 0
        self.state = "normal"
        self.affected = ()
        self.act = False
        self.beating = threading.Event()
        self.clients: list[queue.Queue] = []
        self.ui_log: list[dict] = []
        self.last_beat_mono = None
        self.push_log: list[tuple] = []
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    fake.ui_log.append(json.loads(body))
                except ValueError:
                    pass
                self.send_response(204)
                self.end_headers()

            def do_GET(self):
                if self.path.startswith("/ditto/api/2/search/things"):
                    return self._json({"items": fake.things
                                        + [fake.search_detector, fake.search_control]})
                if self.path.startswith("/ditto-sse/"):
                    return self._sse()
                relative = self.path.split("?")[0].lstrip("/") or "index.html"
                file_path = DIST / relative
                if not file_path.is_file():
                    file_path = DIST / "index.html"
                data = file_path.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    mimetypes.guess_type(str(file_path))[0] or "text/html",
                )
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _json(self, value):
                data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _sse(self):
                client_queue: queue.Queue = queue.Queue()
                with fake._lock:
                    fake.clients.append(client_queue)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    while True:
                        item = client_queue.get()
                        if item is None:
                            return
                        self.wfile.write(
                            b"data: " + json.dumps(item).encode() + b"\n\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
                finally:
                    with fake._lock:
                        if client_queue in fake.clients:
                            fake.clients.remove(client_queue)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._heart, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def _heart(self):
        while True:
            if self.beating.is_set():
                document = detector_doc(
                    self.boot, self.seq, self.state, self.affected, self.act
                )
                self.push_log.append((self.seq, self.state, time.monotonic()))
                self.push(document)
                self.last_beat_mono = time.monotonic()
                self.seq += 1
            if self.control_beating.is_set():
                # Nhip tim RIENG: dung rieng no de kiem masking (detector song
                # che controller chet) ma khong dung toi detector.
                self.push(controlloop_doc(
                    self.control_boot, self.control_seq, self.control_mode,
                    self.control_target, self.control_limit,
                    self.control_hold_s, self.control_probe_s,
                    getattr(self, "control_reason", ""),
                ))
                self.control_seq += 1
            time.sleep(1.0)

    def push(self, document):
        with self._lock:
            for client_queue in list(self.clients):
                client_queue.put(document)

    def drop_sse(self):
        with self._lock:
            for client_queue in list(self.clients):
                client_queue.put(None)

    def set_control(self, mode="IDLE", target="", limit_mbps=0.0,
                    hold_remaining_s=0.0, probe_remaining_s=0.0, reason=""):
        self.control_mode = mode
        self.control_target = target
        self.control_limit = limit_mbps
        self.control_hold_s = hold_remaining_s
        self.control_probe_s = probe_remaining_s
        # 8.8: `reason` phan biet IDLE "ranh" voi IDLE "bi troi tay" (N15/N16).
        self.control_reason = reason

    def push_control(self, **kwargs):
        self.set_control(**kwargs)
        document = controlloop_doc(
            self.control_boot, self.control_seq, self.control_mode,
            self.control_target, self.control_limit,
            self.control_hold_s, self.control_probe_s,
            getattr(self, "control_reason", ""),
        )
        self.control_seq += 1
        self.push(document)
        return document

    def stop_control_heartbeat(self):
        """CHI controller chet; detector van dap binh thuong."""
        self.control_beating.clear()

    def restart_detector(self, boot: str):
        self.boot, self.seq, self.state = boot, 0, "warming_up"

    def close(self):
        self.drop_sse()
        self.server.shutdown()
