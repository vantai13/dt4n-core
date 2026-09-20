"""Vong kin 8.4: reconcile, revert-first, mot-action-mot-append, tat em."""
import threading
import time
from pathlib import Path

import pytest

from controller.locked_log import LockedInterventionLog
from controller.policy import ControllerState, DetectorView, PolicyParams, decide
from controller.runner import (
    CONFIRM_GRACE_S,
    CRASH_LOOP,
    EPS_MBPS,
    LEASE_TTL_S,
    RENEW_PERIOD_S,
    TICK_S,
    ControlRunner,
)
from ml.blast_radius import Routing
from ml.intervention_log import MAX_OPEN_S, InMemoryInterventionLog

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"h1": "client", "h2": "client", "h3": "client",
         "srv1": "server", "srv2": "server"}
H1 = "org.dt4n:host-h1"


class FakeTwin:
    """Twin gia: khong SSE, khong Ditto - chi mot cache doc duoc."""

    def __init__(self, bw=None, state="normal", cause="", affected=(), fresh=True):
        self.bw = dict(bw or {})
        self.state, self.cause, self.affected, self.fresh = state, cause, affected, fresh
        self.dropped = 0

    def detector_view_fields(self):
        return {"state": self.state, "cause": self.cause,
                "affected": tuple(self.affected), "fresh": self.fresh,
                "boot_id": "b3f", "seq": 1, "release_sha256": "deadbeef"}

    def observed_bw(self):
        return dict(self.bw)

    def roles(self):
        return dict(ROLES)


class FakeSend:
    """Ghi lai thu tu goi de kiem write-ahead."""

    def __init__(self, twin=None, journal=None, fail=False):
        self.calls = []
        self.twin = twin
        self.journal = journal
        self.fail = fail

    def __call__(self, command, cid=None):
        if self.journal is not None:
            self.journal.append(("send", command["cid"]))
        self.calls.append(command)
        if self.fail:
            raise RuntimeError("send that bai")
        if self.twin is not None:          # gia lap hieu luc tuc thi
            link = command["target"].split(":link-", 1)[1]
            self.twin.bw[link] = float(command["params"]["bw"])
        return {"cid": command["cid"], "http_status": 202, "post_ms": 12.0,
                "post_error": None}


class JournalLog(LockedInterventionLog):
    def __init__(self, journal):
        super().__init__(InMemoryInterventionLog())
        self.journal = journal

    def append(self, item):
        self.journal.append(("append", item.id))
        super().append(item)


def make_runner(tmp_path, twin, send=None, log_store=None, params=None):
    clock = FakeClock()
    runner = ControlRunner(
        twin=twin,
        # `is None`, KHONG dung `or`: LockedInterventionLog co __len__ nen log
        # rong la FALSY -> `or` se am tham thay bang log mac dinh.
        log_store=LockedInterventionLog(InMemoryInterventionLog())
        if log_store is None else log_store,
        routing=Routing.load(ROOT / "ditto/routing_table.json"),
        send_command=send or FakeSend(twin),
        params=params or PolicyParams(),
        audit_path=tmp_path / "audit.jsonl",
        clock=clock,
        wall_clock=lambda: 1_000_000.0 + clock(),
        sleeper=clock.advance,   # dong ho gia PHAI tien khi ngu, neu khong vong cho treo
    )
    return runner, clock


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
        return self.t


# ------------------------------------------------------------ bulkhead


