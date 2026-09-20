#!/usr/bin/env python3
"""Mo phong su kien roi rac cua vong kin Phase 8 (Lesson 8.2).

Noi decide() THUAN voi mot mo hinh plant + mot mo hinh sensor. MOI hang so
thoi gian deu trich dan receipt - khong bia con so nao (xem docstring field).

Muc dich: co DU DOAN niem phong truoc khi do live (C6, C12, va can cho C3),
va quet duoc duong cong danh doi T0/T_max/W ma live khong the lam noi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from controller.policy import (
    ControllerState,
    DetectorView,
    PolicyParams,
    decide,
)

TICK_S = 1.0   # bridge/detector_contract.py::TICK_INTERVAL_MS = 1000

ROLES = (
    ("h1", "client"), ("h2", "client"), ("h3", "client"),
    ("srv1", "server"), ("srv2", "server"),
)
CULPRIT = "h1"
CULPRIT_THING = "org.dt4n:host-h1"


@dataclass(frozen=True)
class SimParams:
    """Tham so mo hinh. Moi dong mot receipt."""

    # --- sensor: models/detector-release-1.0.0.json -> content.fsm_params
    n_act: int = 2
    release_m: int = 3
    cooldown_s: float = 8.0
    # --- sensor: results/report/phase7_e2e_latency.json -> layers.phys_obs
    #     p95 = 1432.619 ms; nhanh lac quan dung p50 = 1158.573 ms
    d_obs_s: float = 1.433
    # --- actuator: results/report/latency_command_randomized.json
    #     p95 = 984.190 ms (p50 = 674.703 ms)
    d_cmd_s: float = 0.984
    # --- F8-6: setBandwidth dung lai qdisc -> bo dem ve 0 -> 1 tick unknown
    tick_unknown_after_tc: int = 1
    # --- an so 9.3 cua Lesson 8.2: detector bao gi trong luc dang gioi han.
    #     Thiet ke KHONG phu thuoc vao cau tra loi (go theo lich), nhung sim
    #     chay ca hai kich ban de bao cao hai cot du doan. 8.3 se dong an so.
    suppressed_during_mitigation: bool = True


@dataclass
class SimResult:
    n_actions: int = 0
    n_mitigations: int = 0
    n_reverts: int = 0
    harm_s: float = 0.0         # flood chay ma KHONG bi gioi han
    blind_s: float = 0.0        # co can thiep mo HOAC trong cooldown sau revert
    flood_s: float = 0.0        # tong thoi gian flood
    total_s: float = 0.0
    max_open_s: float = 0.0     # khoang giu dai nhat (phai < MAX_OPEN_S)
    timeline: list = field(default_factory=list)

    @property
    def harm_fraction(self) -> float:
        return self.harm_s / self.flood_s if self.flood_s else 0.0

    @property
    def blind_fraction(self) -> float:
        return self.blind_s / self.total_s if self.total_s else 0.0

    def as_dict(self) -> dict:
        return {
            "n_actions": self.n_actions,
            "n_mitigations": self.n_mitigations,
            "n_reverts": self.n_reverts,
            "harm_s": round(self.harm_s, 3),
            "blind_s": round(self.blind_s, 3),
            "flood_s": round(self.flood_s, 3),
            "total_s": round(self.total_s, 3),
            "max_open_s": round(self.max_open_s, 3),
            "harm_fraction": round(self.harm_fraction, 4),
            "blind_fraction": round(self.blind_fraction, 4),
        }


def run(flood_schedule, horizon_s, policy_params=None, sim_params=None,
        keep_timeline=True) -> SimResult:
    """flood_schedule: ham t -> bool, flood co dang chay tai thoi diem t.

    Ham nay tat dinh: khong random ben trong. Ngau nhien (neu can) nam o ham
    sinh flood_schedule ben ngoai, de moi ket qua tai lap duoc tu seed.
    """
    policy_params = policy_params or PolicyParams()
    sim_params = sim_params or SimParams()

    cstate = ControllerState()
    result = SimResult(total_s=float(horizon_s))

    limited = False             # tc dang gioi han?
    pending = []                # [(t_hieu_luc, kind)] lenh da gui, chua co hieu luc
    cooldown_until = float("-inf")
    open_since = None
    consec_act = 0
    unknown_ticks = 0
    history = {}                # t -> (flooding, limited) de mo phong tre quan sat

    t = 0.0
    while t < horizon_s:
        # 1) plant: ap dung cac lenh da den han
        for item in list(pending):
            if t >= item[0]:
                limited = item[1] == "inject"
                pending.remove(item)
                unknown_ticks = sim_params.tick_unknown_after_tc

        flooding = bool(flood_schedule(t))
        history[round(t, 3)] = (flooding, limited)

        if flooding:
            result.flood_s += TICK_S
            if not limited:
                result.harm_s += TICK_S
        suppressed = open_since is not None or t < cooldown_until
        if suppressed:
            result.blind_s += TICK_S
        if open_since is not None:
            result.max_open_s = max(result.max_open_s, t - open_since)

        # 2) sensor: tin hieu tho (tre d_obs) -> state cong bo
        t_obs = round(t - sim_params.d_obs_s, 3)
        past = history.get(t_obs)
        if past is None:
            # lam tron ve tick gan nhat da co
            keys = [k for k in history if k <= t_obs]
            past = history[max(keys)] if keys else (False, False)
        raw_alarm = past[0] and not past[1]

        if unknown_ticks > 0:
            unknown_ticks -= 1
            state, cause = "unknown", "missing_data"
            consec_act = 0
        elif suppressed and (raw_alarm or sim_params.suppressed_during_mitigation):
            state, cause = "unknown", "suppressed_intervention"
            consec_act = 0
        elif raw_alarm:
            consec_act += 1
            state = "act" if consec_act >= sim_params.n_act else "suspect"
            cause = ""
        else:
            consec_act = 0
            state, cause = "normal", ""

        view = DetectorView(
            state=state,
            cause=cause,
            affected=((CULPRIT_THING,) if state == "act" else ()),
            roles=ROLES,
            fresh=True,
            boot_id="sim",
            seq=int(t / TICK_S),
        )

        # 3) controller
        actions, cstate = decide(view, cstate, t, policy_params)
        for action in actions:
            result.n_actions += 1
            pending.append((t + sim_params.d_cmd_s, action.kind))
            if action.kind == "inject":
                result.n_mitigations += 1
                open_since = t
            else:
                result.n_reverts += 1
                cooldown_until = t + sim_params.cooldown_s
                if open_since is not None:
                    result.max_open_s = max(result.max_open_s, t - open_since)
                open_since = None
            if keep_timeline:
                result.timeline.append(
                    (round(t, 2), action.kind, action.reason, cstate.attempt)
                )

        t = round(t + TICK_S, 3)
    return result


# ---------------------------------------------------------------- lich flood


def always(_t: float) -> bool:
    return True


def never(_t: float) -> bool:
    return False


def window(t_start: float, t_end: float):
    return lambda t: t_start <= t < t_end


def poisson_schedule(seed: int, horizon_s: float, rate_per_hour: float = 6.0,
                     mean_duration_s: float = 120.0):
    """Sinh cac khoang flood theo qua trinh Poisson; TAT DINH theo seed.

    Ngau nhien nam O DAY, khong nam trong run(): mot seed -> mot lich -> mot
    ket qua, tai lap duoc.
    """
    import random  # noqa: PLC0415 - chi dung de SINH lich, khong nam trong vong

    rng = random.Random(seed)
    spans, t = [], 0.0
    while t < horizon_s:
        t += rng.expovariate(rate_per_hour / 3600.0)
        if t >= horizon_s:
            break
        duration = rng.expovariate(1.0 / mean_duration_s)
        spans.append((t, min(t + duration, horizon_s)))
        t += duration
    def schedule(now, spans=tuple(spans)):
        return any(a <= now < b for a, b in spans)
    return schedule, spans


# ---------------------------------------------------------------- doi chung


def run_bangbang(flood_schedule, horizon_s, sim_params=None,
                 limit_mbps=7.0) -> SimResult:
    """Doi chung: 'bat khi act, tat khi detector bao khoe' - khong circuit breaker.

    Dung de tinh cai gia cua plan goc bang chinh mo hinh nay, thay vi so sanh
    mot con so mo phong voi mot con so tuong tuong.
    """
    sim_params = sim_params or SimParams()
    result = SimResult(total_s=float(horizon_s))

    limited = False
    pending = []
    cooldown_until = float("-inf")
    open_since = None
    consec_act = 0
    quiet_ticks = 0
    unknown_ticks = 0
    in_act = False
    history = {}

    t = 0.0
    while t < horizon_s:
        for item in list(pending):
            if t >= item[0]:
                limited = item[1] == "inject"
                pending.remove(item)
                unknown_ticks = sim_params.tick_unknown_after_tc

        flooding = bool(flood_schedule(t))
        history[round(t, 3)] = (flooding, limited)
        if flooding:
            result.flood_s += TICK_S
            if not limited:
                result.harm_s += TICK_S
        suppressed = open_since is not None or t < cooldown_until
        if suppressed:
            result.blind_s += TICK_S
        if open_since is not None:
            result.max_open_s = max(result.max_open_s, t - open_since)

        t_obs = round(t - sim_params.d_obs_s, 3)
        keys = [k for k in history if k <= t_obs]
        past = history[max(keys)] if keys else (False, False)
        raw_alarm = past[0] and not past[1]

        if unknown_ticks > 0:
            unknown_ticks -= 1
            alarming = None
            unknown_ticks_state = True
        else:
            alarming = raw_alarm and not suppressed
            unknown_ticks_state = False

        if unknown_ticks_state:
            pass
        elif alarming:
            consec_act += 1
            quiet_ticks = 0
            if consec_act >= sim_params.n_act:
                in_act = True
        else:
            consec_act = 0
            quiet_ticks += 1
            if in_act and quiet_ticks >= sim_params.release_m:
                in_act = False

        # luat bang-bang: bat khi act, tat khi roi act
        if in_act and open_since is None:
            result.n_actions += 1
            result.n_mitigations += 1
            pending.append((t + sim_params.d_cmd_s, "inject"))
            open_since = t
            result.timeline.append((round(t, 2), "inject", "bangbang_act", 0))
        elif (not in_act) and open_since is not None:
            result.n_actions += 1
            result.n_reverts += 1
            pending.append((t + sim_params.d_cmd_s, "revert"))
            cooldown_until = t + sim_params.cooldown_s
            open_since = None
            result.timeline.append((round(t, 2), "revert", "bangbang_quiet", 0))

        t = round(t + TICK_S, 3)
    return result
