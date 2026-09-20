#!/usr/bin/env python3
"""Baseline tam thuong cho ablation 8.6 - HAM THUAN.

Cau hoi cua ablation: bao nhieu phan trong loi ich cua vong kin la nho DETECTOR
da hieu chuan, va bao nhieu phan mot luat nguong nam dong cung lam duoc?

Giu nguyen MOI thu khac (FSM circuit breaker, backoff, actuator, lease, audit,
reconcile); chi thay NGUON KICH HOAT:

    neu txRate cua mot client > X Mbps trong N_ACT tick lien tiep
    -> coi nhu "act", target = client do

X lay tu 8 run TRAIN qua tuong lua ml/operating_range.py::_assert_train_path.
KHONG duoc chinh X: chinh cho baseline thua la gian lan, chinh cho baseline
thang cung la gian lan.
"""
from __future__ import annotations

from dataclasses import dataclass

MBPS = 8.0 / 1e6          # txRate cua collector la Byte/s
N_ACT = 2                 # giong n_act cua detector-release-1.0.0 -> so sanh cong bang


@dataclass(frozen=True)
class ThresholdState:
    """Bo dem tick lien tiep cho tung client. frozen: cung ky luat voi policy."""

    streaks: tuple[tuple[str, int], ...] = ()

    def get(self, host: str) -> int:
        return dict(self.streaks).get(host, 0)


@dataclass(frozen=True)
class ThresholdVerdict:
    act: bool
    target: str | None
    state: ThresholdState
    tx_mbps: tuple[tuple[str, float], ...]


def client_tx_mbps(snapshot: dict) -> dict:
    """{client: txMbps} cho cac tick co rateValid; bo qua tick khong doc duoc."""
    out = {}
    for key, thing in (snapshot.get("things") or {}).items():
        if not key.startswith("host-"):
            continue
        attributes = thing.get("attributes") or {}
        if attributes.get("role") != "client":
            continue
        traffic = (thing.get("features") or {}).get("traffic") or {}
        if traffic.get("rateValid") is not True:
            continue
        value = traffic.get("txRate")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[key[len("host-"):]] = float(value) * MBPS
    return out


def step(snapshot: dict, state: ThresholdState, threshold_mbps: float,
         n_act: int = N_ACT) -> ThresholdVerdict:
    """Mot tick cua luat nguong. Thuan: khong doc dong ho, khong doc file."""
    rates = client_tx_mbps(snapshot)
    streaks = {}
    for host, value in rates.items():
        streaks[host] = state.get(host) + 1 if value > threshold_mbps else 0
    hot = sorted((host for host, n in streaks.items() if n >= n_act),
                 key=lambda h: (-rates[h], h))
    new_state = ThresholdState(tuple(sorted(streaks.items())))
    # >= 2 ung vien: fail-closed GIONG luat v2, de ablation chi khac dung MOT
    # thu (nguon kich hoat), khong khac ca chinh sach xu ly mo ho.
    target = hot[0] if len(hot) == 1 else None
    return ThresholdVerdict(bool(hot), target, new_state,
                            tuple(sorted(rates.items())))


def threshold_from_train(paths) -> dict:
    """Tran tai hop le tren DUNG 8 run train, qua tuong lua train-only."""
    from ml import campaign as C
    from ml import operating_range as O

    paths = list(paths)
    run_ids = [O._assert_train_path(path) for path in paths]
    if sorted(run_ids) != sorted(O.TRAIN_RUN_IDS):
        raise O.FirewallError("phai dung du va dung 8 run train, khong chon loc")
    best, owner = -1.0, None
    for run_id, path in zip(run_ids, paths):
        for index, snapshot in enumerate(C.read_snapshots(path)):
            for host, value in client_tx_mbps(snapshot).items():
                if value > best:
                    best, owner = value, {"run_id": run_id, "tick": index,
                                          "host": host}
    return {"threshold_mbps": best, "owner": owner, "n_runs": len(paths)}
