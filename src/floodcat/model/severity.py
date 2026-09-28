"""Event severity: left-truncated MLE at u0 for lognormal, log-logistic (Fisk) and Burr XII (SPEC §5.1, §9 M3).

Events are only recorded when S >= u0, so each family is fitted to the conditional density
    f(s) / (1 - F(u0)),   loglik = sum_e [ log f(S_e) - log(1 - F(u0)) ]
written out below rather than using scipy's untruncated `fit`.
"""
from __future__ import annotations

import numpy as np
from scipy import optimize, stats

PARAM_NAMES = {
    "lognormal": ["mu", "sigma"],
    "loglogistic": ["shape_c", "scale"],
    "burr12": ["shape_c", "shape_d", "scale"],
}


def dist(family: str, p: dict):
    """Frozen scipy distribution for a parameter dict."""
    if family == "lognormal":
        return stats.lognorm(s=p["sigma"], scale=np.exp(p["mu"]))
    if family == "loglogistic":
        return stats.fisk(c=p["shape_c"], scale=p["scale"])
    if family == "burr12":
        return stats.burr12(c=p["shape_c"], d=p["shape_d"], scale=p["scale"])
    raise ValueError(family)


def _unpack(family: str, theta: np.ndarray) -> dict:
    """Free (unbounded) parameters -> natural parameters (positive ones on the log scale)."""
    if family == "lognormal":
        return {"mu": theta[0], "sigma": np.exp(theta[1])}
    return {k: np.exp(t) for k, t in zip(PARAM_NAMES[family], theta)}


def _start(family: str, x: np.ndarray) -> np.ndarray:
    lx = np.log(x)
    m, s = lx.mean(), max(lx.std(), 0.1)
    c = np.pi / (s * np.sqrt(3))
    return {
        "lognormal": np.array([m, np.log(s)]),
        "loglogistic": np.array([np.log(c), m]),
        "burr12": np.array([np.log(c), 0.0, m]),
    }[family]


def trunc_loglik(family: str, p: dict, x: np.ndarray, u0: float) -> float:
    d = dist(family, p)
    return float(np.sum(d.logpdf(x)) - len(x) * d.logsf(u0))


def fit_truncated(family: str, x: np.ndarray, u0: float) -> dict:
    """Left-truncated MLE. BFGS from several starts, then a Nelder-Mead polish of the best; returns params, loglik, AIC, BIC."""
    x = np.asarray(x, dtype=float)
    if (x < u0).any():
        raise ValueError("observations below the truncation point")

    def nll(theta):
        if np.any(np.abs(theta) > 50):
            return 1e300
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):   # optimiser probes where logsf = -inf
            v = -trunc_loglik(family, _unpack(family, theta), x, u0)
        return v if np.isfinite(v) else 1e300

    base = _start(family, x)
    best = None
    for shift in ([0] * len(base), [-1] + [0] * (len(base) - 1), [0] + [0.5] * (len(base) - 1), [0] + [-0.5] * (len(base) - 1)):
        r = optimize.minimize(nll, base + np.array(shift, dtype=float), method="BFGS")
        if best is None or r.fun < best.fun:
            best = r
    polish = optimize.minimize(nll, best.x, method="Nelder-Mead", options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 20000})
    if polish.fun <= best.fun:
        best = polish
    p = {k: float(v) for k, v in _unpack(family, best.x).items()}
    ll = -float(best.fun)
    k, n = len(p), len(x)
    return {"family": family, "params": p, "loglik": ll, "k": k, "n": n,
            "aic": 2 * k - 2 * ll, "bic": k * np.log(n) - 2 * ll,
            "converged": bool(best.success),
            "at_boundary": bool(np.any(np.abs(best.x) > 40))}   # e.g. Burr XII drifting to its Weibull limit


def cond_isf(family: str, p: dict, u0: float, q: np.ndarray) -> np.ndarray:
    """Level exceeded with probability q given S > u0 (conditional inverse survival function)."""
    d = dist(family, p)
    return d.isf(np.asarray(q) * d.sf(u0))


def cond_isf_inverse(family: str, p: dict, u0: float, x: np.ndarray) -> np.ndarray:
    """P(S > x | S > u0)."""
    d = dist(family, p)
    return d.sf(np.asarray(x)) / d.sf(u0)


def cond_quantile(family: str, p: dict, u0: float, prob: np.ndarray) -> np.ndarray:
    return cond_isf(family, p, u0, 1 - np.asarray(prob))


def sample(family: str, p: dict, u0: float, size: int, rng: np.random.Generator) -> np.ndarray:
    """Draws from the fitted severity truncated below at u0 (inverse survival function)."""
    return cond_isf(family, p, u0, rng.uniform(0, 1, size))


def plotting_positions(n: int) -> np.ndarray:
    """Weibull positions i / (n + 1) for the ascending sample."""
    return np.arange(1, n + 1) / (n + 1)


def mean_finite(family: str, p: dict) -> bool:
    if family == "lognormal":
        return True
    if family == "loglogistic":
        return p["shape_c"] > 1
    return p["shape_c"] * p["shape_d"] > 1


# ---------------------------------------------------------------- GPD diagnostics and tail stress

def mean_excess(x: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    return np.array([np.mean(x[x > u] - u) if (x > u).sum() > 0 else np.nan for u in thresholds])


def fit_gpd(x: np.ndarray, threshold: float) -> dict:
    """GPD MLE for excesses over `threshold` (location fixed at 0)."""
    y = x[x > threshold] - threshold
    xi, _, beta = stats.genpareto.fit(y, floc=0)
    return {"threshold": float(threshold), "xi": float(xi), "beta": float(beta), "n_exceed": int(len(y))}


def sample_body_gpd(family: str, p: dict, u0: float, gpd: dict, size: int, rng: np.random.Generator) -> np.ndarray:
    """Tail stress (SPEC §5.4 tail_heavy): fitted severity between u0 and m, GPD(xi, beta) above m.

    P(S > m | S > u0) is kept from the fitted severity, so only the shape above m changes."""
    d = dist(family, p)
    m = gpd["threshold"]
    s0, sm_ = d.sf(u0), d.sf(m)
    p_tail = sm_ / s0
    u = rng.uniform(0, 1, size)
    out = np.empty(size)
    tail = u < p_tail
    v = rng.uniform(0, 1, size)
    out[~tail] = d.isf(s0 - v[~tail] * (s0 - sm_))
    out[tail] = m + stats.genpareto.ppf(v[tail], gpd["xi"], scale=gpd["beta"])
    return out
