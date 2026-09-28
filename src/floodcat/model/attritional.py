"""Attritional annual loss A (SPEC §5.1, §9 M3): bootstrap of calibration as-if A_t (base), lognormal by moments (sensitivity)."""
from __future__ import annotations

import numpy as np


def lognormal_moments(a: np.ndarray) -> dict:
    """Lognormal matching the sample mean and variance of A_t."""
    m, v = float(np.mean(a)), float(np.var(a, ddof=1))
    s2 = np.log(1 + v / m ** 2)
    return {"mu": float(np.log(m) - s2 / 2), "sigma": float(np.sqrt(s2))}


def fit_attritional(a: np.ndarray) -> dict:
    a = np.asarray(a, dtype=float)
    return {"values": a.tolist(), "mean": float(a.mean()), "sd": float(a.std(ddof=1)), "lognormal": lognormal_moments(a)}


def sample_attritional(fit: dict, n_years: int, rng: np.random.Generator, method: str = "bootstrap") -> np.ndarray:
    if method == "bootstrap":
        return rng.choice(np.asarray(fit["values"]), size=n_years, replace=True)
    ln = fit["lognormal"]
    return rng.lognormal(ln["mu"], ln["sigma"], n_years)