def test_controller_khong_chay_tren_collector():
    """Bulkhead: controller/ khong duoc import Collector hay chay tren on_tick."""
    for path in sorted((ROOT / "controller").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("from bridge.collector", "import Collector", "on_tick"):
            assert forbidden not in source, "%s: %s" % (path.name, forbidden)


def test_thu_tu_timeout_nhat_quan():
    """Loi timeout pho bien nhat khong phai sai gia tri ma la HAI TIMEOUT
    KHONG NHAT QUAN voi nhau."""
    params = PolicyParams()
    assert TICK_S < RENEW_PERIOD_S < LEASE_TTL_S
    assert RENEW_PERIOD_S * 3 <= LEASE_TTL_S
    assert LEASE_TTL_S <= params.t0_s
    assert params.t0_s <= params.t_max_s < MAX_OPEN_S - 5.0


# ------------------------------------------------------------ write-ahead


def test_write_ahead_append_truoc_khi_gui(tmp_path):
    journal = []
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    log_store = JournalLog(journal)
    runner, clock = make_runner(tmp_path, twin, send=FakeSend(twin, journal),
                                log_store=log_store)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    assert journal[0][0] == "append" and journal[1][0] == "send"
    assert journal[0][1] == journal[1][1]          # cung intervention_id = cid


def test_mot_action_mot_append(tmp_path):
    """_reassert KHONG duoc append: id tat dinh + log append-only -> ValueError."""
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()                                   # inject
    assert len(runner.log) == 1
    for _ in range(12):                             # nhieu nhip gia han
        clock.advance(TICK_S)
        twin.state = "unknown"
        twin.cause = "suppressed_intervention"
        runner.tick()
    assert len(runner.log) == 1                     # VAN mot
    assert runner.stats["renewals"] >= 2


def test_t_start_dung_wall_clock(tmp_path):
    """FSM so t_start voi t_source (wall). Dung monotonic o day -> uc che sai hoan toan."""
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    item = runner.log.snapshot()[0]
    assert item.t_start >= 1_000_000.0              # wall clock gia, khong phai mono


# ------------------------------------------------------------ reconcile


def test_reconcile_sua_troi_gia_tri(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    assert twin.bw["h1-s1"] == 7.0
    twin.bw["h1-s1"] = 20.0                         # ai do ghi de tc
    clock.advance(CONFIRM_GRACE_S + TICK_S)         # qua han an han quan sat
    runner.tick()
    assert twin.bw["h1-s1"] == 7.0                  # vong LEVEL tu sua
    assert runner.stats["drift_fixes"] == 1


def test_observed_chua_biet_thi_khong_hanh_dong(tmp_path):
    """Nguyen tac ba trang thai: dung / sai / CHUA BIET. Gop 'chua biet' vao
    'sai' la nguon cua phan lon hanh vi hoang loan."""
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(None)                           # khong cap nhat twin
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    twin.bw.pop("h1-s1")                            # SSE chua gui delta link nay
    before = len(send.calls)
    clock.advance(TICK_S)
    runner.tick()
    assert len(send.calls) == before                # khong ban lenh mu
    assert runner.stats["unknown_observed"] >= 1


def test_gia_han_dung_chu_ky_va_cid_tat_dinh(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    first_cid = send.calls[-1]["cid"]
    for _ in range(int(RENEW_PERIOD_S)):
        clock.advance(TICK_S)
        runner.tick()
    renew = [c for c in send.calls if "#r" in c["cid"]]
    assert renew, "chua co lan gia han nao"
    assert renew[-1]["params"]["leaseS"] == LEASE_TTL_S
    assert runner.renewal_cid(clock()) == runner.renewal_cid(clock())   # tat dinh
    assert renew[-1]["cid"].startswith(first_cid)


def test_gui_lenh_luon_kem_lease_khi_inject(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    assert send.calls[0]["params"]["leaseS"] == LEASE_TTL_S


# ------------------------------------------------------------ revert-first


def test_revert_first_don_trang_thai_vo_chu(tmp_path):
    """Controller restart khi bw dang 7.0: phai GO truoc khi vao IDLE."""
    twin = FakeTwin(bw={"h1-s1": 7.0, "h2-s1": 20.0})
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    cstate = runner.bootstrap_safe_state()
    assert twin.bw["h1-s1"] == 20.0
    assert cstate.mode == "IDLE" and runner.stats["orphans_reverted"] == 1
    assert len(runner.log) == 1                     # co write-ahead


def test_revert_orphan_co_write_ahead(tmp_path):
    journal = []
    twin = FakeTwin(bw={"h1-s1": 7.0})
    runner, clock = make_runner(tmp_path, twin, send=FakeSend(twin, journal),
                                log_store=JournalLog(journal))
    runner.bootstrap_safe_state()
    assert journal[0][0] == "append" and journal[1][0] == "send"


def test_chi_dieu_hoa_link_minh_so_huu(tmp_path):
    """Fighting controllers: khong dung vao tai nguyen khong phai cua minh."""
    twin = FakeTwin(bw={"h1-s1": 20.0, "s2-s3": 3.0, "srv1-s2": 11.0})
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.bootstrap_safe_state()
    assert send.calls == []
    assert twin.bw["s2-s3"] == 3.0 and twin.bw["srv1-s2"] == 11.0


def test_boot_khong_co_du_lieu_thi_HOLD(tmp_path):
    twin = FakeTwin(bw={})
    runner, clock = make_runner(tmp_path, twin)
    cstate = runner.bootstrap_safe_state()
    assert cstate.mode == "HOLD" and cstate.reason == "boot_no_twin_data"
    assert runner.stats["commands"] == 0


# ------------------------------------------------------------ ngoai le 8.3


def test_act_trong_mitigating_khong_sinh_hanh_dong(tmp_path):
    """Ngoai le uc che do o 8.3: vung 15/16 thieu link-s2-s3 nen detector CO THE
    vao act trong luc dang MITIGATING. Circuit breaker phai nuot no."""
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    n_after_inject = len(send.calls)
    episode = runner.cstate.episode
    for _ in range(5):                              # detector van bao act
        clock.advance(TICK_S)
        runner.tick()
    assert runner.cstate.mode == "MITIGATING"
    assert runner.cstate.episode == episode         # khong mo episode moi
    assert len(runner.log) == 1                     # khong can thiep moi
    assert all("#r" in c["cid"] for c in send.calls[n_after_inject:])


# ------------------------------------------------------------ tat / hong


def test_tat_em_go_can_thiep(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(twin)
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    cstate = runner.shutdown()
    assert twin.bw["h1-s1"] == 20.0
    assert cstate.mode == "HOLD" and cstate.reason == "shutting_down"
    assert send.calls[-1]["params"]["bw"] == 20.0


def test_tat_em_that_bai_van_thoat(tmp_path):
    """Go that bai KHONG duoc ngan thoat, neu khong `systemctl stop` treo."""
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin, send=FakeSend(twin))
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    runner.send = FakeSend(None, fail=True)
    cstate = runner.shutdown()                      # khong duoc nem ra ngoai
    assert cstate.mode in ("MITIGATING", "HOLD")


def test_crash_loop_fail_closed(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("hong")

    runner.tick = boom
    verdict = runner.run_forever()
    assert verdict == "crash_loop"
    assert calls["n"] == CRASH_LOOP[0] + 1
    assert runner.cstate.mode == "HOLD" and runner.cstate.reason == "crash_loop"


# ------------------------------------------------------------ audit / C10


def test_audit_du_de_dung_lai_bit_exact(tmp_path):
    from controller.audit import read_rows, verify_chain

    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    assert verify_chain(runner.audit.path)["ok"] is True
    row = [r for r in read_rows(runner.audit.path) if r["kind"] == "inject"][0]
    view = DetectorView(
        state=row["input"]["state"], cause=row["input"]["cause"],
        affected=tuple(row["input"]["affected"]),
        roles=tuple(sorted(row["roles"].items())), fresh=row["input"]["fresh"],
        boot_id=row["input"]["bootId"], seq=row["input"]["seq"],
    )
    before = ControllerState(**row["cstate_before"])
    actions, after = decide(view, before, row["now_mono"], PolicyParams())
    assert [a.intervention_id for a in actions] == [
        a["intervention_id"] for a in row["actions"]
    ]
    assert after.mode == row["cstate_after"]["mode"]


# ------------------------------------------------------------ an toan luong


def test_log_an_toan_luong():
    from ml.intervention_log import Intervention

    log_store = LockedInterventionLog(InMemoryInterventionLog())
    errors = []

    def make(index):
        return Intervention(
            id="w-%d:inject" % index, t_start=time.time(), actor="t",
            action="inject:rate_limit", targets={"links": ["h1-s1"], "flows": []},
            blast_radius=frozenset({"link-h1-s1"}), routing_sha256="x",
        )

    def writer():
        for index in range(2000):
            try:
                log_store.append(make(index))
            except Exception as exc:
                errors.append(exc)

    def reader():
        for _ in range(2000):
            try:
                log_store.active(time.time(), 8.0)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(log_store) == 2000


def test_tre_quan_sat_khong_bi_coi_la_troi_gia_tri(tmp_path):
    """Sau khi gui lenh, twin can ~1 tick moi phan anh (p50 667 ms, p95 1003 ms
    do o 8.4). Coi khoang do la 'troi' se gui mot lenh thua moi lan can thiep."""
    from controller.runner import CONFIRM_GRACE_S

    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    send = FakeSend(None)                  # KHONG cap nhat twin: gia lap tre
    runner, clock = make_runner(tmp_path, twin, send=send)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()                          # inject; twin van bao 20.0
    n = len(send.calls)
    clock.advance(CONFIRM_GRACE_S / 2)
    runner.tick()
    assert len(send.calls) == n and runner.stats["drift_fixes"] == 0
    clock.advance(CONFIRM_GRACE_S)         # qua han an han -> moi la troi that
    runner.tick()
    assert runner.stats["drift_fixes"] == 1


def test_tat_em_giu_dau_vet_episode(tmp_path):
    twin = FakeTwin(bw={"h1-s1": 20.0}, state="act", affected=(H1,))
    runner, clock = make_runner(tmp_path, twin)
    runner.cstate = ControllerState(mode="IDLE")
    runner.tick()
    episode = runner.cstate.episode
    cstate = runner.shutdown()
    assert cstate.episode == episode == 1   # khong xoa dau vet khi tat
    assert cstate.mode == "HOLD" and cstate.open_id is None
