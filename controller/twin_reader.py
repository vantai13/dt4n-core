#!/usr/bin/env python3
"""Hop dong A - controller DOC detector QUA TWIN, khong doc tat.

Controller chay cung tien trinh voi vong chay cua detector (M9) nen no *co the*
doc thang bien trang thai trong bo nho cua vong do. KHONG DUOC. Doc tat = bo qua twin = hai duong su that,
dung thu ma luan diem cot loi cua do an chong lai: DittoTransport PATCH mot
lan, khong retry - mot PATCH rot la dashboard thay mot dang, controller thay
mot dang khac.

Chi phi cua viec lam dung: write_2xx p95 11.173 ms + fanout_sse p95 11.030 ms
= 22.2 ms tren ngan sach C3 10 000 ms (results/report/phase7_e2e_latency.json),
tuc 0.22%.
"""
from __future__ import annotations

import json
import threading
import time

import requests

from bridge.detector_contract import DETECTOR_THING_ID
from bridge.ditto_common import DITTO_AUTH, DITTO_BASE_URL, NAMESPACE
from bridge.freshness import MonotonicFreshness

SSE_HEADERS = {
    "Accept": "text/event-stream",
    "Accept-Encoding": "identity",   # tat gzip: gzip giu event nho trong buffer
    "Cache-Control": "no-cache",
}
SSE_PATH = (
    "/things?namespaces=%s&fields=thingId,attributes,features" % NAMESPACE
)
RECONNECT_BACKOFF_S = 1.0
PRIME_PATH = SSE_PATH       # cung bo loc, nhung la GET mot lan


