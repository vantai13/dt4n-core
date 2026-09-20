"""Hop dong A: TwinReader gop delta dung, va R3 duoc kiem TRUOC khi gop."""
import itertools

import pytest

from bridge.detector_contract import DETECTOR_THING_ID
from controller.twin_reader import SSE_HEADERS, TwinReader, deep_merge


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def fresh_props(seq, boot="b3f"):
    return {"bootId": boot, "seq": seq, "ttlTicks": 3, "tickIntervalMs": 1000}


def detector_delta(state=None, affected=None, seq=None, boot="b3f", cause=None):
    features = {}
    if state is not None or cause is not None:
        props = {}
        if state is not None:
            props["state"] = state
        if cause is not None:
            props["cause"] = cause
        features["decision"] = {"properties": props}
    if affected is not None:
        features["evidence"] = {"properties": {"affected": list(affected)}}
    if seq is not None:
        features["freshness"] = {"properties": fresh_props(seq, boot)}
    return {"thingId": DETECTOR_THING_ID, "features": features}


def test_deep_merge_giu_nhanh_khong_doi():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    assert deep_merge(base, {"a": {"y": 9}}) == {"a": {"x": 1, "y": 9}, "b": 3}


def test_delta_khong_lam_mat_affected():
    """Bay 1: SSE tra DELTA. Quen gop -> affected rong -> khong bao gio hanh dong."""
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="act", affected=["org.dt4n:host-h1"], seq=1))
    reader.apply(detector_delta(state="act", seq=2))       # tick sau: affected khong doi
    assert reader.detector_view_fields()["affected"] == ("org.dt4n:host-h1",)


def test_r3_seq_lui_thi_bo_ca_ban_tin():
    """Bay 2: resync sau dut ket noi co the tra ban CU."""
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="normal", affected=[], seq=10))
    reader.apply(detector_delta(state="act", affected=["org.dt4n:host-h1"], seq=9))
    fields = reader.detector_view_fields()
    assert fields["state"] == "normal"          # ban tin lui bi BO HOAN TOAN
    assert fields["affected"] == ()
    assert reader.dropped == 1


def test_r3_seq_trung_cung_bi_bo():
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="normal", seq=5))
    reader.apply(detector_delta(state="act", seq=5))
    assert reader.detector_view_fields()["state"] == "normal"
    assert reader.dropped == 1


def test_r3_kiem_truoc_khi_gop():
    """Neu kiem SAU khi gop, cache da nhiem ban tin lui."""
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="normal", affected=[], seq=10))
    before = dict(reader.things[DETECTOR_THING_ID])
    reader.apply(detector_delta(state="act", affected=["org.dt4n:host-h2"], seq=3))
    assert reader.things[DETECTOR_THING_ID] == before


def test_boot_id_retired_thi_bo():
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="normal", seq=1, boot="old"))
    reader.apply(detector_delta(state="normal", seq=1, boot="new"))   # boot moi
    reader.apply(detector_delta(state="act", seq=99, boot="old"))     # boot da retired
    assert reader.detector_view_fields()["state"] == "normal"
    assert reader.dropped == 1


def test_freshness_mac_dinh_la_stale():
    """Arm roi confirm: truoc khi quan sat mot thay doi hop le -> STALE."""
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="act", affected=["org.dt4n:host-h1"], seq=1))
    assert reader.detector_view_fields()["fresh"] is False


def test_ttl_het_thi_stale():
    clock = FakeClock()
    reader = TwinReader(clock=clock)
    reader.apply(detector_delta(state="normal", seq=1, boot="a"))
    reader.apply(detector_delta(state="normal", seq=2, boot="b"))   # confirm
    assert reader.detector_view_fields()["fresh"] is True
    clock.t += 3.5                                                   # ttl = 3 tick
    assert reader.detector_view_fields()["fresh"] is False


def test_observed_bw_la_kenh_xac_nhan():
    reader = TwinReader(clock=FakeClock())
    reader.apply({"thingId": "org.dt4n:link-h1-s1",
                  "features": {"capacity": {"properties": {"bwMbps": 20.0}}}})
    assert reader.observed_bw() == {"h1-s1": 20.0}
    reader.apply({"thingId": "org.dt4n:link-h1-s1",
                  "features": {"capacity": {"properties": {"bwMbps": 7.0}}}})
    assert reader.observed_bw() == {"h1-s1": 7.0}


def test_roles_doc_tu_twin():
    reader = TwinReader(clock=FakeClock())
    reader.apply({"thingId": "org.dt4n:host-h1",
                  "attributes": {"type": "host", "role": "client"}})
    reader.apply({"thingId": "org.dt4n:host-srv1",
                  "attributes": {"type": "host", "role": "server"}})
    assert reader.roles() == {"h1": "client", "srv1": "server"}


def test_mot_stream_hai_loai_du_lieu():
    """Bay 3: detector VA link den tu CUNG mot stream; khong mo hai ket noi."""
    reader = TwinReader(clock=FakeClock())
    reader.apply(detector_delta(state="act", affected=["org.dt4n:host-h1"], seq=1))
    reader.apply({"thingId": "org.dt4n:link-h1-s1",
                  "features": {"capacity": {"properties": {"bwMbps": 7.0}}}})
    assert reader.detector_view_fields()["state"] == "act"
    assert reader.observed_bw() == {"h1-s1": 7.0}


def test_bo_qua_dong_khong_phai_data():
    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_lines(self, decode_unicode=False):
            yield ""
            yield ": heartbeat"
            yield "event: message"
            yield 'data: {"thingId": "org.dt4n:host-h1", "attributes": {"role": "client"}}'
            yield "data:"
            yield "data: {khong-phai-json"

    class FakeSession:
        def get(self, url, **kwargs):
            assert "fields=thingId,attributes,features" in url
            assert kwargs["headers"] is SSE_HEADERS
            return FakeResponse()

    class Stop:
        def is_set(self):
            return False

    reader = TwinReader(clock=FakeClock())
    reader.stream_once(FakeSession(), Stop())
    assert reader.roles() == {"h1": "client"}
    assert reader.events == 1


def test_gzip_bi_tat():
    """gzip giu event nho trong buffer -> controller nhan tre hoac khong nhan."""
    assert SSE_HEADERS["Accept-Encoding"] == "identity"
