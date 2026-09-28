"""Empirical risk measures exactly as defined in SPEC §4.3.

On a sample sorted ascending x_(1) <= ... <= x_(n):
    VaR_p  = x_(ceil(n p))
    TVaR_p = mean of { x_(i) : i >= ceil(n p) }
    EC     = VaR_0.995(L) - mean(L)
"""
from __future__ import annotations

import math

import numpy as np


def _k(n: int, p: float) -> int:
    """1-based index ceil(n p), guarded against floating-point noise (e.g. 1000 * 0.995)."""
    return max(1, min(n, math.ceil(round(n * p, 9))))


def var(x: np.ndarray, p: float) -> float:
    x = np.asarray(x, dtype=float)
    k = _k(len(x), p)
    return float(np.partition(x, k - 1)[k - 1])


def tvar(x: np.ndarray, p: float) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    k = _k(len(x), p)
    return float(x[k - 1:].mean())


def economic_capital(x: np.ndarray, p: float = 0.995) -> float:
    return var(x, p) - float(np.mean(x))


def exceedance_prob(x: np.ndarray, y: float) -> float:
    """Share of years with x > y (OEP if x is the annual maximum event, AEP if x is the annual loss)."""
    return float(np.mean(np.asarray(x) > y))


def return_level(x: np.ndarray, rp: float) -> float:
    """OEP^-1 / AEP^-1 at return period rp: VaR_(1 - 1/rp) (SPEC §4.3)."""
    return var(x, 1 - 1 / rp)
