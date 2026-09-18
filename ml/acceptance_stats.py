"""Thong ke cho lan nghiem thu 6R.7. Ham thuan tuy: khong doc file, khong in."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

SEP_FLOOR = 1e-3
TICK_S = 1.0


def poisson_upper_one_sided(k: int, alpha: float = 0.05) -> float:
    """Can tren mot phia: lambda sao cho P(X <= k; lambda) = alpha."""
    if k < 0:
        raise ValueError("k phai >= 0")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha phai nam trong (0, 1)")

    def cdf(lam: float) -> float:
        term = total = math.exp(-lam)
        for i in range(1, k + 1):
            term *= lam / i
            total += term
        return total

    lo, hi = 0.0, max(10.0, 10.0 * (k + 1))
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def false_alarm_rate_upper(
    n_events: int, at_risk_ticks: int, alpha: float = 0.05
) -> dict:
    """Tinh S2 (can tren event/gio) va S3 (can duoi MTBFA) tu cung phep do."""
    if at_risk_ticks <= 0:
        raise ValueError("exposure = 0: khong co gi de uoc luong")
    hours = at_risk_ticks * TICK_S / 3600.0
    rate_upper = poisson_upper_one_sided(n_events, alpha) / hours
    return {
        "n_events": n_events,
        "at_risk_ticks": at_risk_ticks,
        "exposure_hours": hours,
        "rate_point_per_hour": n_events / hours,
        "rate_upper_per_hour": rate_upper,
        "mtbfa_lower_minutes": 60.0 / rate_upper,
        "alpha_one_sided": alpha,
    }


@dataclass(frozen=True)
class DosePoint:
    run_id: str
    separation: float
    detected: bool


def _log_sep(value: float) -> tuple[float, bool]:
    if value is None or not math.isfinite(value):
        raise ValueError("separation khong huu han")
    return math.log10(max(value, SEP_FLOOR)), value < SEP_FLOOR


def dose_bracket(points: list[DosePoint]) -> dict:
    """Fallback ED50: noi suy log neu don dieu; khong uoc luong neu chong lan."""
    hits = sorted(p.separation for p in points if p.detected)
    misses = sorted(p.separation for p in points if not p.detected)
    base = {
        "n_points": len(points),
        "n_hits": len(hits),
        "n_misses": len(misses),
        "n_floored": sum(_log_sep(p.separation)[1] for p in points),
    }
    if not hits or not misses:
        return {
            **base,
            "kind": "censored_all_hit" if hits else "censored_all_miss",
            "bracket": None,
            "ed50": None,
            "monotone": None,
        }
    lo, hi = max(misses), min(hits)
    if lo < hi:
        mid = (_log_sep(lo)[0] + _log_sep(hi)[0]) / 2
        return {
            **base,
            "kind": "bracket",
            "monotone": True,
            "bracket": [lo, hi],
            "ed50": 10**mid,
        }
    inversions = sum(1 for miss in misses for hit in hits if miss >= hit)
    return {
        **base,
        "kind": "overlap",
        "monotone": False,
        "bracket": [hi, lo],
        "ed50": None,
        "n_inversions": inversions,
    }


def logistic_fit(x, y, max_iter: int = 100) -> dict:
    """MLE logistic hai tham so, khong regularization va fail-closed."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.size == 0 or x.shape != y.shape:
        return {"converged": False, "why": "invalid_shape"}
    if y.min() == y.max():
        return {"converged": False, "why": "degenerate_one_class"}
    design = np.column_stack([np.ones_like(x), x])
    beta = np.zeros(2)
    for _ in range(max_iter):
        probability = 1 / (1 + np.exp(-np.clip(design @ beta, -35, 35)))
        weight = probability * (1 - probability)
        if weight.min() < 1e-10:
            return {"converged": False, "why": "separation_p_at_0_or_1"}
        try:
            step = np.linalg.solve(
                design.T @ (design * weight[:, None]),
                design.T @ (y - probability),
            )
        except np.linalg.LinAlgError:
            return {"converged": False, "why": "singular_hessian"}
        beta = beta + step
        if np.abs(beta).max() > 1e3:
            return {"converged": False, "why": "beta_diverged"}
        if np.abs(step).max() < 1e-10:
            if beta[1] <= 0:
                return {"converged": False, "why": "non_increasing_slope"}
            log_ed50 = -beta[0] / beta[1]
            if not (x.min() - 1.0 <= log_ed50 <= x.max() + 1.0):
                return {"converged": False, "why": "ed50_extrapolated"}
            return {
                "converged": True,
                "b0": float(beta[0]),
                "b1": float(beta[1]),
                "ed50": float(10**log_ed50),
            }
    return {"converged": False, "why": "max_iter"}


def bootstrap_ed50(
    points,
    *,
    n_boot=2000,
    seed=20260918,
    min_converged_fraction=0.5,
) -> dict:
    """Bootstrap theo run va dung fallback da dang ky khi logistic khong hoi tu."""
    if not points:
        raise ValueError("can it nhat mot dose point")
    x = np.array([_log_sep(point.separation)[0] for point in points])
    y = np.array([1.0 if point.detected else 0.0 for point in points])
    point_fit = logistic_fit(x, y)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(n_boot):
        indexes = rng.integers(0, len(points), len(points))
        fit = logistic_fit(x[indexes], y[indexes])
        if fit["converged"]:
            estimates.append(fit["ed50"])
    out = {
        "n_boot": n_boot,
        "seed": seed,
        "n_converged": len(estimates),
        "point_fit": point_fit,
        "fallback": dose_bracket(points),
    }
    if len(estimates) / n_boot <= min_converged_fraction or not point_fit["converged"]:
        return {
            **out,
            "method": "interpolation_fallback",
            "ed50": out["fallback"]["ed50"],
            "ci95": None,
        }
    lo, hi = np.percentile(estimates, [2.5, 97.5])
    return {
        **out,
        "method": "logistic",
        "ed50": point_fit["ed50"],
        "ci95": [float(lo), float(hi)],
    }
