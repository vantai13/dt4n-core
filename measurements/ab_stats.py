#!/usr/bin/env python3
"""Thong ke cho A/B cua Lesson 8.6 - HAM THUAN, khong I/O, khong dong ho.

Hai nguyen tac:
  1. Bao DO LON kem DO BAT DINH (effect size + CI), khong bao p-value tran.
     Voi n du lon moi khac biet khac 0 deu "co y nghia"; mot controller cai
     thien 0.05 Mbps van co the p < 0.05 va van vo dung.
  2. Don vi lay mau lai la KHOI, khong phai luot: trong mot khoi cac luot dung
     chung dieu kien may (nhiet, RSS, qdisc) nen KHONG doc lap. Lay mau lai
     luot se coi quan sat phu thuoc thanh doc lap -> CI HEP GIA -> tu tin sai.
"""
from __future__ import annotations

import itertools
import random


def block_diffs(trials, key="primary", arm_a="A", arm_b="B"):
    """[mean(A trong khoi k) - mean(B trong khoi k)] theo thu tu khoi."""
    out = []
    for block in sorted({t["block"] for t in trials}):
        rows = [t for t in trials if t["block"] == block]
        a = [t[key] for t in rows if t["arm"] == arm_a and t[key] is not None]
        b = [t[key] for t in rows if t["arm"] == arm_b and t[key] is not None]
        if not a or not b:
            continue        # khoi khong du hai nhanh -> bo, va PHAI bao cao
        out.append(sum(a) / len(a) - sum(b) / len(b))
    return out


def bootstrap_ci(diffs, n_boot=10000, seed=20260920, alpha=0.05):
    """Bootstrap percentile tren KHOI. Tra (mean, lo, hi).

    Khong gia dinh phan phoi: goodput bi chan duoi boi 0, chan tren boi bang
    thong link, lech manh; moi kiem dinh dua tren gia dinh chuan deu mong manh
    o n nho.
    """
    if not diffs:
        return None, None, None
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * (n_boot - 1))]
    hi = means[int((1 - alpha / 2) * (n_boot - 1))]
    return sum(diffs) / n, lo, hi


def randomization_test(diffs, n_perm=20000, seed=20260920):
    """Kiem dinh hoan vi doi dau tren hieu theo khoi (two-sided).

    Co so: thu tu trong moi khoi la ABBA hoac BAAB do DONG XU CO SEED quyet
    dinh, nen duoi H0 nhan cua mot khoi doi duoc. Voi <= 20 khoi liet ke DU
    2^n to hop -> phep kiem CHINH XAC, dung ngay ca voi 5 khoi (khac han
    bootstrap percentile o n nho).
    """
    n = len(diffs)
    if n == 0:
        return None
    observed = abs(sum(diffs) / n)
    if n <= 20:
        total = 0
        hits = 0
        for signs in itertools.product((1, -1), repeat=n):
            total += 1
            value = sum(s * d for s, d in zip(signs, diffs)) / n
            if abs(value) >= observed - 1e-12:
                hits += 1
        return {"p_two_sided": hits / total, "exact": True, "n_perm": total}
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_perm):
        value = sum(d if rng.random() < 0.5 else -d for d in diffs) / n
        if abs(value) >= observed - 1e-12:
            hits += 1
    return {"p_two_sided": hits / n_perm, "exact": False, "n_perm": n_perm}


def summarise(trials, key="primary", arm_a="A", arm_b="B", **kwargs):
    """Goi du mot lan: hieu tho theo khoi + effect size + CI + hoan vi."""
    diffs = block_diffs(trials, key=key, arm_a=arm_a, arm_b=arm_b)
    mean, lo, hi = bootstrap_ci(diffs, **kwargs)
    caveat = None
    if 0 < len(diffs) < 8:
        caveat = ("bootstrap percentile voi %d khoi la THO: bien CI chi roi vao "
                  "mot tap huu han nho va do phu thuc te thuong < 95%%; doc "
                  "block_diffs va randomization_test truoc" % len(diffs))
    return {
        "n_blocks": len(diffs),
        # LUON in hieu tho: trung binh + CI khong bao gio thay the duoc du lieu.
        "block_diffs": [round(d, 4) for d in diffs],
        "mean_diff": None if mean is None else round(mean, 4),
        "ci95": [None, None] if mean is None else [round(lo, 4), round(hi, 4)],
        "ci95_excludes_zero": bool(mean is not None and (lo > 0 or hi < 0)),
        "randomization_test": randomization_test(diffs),
        "caveat": caveat,
    }
