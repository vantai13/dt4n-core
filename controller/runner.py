#!/usr/bin/env python3
"""Vong kin Phase 8 - KHOANG THU BA, doc lap voi collector (Lesson 8.4).

Kien truc 4 luong:

    collector ──mailbox──> detector-writer ──PATCH──> Ditto
                                                        │ SSE
                                                   twin-sse
                                                        │ cache
                                                   CONTROL   <- file nay

Diem giao DUY NHAT giua khoang collector va khoang control la intervention_log
(control GHI, collector DOC), boc bang LockedInterventionLog.

KHONG chay trong callback cua collector: gui lenh p95 984 ms se lam collector tre tick ->
tick_overruns -> chuoi thoi gian meo -> detector DA DONG BANG cho ket qua khac
luc train. Controller se pha chinh cam bien no phu thuoc (vong phan hoi duong
o tang TAI NGUYEN, kho thay hon o tang logic).

EDGE cho quyet dinh (latch muc tieu tai suon len), LEVEL cho duy tri (moi nhip
so desired voi observed). Ly do LEVEL: su kien co the mat o BON cho da biet -
mailbox ghi de, PATCH khong retry, SSE reconnect tra ban cu, R3 bo ca ban tin.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, replace

from bridge.detector_contract import new_boot_id
from controller.audit import AuditLog, sha
from controller.intervene import to_command, to_intervention
from controller.policy import (
    Action,
    ControllerState,
    DetectorView,
    PolicyParams,
    decide,
    desired_bw,
    link_of,
)

log = logging.getLogger("controller.runner")

TICK_S = 1.0
EPS_MBPS = 0.01              # so thuc: khong bao gio so sanh bang `==`
RENEW_PERIOD_S = 5.0         # chiu duoc 2 lan lo trong LEASE_TTL_S
LEASE_TTL_S = 15.0           # 3 x chu ky gia han
BOOT_SSE_WAIT_S = 10.0
# Sau khi gui lenh, twin can ~1 tick collector + PATCH + SSE moi phan anh gia
# tri moi (do that o 8.4: p50 667 ms, p95 1003 ms). Trong khoang do, "observed
# khac desired" la TRE QUAN SAT, khong phai troi gia tri: coi la troi se gui
# them mot lenh thua moi lan can thiep.
CONFIRM_GRACE_S = 2.0
# Khe ho list-then-watch (prime GET tai t0, SSE mo tai t1): su kien trong
# [t0, t1] bi mat. Tu lanh nho sync_agent day FULL STATE moi `reconcile_every`
# chu ky (mac dinh 30, bridge/sync_agent.py:54). Neu ai do ha ve 0, cache co
# the sai VINH VIEN -> test_reconcile_every_phai_bat canh gac dieu do.
STALE_OBSERVE_HEAL_S = 30.0
# Khi mot vong sua loi lap lai ma loi khong bien mat, no khong con sua loi nua -
# no dang thanh NGUON TAI. Sau 3 lan troi lien tiep, gian chu ky gui lai.
DRIFT_STREAK_ALERT = 3
DRIFT_BACKOFF_MAX_S = 30.0
SHUTDOWN_TIMEOUT_S = 5.0
CRASH_LOOP = (5, 60.0)
ACCESS_SWITCH = "s1"         # ditto/topology_spec.json: client deu treo vao s1


def _row(item) -> dict:
    return asdict(item)


def _view_row(view: DetectorView) -> dict:
    return {
        "state": view.state,
        "cause": view.cause,
        "affected": list(view.affected),
        "fresh": view.fresh,
        "bootId": view.boot_id,
        "seq": view.seq,
    }


def _slim(result) -> dict:
    if not isinstance(result, dict):
        return {"result": str(result)}
    return {key: result.get(key)
            for key in ("cid", "http_status", "post_ms", "post_error")}


class ControlRunner:
    """Vong dieu khien. Moi thu ban (I/O, dong ho, mang) nam o day; decide() van thuan."""

    def __init__(self, twin, log_store, routing, send_command, publish=None,
                 params=None, audit_path="logs/controller_audit.jsonl",
                 clock=time.monotonic, wall_clock=time.time, sleeper=None,
                 view_provider=None):
        self.twin = twin                  # TwinReader        (hop dong A)
        self.log = log_store              # LockedInterventionLog (hop dong B)
        self.routing = routing
        self.send = send_command          # env.send_command(cmd, cid=...)  (hop dong C)
        self.publish = publish            # callable(document) -> PATCH controlloop (D)
        self.params = params or PolicyParams()
        self.audit = AuditLog(audit_path)  # hop dong E
        self.clock = clock
        self.wall_clock = wall_clock
        # Ablation 8.6: thay DUY NHAT nguon kich hoat, giu nguyen moi thu khac
        # (FSM, backoff, actuator, lease, audit, reconcile). Mac dinh la detector.
        self.view_provider = view_provider

        self.boot_id = new_boot_id()
        self.cstate = ControllerState(mode="HOLD", reason="never_started",
                                      incarnation=self.boot_id)
        self.seq = 0
        self.opened_at_mono = None
        self._last_renew = {}
        self._last_send = {}
        self._drift_streak = {}
        self._stop = threading.Event()
        # tick() va shutdown() cung sua cstate VA cung co the phat `revert` cho
        # cung mot open_id. Chay song song -> hai duong sinh CUNG mot
        # intervention_id -> InterventionLog.append nem ValueError (id tat dinh,
        # append-only). Day la mot data race THAT, bat duoc khi chay A/B live.
        self._lock = threading.RLock()
        self._sleep = sleeper or self._stop.wait
        self._exc_times = deque(maxlen=CRASH_LOOP[0] + 1)
        self.stats = {
            "ticks": 0, "commands": 0, "renewals": 0, "drift_fixes": 0,
            "orphans_reverted": 0, "exceptions": 0, "unknown_observed": 0,
        }

    # ------------------------------------------------------------ khoi dong

    def bootstrap_safe_state(self):
        """Revert-first: don TRANG THAI VO CHU truoc khi nhan quyet dinh moi.

        Giong crash recovery cua CSDL: undo giao dich do dang truoc khi nhan
        giao dich moi. Neu bo qua, mot controller restart se tin minh dang IDLE
        trong khi mang van bi gioi han, va KHONG AI se go.
        """
        deadline = self.clock() + BOOT_SSE_WAIT_S
        observed = self.twin.observed_bw()
        while not observed and self.clock() < deadline:
            self._sleep(0.2)
            observed = self.twin.observed_bw()
        if not observed:
            # CHUA BIET != KHONG CO CAN THIEP. IDLE nghia la "toi da kiem tra va
            # khong co gi dang mo" - noi the luc nay la noi doi.
            log.error("khong co du lieu bw tu twin sau %.0f s -> HOLD",
                      BOOT_SSE_WAIT_S)
            self.cstate = ControllerState(mode="HOLD", reason="boot_no_twin_data",
                                          incarnation=self.boot_id)
            return self.cstate

        roles = self.twin.roles()
        for link, bw in sorted(observed.items()):
            if not self._owned(link, roles):
                continue     # chi dieu hoa tai nguyen MINH so huu (chong fighting controllers)
            if abs(bw - self.params.default_mbps) <= EPS_MBPS:
                continue
            log.warning("trang thai VO CHU: %s bw=%.2f -> phuc hoi %.2f",
                        link, bw, self.params.default_mbps)
            action = Action(
                "revert", link, self.params.default_mbps,
                "ctl-%s-orphan-%s:revert" % (self.boot_id, link),
                "orphan_revert",
            )
            # Revert orphan CUNG phai write-ahead: doi bw cung la mot nhieu loan
            # (reset qdisc) va detector se bao dong neu khong duoc bao truoc.
            self._execute(action)
            self.stats["orphans_reverted"] += 1

        self.cstate = ControllerState(mode="IDLE", reason="boot_clean",
                                      incarnation=self.boot_id)
        return self.cstate

    def _owned(self, link: str, roles: dict) -> bool:
        """Chi link truy nhap cua client: `<client>-s1` (prereg 8.1)."""
        host, _, switch = link.partition("-")
        return switch == ACCESS_SWITCH and roles.get(host) == "client"

    # ------------------------------------------------------------ vong chinh

    def run_forever(self):
        self.bootstrap_safe_state()
        next_tick = self.clock()
        while not self._stop.is_set():
            next_tick += TICK_S
            try:
                self.tick()
            except Exception:
                if self._stop.is_set():
                    break                       # dang tat: khong tinh la crash loop
                self.stats["exceptions"] += 1
                self._exc_times.append(self.clock())
                log.exception("loi trong control tick")
                if (len(self._exc_times) > CRASH_LOOP[0]
                        and self._exc_times[-1] - self._exc_times[0] < CRASH_LOOP[1]):
                    self._enter_crash_loop()
                    return "crash_loop"
            remaining = next_tick - self.clock()
            if remaining > 0:
                self._sleep(remaining)
            else:
                next_tick = self.clock()     # bi tre -> KHONG don tick bu
        return "stopped"

    def tick(self):
        with self._lock:
            return self._tick_locked()

    def _tick_locked(self):
        # Sau khi shutdown() da dat co dung, vong tick KHONG duoc phat them hanh
        # dong nao: no se sinh LAI dung `revert` ma shutdown vua phat (id tat
        # dinh) -> InterventionLog.append nem ValueError -> chuoi ngoai le ->
        # crash loop gia. Bat duoc khi chay A/B live o 8.6.
        if self._stop.is_set():
            return self.cstate
        now = self.clock()
        self.stats["ticks"] += 1

        # 1) EDGE: quyet dinh - ham THUAN, moi dau vao tu twin
        view = self.build_view()
        cstate_before = self.cstate
        actions, self.cstate = decide(view, cstate_before, now, self.params)
        if self.cstate.open_id and not cstate_before.open_id:
            self.opened_at_mono = now
        if not self.cstate.open_id:
            self.opened_at_mono = None
            self._last_renew.clear()

        # C10 doi 100% QUYET DINH dung lai duoc, khong phai 100% hanh dong.
        # Mot quyet dinh KHONG sinh hanh dong van la mot quyet dinh - va la loai
        # kho giai thich nhat ("vi sao luc do controller khong lam gi?").
        # Day cung la cong cu chan doan dau tien: loi live #1 cua 8.4 (291 tick
        # / 0 lenh) se lo ra ngay o 291 dong `idle_no_client_candidate`.
        self._audit_tick(view, cstate_before, self.cstate, actions, now)

        for action in actions:
            self._execute(action, view=view, cstate_before=cstate_before,
                          cstate_after=self.cstate, now_mono=now)

        # 2) LEVEL: dieu hoa desired vs observed
        self.reconcile(now)

        # 3) Cong bo trang thai cua CHINH controller (hop dong D)
        self._publish(now)
        return self.cstate

    def _audit_tick(self, view, cstate_before, cstate_after, actions, now):
        """Moi lan goi decide() deu de lai dau vet du de goi lai decide()."""
        changed = (cstate_after.mode != cstate_before.mode) or bool(actions)
        row = {
            "kind": "decision",
            "t_mono": now,
            "t_wall": self.wall_clock(),
            "input": _view_row(view),
            "cstate_before": _row(cstate_before),
            "cstate_after": _row(cstate_after),
            "n_actions": len(actions),
            "changed": changed,
        }
        # roles la DAU VAO BAT BUOC cua localize() moi khi nhan la ACT. Tick
        # "act nhung khong dinh vi duoc" KHONG lam doi mode nen changed=False -
        # ma do lai dung la loai tick can dung lai nhat (loi live #1 cua 8.4:
        # 291 tick nhu vay). Thieu roles o day = C10 khong dat o dung cho kho nhat.
        if changed or view.state == "act":
            row["roles"] = dict(view.roles)
            row["params_sha256"] = sha(asdict(self.params))
        return self.audit.append(row)

    def build_view(self) -> DetectorView:
        if self.view_provider is not None:
            return self.view_provider()
        fields = self.twin.detector_view_fields()
        return DetectorView(
            state=fields["state"],
            cause=fields["cause"],
            affected=fields["affected"],
            roles=tuple(sorted(self.twin.roles().items())),
            fresh=fields["fresh"],
            boot_id=fields["boot_id"],
            seq=fields["seq"],
        )

    # ------------------------------------------------------------ LEVEL

    def reconcile(self, now):
        """desired - observed. Vong nay KHONG co bo nho ve viec da gui lenh hay chua."""
        desired = desired_bw(self.cstate, self.params)
        observed = self.twin.observed_bw()
        for link, want in sorted(desired.items()):
            have = observed.get(link)
            if have is None:
                self.stats["unknown_observed"] += 1
                continue                       # CHUA BIET != SAI
            if abs(have - want) > EPS_MBPS:
                streak = self._drift_streak.get(link, 0)
                # Gian dan 2 -> 4 -> 8 ... (tran 30 s): 3 lan lien tiep nghia la
                # lenh KHONG mat, ma quan sat bi ket hoac co TAC NHAN KHAC dang
                # ghi de. Ca hai deu khong sua duoc bang cach ban them lenh.
                wait = min(CONFIRM_GRACE_S * (2 ** streak), DRIFT_BACKOFF_MAX_S)
                if now - self._last_send.get(link, float("-inf")) < wait:
                    continue          # TRE QUAN SAT hoac dang giam tan suat
                self._drift_streak[link] = streak + 1
                if self._drift_streak[link] >= DRIFT_STREAK_ALERT:
                    log.error("DRIFT DAI DANG %s: want=%.2f have=%.2f streak=%d "
                              "(khe ho list-then-watch tu lanh trong <= %.0f s)",
                              link, want, have, self._drift_streak[link],
                              STALE_OBSERVE_HEAL_S)
                self._reassert(link, want, now, "drift")
                self.stats["drift_fixes"] += 1
            elif now - self._last_renew.get(link, float("-inf")) >= RENEW_PERIOD_S:
                self._drift_streak.pop(link, None)   # da khop lai -> quen chuoi troi
                self._reassert(link, want, now, "lease_renew")
                self.stats["renewals"] += 1

    def renewal_cid(self, now) -> str:
        """Tat dinh: cung (open_id, opened_at, now) -> cung cid, nen C10 van dung lai duoc.

        Khong dung lai cid cu vi `processed_result` se tra ket qua cache va
        KHONG cham Mininet -> lease khong duoc gia han.
        """
        base = self.cstate.open_id or "ctl-%s-unowned" % self.boot_id
        opened = self.opened_at_mono if self.opened_at_mono is not None else now
        index = int((now - opened) // RENEW_PERIOD_S)
        return "%s#r%d" % (base, index)

    def _reassert(self, link, bw, now, reason):
        """Gui LAI lenh. KHONG append InterventionLog: MOT ACTION = MOT APPEND.

        Append lan hai se ValueError (id tat dinh, log append-only) -> crash.
        Lenh trung gia tri la no-op o phia agent (ban va 8.4) nen khong reset qdisc.
        """
        cid = self.renewal_cid(now)
        command = {
            "subject": "setBandwidth",
            "target": "org.dt4n:link-" + link,
            "params": {"bw": float(bw), "leaseS": LEASE_TTL_S},
            "cid": cid,
        }
        result = self.send(command, cid=cid)
        self._last_renew[link] = now
        self._last_send[link] = now
        self.stats["commands"] += 1
        self.audit.append({
            "kind": "reassert", "reason": reason, "t_mono": now,
            "t_wall": self.wall_clock(), "command": command,
            "result": _slim(result),
        })
        return result

    # ------------------------------------------------------------ EDGE

    def _execute(self, action, view=None, cstate_before=None,
                 cstate_after=None, now_mono=None):
        now_mono = self.clock() if now_mono is None else now_mono
        # WALL CLOCK: FSM so t_start voi t_source cua snapshot (M8). KHONG dung
        # monotonic o day du policy dung monotonic cho deadline - hai dong ho,
        # hai muc dich, khong duoc lan.
        t_wall = self.wall_clock()
        intervention = to_intervention(action, self.routing, t_wall)
        self.log.append(intervention)                       # (1) WRITE-AHEAD (M5)
        command = to_command(action)
        if action.kind == "inject":
            command["params"]["leaseS"] = LEASE_TTL_S       # dead-man switch
        result = self.send(command, cid=command["cid"])     # (2) roi moi gui
        self.stats["commands"] += 1
        # Lenh vua gui DA gia han lease; khong de vong LEVEL gui them mot lan
        # nua ngay trong cung mot nhip (se thanh hai lenh cho mot quyet dinh).
        if action.kind == "inject":
            self._last_renew[action.link] = now_mono
        self._last_send[action.link] = now_mono
        self.audit.append({
            "kind": action.kind,
            "t_mono": now_mono,
            "t_wall": t_wall,
            "input": None if view is None else _view_row(view),
            "roles": None if view is None else dict(view.roles),
            "now_mono": now_mono,
            "params_sha256": sha(asdict(self.params)),
            "cstate_before": None if cstate_before is None else _row(cstate_before),
            "cstate_after": None if cstate_after is None else _row(cstate_after),
            "actions": [_row(action)],
            "intervention": {
                "id": intervention.id,
                "action": intervention.action,
                "blast_radius_n": len(intervention.blast_radius),
                "routing_sha256": intervention.routing_sha256,
            },
            "command": command,
            "result": _slim(result),
        })
        return result

    # ------------------------------------------------------------ hop dong D

    def _publish(self, now):
        if self.publish is None:
            return None
        from bridge import controlloop_contract as CL

        self.seq += 1
        iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.wall_clock()))
        document = CL.build_document(
            self.cstate, self.params,
            boot_id=self.boot_id, seq=self.seq, heartbeat_at=iso,
            decided_at=iso, now_mono=now, dropped=getattr(self.twin, "dropped", 0),
            provenance=self.provenance(),
        )
        try:
            self.publish(document)
        except Exception:
            log.exception("PATCH controlloop that bai (bo qua mot nhip)")
        return document

    def provenance(self) -> dict:
        from ml import campaign as C

        def digest(rel):
            try:
                return C.sha256_bytes((C.ROOT / rel).read_bytes())
            except OSError:
                return ""

        return {
            "policySha256": digest("controller/policy.py"),
            "preregSha256": digest("results/report/phase8_prereg.json"),
            "simPredictionsSha256": digest("results/report/phase8_sim_predictions.json"),
            "contractSha256": digest("results/report/phase8_contract.json"),
            "detectorReleaseSha256": self.twin.detector_view_fields().get(
                "release_sha256", ""
            ),
        }

    # ------------------------------------------------------------ tat / hong

    def shutdown(self, timeout_s=SHUTDOWN_TIMEOUT_S):
        with self._lock:
            return self._shutdown_locked(timeout_s)

    def _shutdown_locked(self, timeout_s=SHUTDOWN_TIMEOUT_S):
        """Go can thiep dang mo TRUOC khi thoat.

        KHONG dua vao dead-man switch o duong thoat BINH THUONG: switch la luoi
        an toan cho truong hop bat thuong. Dua vao no moi lan restart = 17 s suy
        giam khong can thiet.
        """
        self._stop.set()
        deadline = self.clock() + timeout_s
        # Sau khi doat khoa, vong tick co the VUA go xong (open_id = None) ->
        # khong con gi de go. shutdown phai LU Y DANG.
        if self.cstate.open_id and self.cstate.target:
            action = Action(
                "revert", link_of(self.cstate.target), self.params.default_mbps,
                self.cstate.open_id.replace(":inject", ":revert"),
                "graceful_shutdown",
            )
            try:
                self._execute(action)
                self.cstate = replace(self.cstate, mode="HOLD", target=None,
                                      open_id=None, deadline_mono=None,
                                      window_end_mono=None,
                                      reason="shutting_down")
            except Exception:
                # Go that bai KHONG duoc ngan tien trinh thoat, neu khong
                # `systemctl stop` se treo. Lease la luoi do.
                log.exception("go can thiep luc tat that bai -> dua vao lease")
        else:
            self.cstate = replace(self.cstate, mode="HOLD",
                                  reason="shutting_down")
        if self.clock() > deadline:
            log.warning("tat em qua han %.1f s", timeout_s)
        self._publish(self.clock())
        return self.cstate

    def _enter_crash_loop(self):
        """Fail-closed: go can thiep, ngung quyet dinh, NHUNG giu heartbeat.

        Chet im lang khac han voi "con song va dang tu choi hoat dong": cai sau
        nhin thay duoc tren dashboard.
        """
        log.error("crash loop: %d loi trong %.0f s -> ngung quyet dinh",
                  len(self._exc_times), CRASH_LOOP[1])
        try:
            if self.cstate.open_id and self.cstate.target:
                action = Action(
                    "revert", link_of(self.cstate.target), self.params.default_mbps,
                    self.cstate.open_id.replace(":inject", ":revert"), "crash_loop",
                )
                self._execute(action)
        except Exception:
            log.exception("go can thiep khi crash loop that bai -> dua vao lease")
        self.cstate = replace(self.cstate, mode="HOLD", reason="crash_loop")
        self._publish(self.clock())

    def stop(self):
        self._stop.set()
