#!/usr/bin/env python3
"""Policy cua controller Phase 8 - HAM THUAN.

    decide(view, cstate, now_mono, params) -> (actions, cstate')

Khong I/O, khong dong ho, khong random, khong file, khong sinh id ngau nhien.
Moi dieu cam N10-N16 la MOT DONG trong bang chuyen trang thai, khong phai mot
`if` rai rac - nho vay test duoc bang liet ke (C7) va mo phong duoc (C6).

Circuit breaker 4 trang thai:
    IDLE --act+dinh vi ro--> MITIGATING --het gio giu--> PROBING --sach--> IDLE
                                   ^                        |
                                   +----act lai trong W-----+   (T <- min(2T, T_max))
    Bat ky trang thai nao + freshness chet -> HOLD.

Nguyen tac: KHONG BAO GIO go vi "trong co ve khoe". Su khoe manh quan sat duoc
trong luc dang can thiep la bang chung VO GIA TRI (do chinh minh tao ra). Go
theo LICH, va moi lan go la mot thi nghiem (probe).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from controller.localize import localize

# Lease cua ml/intervention_log.py::MAX_OPEN_S. De o day duoi dang hang so vi
# module nay khong duoc import runtime; test/test_phase8_policy.py kiem hai
# gia tri phai bang nhau.
LEASE_MAX_OPEN_S = 120.0

# Tre chet da do cua nhanh "phat hien lai" sau khi revert:
#   cooldown_s 8.0 (detector-release-1.0.0.json)
# + phys_obs p95 1.433 s (phase7_e2e_latency.json)
# + n_act 2 tick (detector-release-1.0.0.json)
DEAD_TIME_S = 8.0 + 1.433 + 2.0


# ---------------------------------------------------------------- tham so


@dataclass(frozen=True)
class PolicyParams:
    t0_s: float = 15.0           # thoi gian giu lan dau
    t_max_s: float = 110.0       # tran; PHAI < LEASE_MAX_OPEN_S - bien
    probe_w_s: float = 14.0      # cua so probe; >= DEAD_TIME_S + bien
    growth: float = 2.0          # he so backoff mu
    limit_mbps: float = 7.0      # prereg 8.1 (tran tai hop le train 6.181986)
    default_mbps: float = 20.0   # mininet/topology.py:88 bw_backbone
    lease_margin_s: float = 5.0  # bien cho do tre lenh p95 0.984 s + ghi log

    def __post_init__(self):
        if not (0 < self.t0_s <= self.t_max_s):
            raise ValueError("can 0 < t0_s <= t_max_s")
        if self.t_max_s >= LEASE_MAX_OPEN_S - self.lease_margin_s:
            raise ValueError(
                "t_max_s phai < MAX_OPEN_S - bien (lease %.0f s)" % LEASE_MAX_OPEN_S
            )
        if self.probe_w_s < DEAD_TIME_S:
            raise ValueError(
                "cua so probe ngan hon tre chet da do (%.3f s)" % DEAD_TIME_S
            )
        if self.growth < 1.0:
            raise ValueError("backoff khong duoc co lai")


# ---------------------------------------------------------------- kieu du lieu


@dataclass(frozen=True)
class DetectorView:
    """Anh chup cai controller DOC tu twin. Khong chua gi controller tu tinh."""

    state: str                           # warming_up|normal|suspect|act|unknown
    cause: str
    affected: tuple[str, ...]            # evidence.affected (R2)
    roles: tuple[tuple[str, str], ...]   # ((host, role), ...) - tuple de hashable
    fresh: bool                          # ket qua MonotonicFreshness (R3)
    boot_id: str
    seq: int


@dataclass(frozen=True)
class ControllerState:
    mode: str = "IDLE"                    # IDLE | MITIGATING | PROBING | HOLD
    target: str | None = None
    attempt: int = 0                      # k - so probe that bai lien tiep
    deadline_mono: float | None = None    # het gio giu
    window_end_mono: float | None = None  # het cua so probe
    open_id: str | None = None            # id can thiep dang mo
    episode: int = 0                      # tang moi lan vao MITIGATING tu IDLE
    reason: str = "boot"
    mode_before_hold: str | None = None
    # Lan chay (incarnation) cua CHINH controller. Phai co trong id can thiep:
    # view.boot_id la bootId cua DETECTOR va no khong doi khi controller khoi
    # dong lai, nen mot controller moi se sinh lai dung "e1-k0:inject" va
    # InterventionLog (append-only) nem ValueError. Bat duoc khi chay A/B o 8.6,
    # noi moi luot dung mot ControlRunner moi tren cung mot detector.
    incarnation: str = ""


@dataclass(frozen=True)
class Action:
    kind: str            # "inject" | "revert"
    link: str            # "h1-s1"
    bw_mbps: float
    intervention_id: str
    reason: str


# ---------------------------------------------------------------- nhan dau vao

STALE = "STALE"
STALE_INTERVENTION = "STALE_INTERVENTION"
OUT_OF_RANGE = "OUT_OF_RANGE"
WARMING = "WARMING"
SUPPRESSED = "SUPPRESSED"
UNKNOWN = "UNKNOWN"
ACT = "ACT"
QUIET = "QUIET"   # normal VA suspect - N10 hien thuc hoa bang cach GOP

LABELS = (
    STALE, STALE_INTERVENTION, OUT_OF_RANGE, WARMING,
    SUPPRESSED, UNKNOWN, ACT, QUIET,
)


def classify(view: DetectorView) -> str:
    """THU TU CO Y NGHIA: freshness kiem TRUOC state.

    Mot ban tin `act` da het TTL van la ban tin chet (N12). Dao thu tu ->
    N12 bi pha ma test don le van pass.
    """
    if not view.fresh:
        return STALE
    if view.cause == "stale_intervention":        # N15
        return STALE_INTERVENTION
    if view.cause == "out_of_operating_range":    # N16
        return OUT_OF_RANGE
    if view.state == "warming_up":
        return WARMING
    if view.state == "unknown":
        return SUPPRESSED if view.cause == "suppressed_intervention" else UNKNOWN
    if view.state == "act":                       # R1 - loi vao DUY NHAT
        return ACT
    return QUIET                                  # normal + suspect (N10)


# ---------------------------------------------------------------- tien ich thuan


def hold_seconds(params: PolicyParams, attempt: int) -> float:
    """T_k = min(T0 * growth^k, T_max)."""
    return min(params.t0_s * (params.growth ** attempt), params.t_max_s)


def _iid(view: DetectorView, cstate: ControllerState, kind: str) -> str:
    """Id TAT DINH. KHONG ngau nhien: C10 doi dung lai bit-exact tu audit.

    Gom CA bootId cua detector (truy vet ban tin nao sinh ra quyet dinh) LAN
    incarnation cua controller (phan biet hai lan chay controller tren cung mot
    detector). Thieu ve thu hai -> trung id -> append-only nem ValueError.
    """
    prefix = "ctl-%s" % view.boot_id
    if cstate.incarnation:
        prefix += "-" + cstate.incarnation
    return "%s-e%d-k%d:%s" % (prefix, cstate.episode, cstate.attempt, kind)


def link_of(host: str) -> str:
    """Client noi vao s1 (ditto/topology_spec.json)."""
    return "%s-s1" % host


def desired_bw(cstate: ControllerState, params: PolicyParams) -> dict:
    """Trang thai MONG MUON - dau vao cua vong reconcile o 8.4."""
    if cstate.mode in ("MITIGATING", "HOLD") and cstate.target and cstate.open_id:
        return {link_of(cstate.target): params.limit_mbps}
    return {}


# ---------------------------------------------------------------- bang chuyen


def decide(
    view: DetectorView,
    cstate: ControllerState,
    now_mono: float,
    params: PolicyParams,
) -> tuple[tuple[Action, ...], ControllerState]:
    label = classify(view)

    # ---------- HOLD: detector khong dang tin ----------
    if cstate.mode == "HOLD":
        if label == STALE:
            # Lich VAN THANG: go can thiep cua CHINH MINH la fail-safe, khong
            # phai "hanh dong moi" (N12 chi cam hanh dong moi). Neu khong go,
            # lease 120 s het han -> stale_intervention -> tinh huong xau hon.
            if (
                cstate.open_id
                and cstate.deadline_mono is not None
                and now_mono >= cstate.deadline_mono
            ):
                return _revert(view, cstate, now_mono, params, "hold_deadline_reached")
            return (), replace(cstate, reason="hold_stale")
        if cstate.open_id:                      # freshness tro lai, con can thiep mo
            return (), replace(
                cstate, mode="MITIGATING", mode_before_hold=None, reason="hold_resume"
            )
        return (), _idle(cstate, "hold_clear")

    if label == STALE:
        return (), replace(
            cstate, mode="HOLD", mode_before_hold=cstate.mode, reason="freshness_stale"
        )

    # ---------- MITIGATING ----------
    if cstate.mode == "MITIGATING":
        if label == STALE_INTERVENTION:         # N15: go cai dang mo, KHONG tao moi
            return _revert(view, cstate, now_mono, params, "n15_stale_intervention")
        if cstate.deadline_mono is not None and now_mono >= cstate.deadline_mono:
            return _revert(view, cstate, now_mono, params, "hold_expired")
        return (), replace(cstate, reason="holding")   # reconcile lo o 8.4

    # ---------- PROBING ----------
    if cstate.mode == "PROBING":
        if cstate.window_end_mono is not None and now_mono >= cstate.window_end_mono:
            return (), _idle(cstate, "probe_clean")    # probe THANH CONG -> reset k
        if label == ACT:
            loc = localize(view.affected, dict(view.roles))
            if loc.target is None:
                return (), replace(cstate, reason="probe_act_" + loc.reason)
            if loc.target != cstate.target:
                # thu pham doi -> bo nho backoff cu vo nghia -> fail-closed.
                # CACH LY probe_w_s giay: ung vien moi xuat hien NGAY sau khi go
                # gioi han rat co the la NAN NHAN dang recovery burst (8.1), khong
                # phai thu pham moi. Tai dung window_end_mono (IDLE von luon None)
                # de KHONG them truong vao ControllerState -> audit cu van dung
                # lai bit-exact (C10 lam hoi quy).
                quarantined = _idle(cstate, "probe_target_changed")
                return (), replace(
                    quarantined, window_end_mono=now_mono + params.probe_w_s
                )
            return _inject(
                view,
                replace(cstate, attempt=cstate.attempt + 1),
                now_mono,
                params,
                "probe_failed_backoff",
            )
        return (), replace(cstate, reason="probing")

    # ---------- IDLE ----------
    if cstate.window_end_mono is not None:  # dang cach ly sau doi muc tieu
        if now_mono < cstate.window_end_mono:
            return (), replace(cstate, reason="idle_quarantine")
        cstate = replace(cstate, window_end_mono=None)
    if label != ACT:
        return (), replace(cstate, reason="idle_" + label.lower())
    loc = localize(view.affected, dict(view.roles))
    if loc.target is None:
        return (), replace(cstate, reason="idle_" + loc.reason)
    return _inject(
        view,
        replace(cstate, episode=cstate.episode + 1, attempt=0, target=loc.target),
        now_mono,
        params,
        "act_localized",
    )


# ---------------------------------------------------------------- phat hanh dong


def _inject(view, cstate, now_mono, params, reason):
    iid = _iid(view, cstate, "inject")
    action = Action("inject", link_of(cstate.target), params.limit_mbps, iid, reason)
    return (action,), replace(
        cstate,
        mode="MITIGATING",
        open_id=iid,
        deadline_mono=now_mono + hold_seconds(params, cstate.attempt),
        window_end_mono=None,
        mode_before_hold=None,
        reason=reason,
    )


def _revert(view, cstate, now_mono, params, reason):
    iid = _iid(view, cstate, "revert")
    action = Action("revert", link_of(cstate.target), params.default_mbps, iid, reason)
    return (action,), replace(
        cstate,
        mode="PROBING",
        open_id=None,
        deadline_mono=None,
        window_end_mono=now_mono + params.probe_w_s,
        mode_before_hold=None,
        reason=reason,
    )


def _idle(cstate, reason):
    return replace(
        cstate,
        mode="IDLE",
        target=None,
        attempt=0,
        open_id=None,
        deadline_mono=None,
        window_end_mono=None,
        mode_before_hold=None,
        reason=reason,
    )