def deep_merge(base: dict, delta: dict) -> dict:
    """SSE tra DELTA, khong tra Thing day du. Quen gop = affected rong."""
    out = dict(base)
    for key, value in delta.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class TwinReader:
    """Consumer SSE + cache + freshness. Ngang hang voi dashboard."""

    def __init__(self, base_url=DITTO_BASE_URL, auth=DITTO_AUTH,
                 clock=time.monotonic):
        self.base_url = base_url
        self.auth = auth
        self.things: dict[str, dict] = {}
        self.freshness = MonotonicFreshness(clock=clock)
        self.dropped = 0            # so ban tin bi bo vi R3
        self.reconnects = 0
        self.events = 0
        self.primed = 0
        self.last_event_mono = None
        self._lock = threading.Lock()
        self._clock = clock

    # ---------------------------------------------------------- moi cache

    def prime(self, session=None) -> int:
        """GET mot lan toan bo Things de MOI cache truoc khi nghe SSE.

        BAT BUOC, va day la bai hoc dat gia cua 8.4: SSE chi gui TRUONG THAY
        DOI. `attributes.role` cua host KHONG BAO GIO doi, nen no KHONG BAO GIO
        xuat hien trong stream. Chi nghe SSE => roles() tra toan None =>
        localize() thay 0 ung vien client => controller KHONG BAO GIO hanh dong,
        du detector bao `act` va `affected` co host-h1.

        Mau chuan cua moi consumer stream: SNAPSHOT roi moi STREAM.
        """
        session = session or requests.Session()
        try:
            response = session.get(self.base_url + PRIME_PATH, auth=self.auth,
                                   timeout=(5, 10))
        except requests.RequestException:
            return 0
        if response.status_code != 200:
            return 0
        try:
            items = response.json()
        except ValueError:
            return 0
        if isinstance(items, dict):
            items = items.get("items") or []
        primed = 0
        for item in items:
            if not isinstance(item, dict) or not item.get("thingId"):
                continue
            if item["thingId"] == DETECTOR_THING_ID:
                # Thing detector duoc PATCH TOAN BO moi tick (vong chay cua detector
                # dung build_document roi transport) nen KHONG co truong tinh nao can
                # prime. Prime no se ghi vao cache MA KHONG qua MonotonicFreshness
                # -> cache va bo theo doi lech nhau -> cache co the di LUI khi mot
                # event seq nho hon (nhung lon hon seq cua tracker) toi. Chinh la
                # thu R3 sinh ra de chan.
                continue
            self.apply(item, check_freshness=False)
            primed += 1
        self.primed = primed
        return primed

    # ---------------------------------------------------------- vong SSE

    def run_forever(self, stop_event, session=None):
        session = session or requests.Session()
        self.prime(session)
        while not stop_event.is_set():
            try:
                self.stream_once(session, stop_event)
            except requests.RequestException:
                pass
            if not stop_event.is_set():
                self.reconnects += 1
                stop_event.wait(RECONNECT_BACKOFF_S)
                # Moi lai sau khi dut: ban tin bo lo luc dut co the la ban duy
                # nhat mang mot truong tinh.
                self.prime(session)

    def stream_once(self, session, stop_event):
        url = self.base_url + SSE_PATH
        with session.get(url, headers=SSE_HEADERS, auth=self.auth,
                         stream=True, timeout=(5, 30)) as response:
            if response.status_code != 200:
                return
            for raw in response.iter_lines(decode_unicode=True):
                if stop_event.is_set():
                    return
                if not raw or not raw.startswith("data:"):
                    continue          # heartbeat/comment cua Ditto
                payload = raw[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    self.apply(json.loads(payload))
                except ValueError:
                    continue

    # ---------------------------------------------------------- gop + R3

    def apply(self, delta: dict, check_freshness: bool = True):
        """Gop mot delta vao cache. R3 duoc kiem TRUOC khi gop.

        `check_freshness=False` chi dung cho prime(): anh chup REST khong phai
        mot ban tin trong dong nen khong duoc tinh vao monotonic-read.
        """
        thing_id = delta.get("thingId")
        if not thing_id:
            return
        with self._lock:
            if thing_id == DETECTOR_THING_ID and check_freshness:
                # R3: seq lui / trung / bootId da retired -> BO CA BAN TIN.
                # Kiem TRUOC khi gop; neu kiem sau, cache da nhiem ban tin lui
                # va MonotonicFreshness tro thanh vo dung.
                fresh = (
                    ((delta.get("features") or {}).get("freshness") or {})
                    .get("properties") or {}
                )
                if fresh and not self.freshness.observe(fresh):
                    self.dropped += 1
                    return
            self.things[thing_id] = deep_merge(
                self.things.get(thing_id, {}), delta
            )
            self.events += 1
            self.last_event_mono = self._clock()

    # ---------------------------------------------------------- doc ra

    def detector_view_fields(self) -> dict:
        """Tra nguyen lieu THO cho DetectorView. KHONG tu suy ra gi (N13)."""
        with self._lock:
            features = (
                (self.things.get(DETECTOR_THING_ID) or {}).get("features") or {}
            )
        decision = (features.get("decision") or {}).get("properties") or {}
        evidence = (features.get("evidence") or {}).get("properties") or {}
        fresh = (features.get("freshness") or {}).get("properties") or {}
        provenance = (features.get("provenance") or {}).get("properties") or {}
        return {
            "state": decision.get("state", "unknown"),
            "cause": decision.get("cause", "never_started"),
            # R2: evidence.affected cua chinh tick do, KHONG phai decision.affected
            "affected": tuple(evidence.get("affected") or ()),
            "fresh": (not self.freshness.is_stale(fresh)) if fresh else False,
            "boot_id": fresh.get("bootId", ""),
            "seq": int(fresh.get("seq", -1)),
            "release_sha256": provenance.get("releaseSha256", ""),   # R4
        }

    def observed_bw(self) -> dict:
        """Kenh XAC NHAN HIEU LUC (hop dong C): {link_key: bwMbps}.

        `capacity` KHONG nam trong 71 cot dac trung cua envelope-1.0.0 nen doc
        no khong vi pham N13 (da kiem o Lesson 8.1). Chuoi nhan qua:
        command_agent.py:258 ghi ln.dt4n_bw -> collector.py:403 doc ->
        collector.py:639 ghi features['capacity'] -> PATCH -> SSE -> day.
        """
        out = {}
        with self._lock:
            items = list(self.things.items())
        for thing_id, body in items:
            if ":link-" not in thing_id:
                continue
            capacity = (
                ((body.get("features") or {}).get("capacity") or {})
                .get("properties") or {}
            )
            if "bwMbps" in capacity:
                out[thing_id.split(":link-", 1)[1]] = float(capacity["bwMbps"])
        return out

    def roles(self) -> dict:
        """{host: role} doc tu twin; khong hardcode ten host."""
        out = {}
        with self._lock:
            items = list(self.things.items())
        for thing_id, body in items:
            if ":host-" not in thing_id:
                continue
            out[thing_id.split(":host-", 1)[1]] = (
                (body.get("attributes") or {}).get("role")
            )
        return out
