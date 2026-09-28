"""Annual event frequency: Poisson vs Negative Binomial (SPEC §5.1, §9 M3).

NB is parameterised by mean mu and size r: Var(N) = mu + mu^2 / r; r -> infinity is Poisson.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import optimize, special, stats


def poisson_loglik(n: np.ndarray, lam: float) -> float:
    return float(stats.poisson.logpmf(n, lam).sum())


def nb_logpmf(n: np.ndarray, mu: float, r: float) -> np.ndarray:
    """log P(N = n) for NB(mean mu, size r), written out so r can be very large."""
    n = np.asarray(n, dtype=float)
    return (special.gammaln(n + r) - special.gammaln(r) - special.gammaln(n + 1)
            + r * np.log(r / (r + mu)) + n * np.log(mu / (r + mu)))


@dataclass
class FrequencyFit:
    family: str
    mean: float
    size: float | None          # NB size r (None for Poisson)
    loglik_poisson: float
    loglik_nb: float
    lr_stat: float
    dispersion_index: float
    n_years: int
    trend: dict
    nb_size: float | None = None   # NB MLE size r even when Poisson is chosen (inf on the Poisson boundary)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def fit_nb(n: np.ndarray) -> tuple[float, float, float]:
    """NB MLE: mu-hat is the sample mean; r maximises the profile likelihood. Returns (mu, r, loglik).

    If the sample variance does not exceed the mean the MLE sits on the Poisson boundary (r = inf)."""
    mu = float(np.mean(n))
    if np.var(n) <= mu:
        return mu, np.inf, poisson_loglik(n, mu)
    res = optimize.minimize_scalar(lambda lr: -nb_logpmf(n, mu, np.exp(lr)).sum(), bounds=(-6, 12), method="bounded")
    r = float(np.exp(res.x))
    return mu, r, float(nb_logpmf(n, mu, r).sum())


def poisson_trend(counts: pd.Series) -> dict:
    """Poisson GLM log E[N] = a + b (year - mean year); report only (SPEC §9 M3)."""
    x = sm.add_constant(counts.index.values - counts.index.values.mean())
    try:
        res = sm.GLM(counts.values, x, family=sm.families.Poisson()).fit()
        return {"slope_per_year": float(res.params[1]), "p_value": float(res.pvalues[1])}
    except Exception as exc:  # pragma: no cover - reported, never used
        return {"error": str(exc)}


def fit_frequency(counts: pd.Series, lr_critical: float) -> FrequencyFit:
    """counts: events per calibration year (index = year, zeros included)."""
    n = counts.values.astype(float)
    lam = float(n.mean())
    ll_p = poisson_loglik(n, lam)
    mu, r, ll_nb = fit_nb(n)
    lr = max(0.0, 2 * (ll_nb - ll_p))
    use_nb = lr > lr_critical
    return FrequencyFit(
        family="negbin" if use_nb else "poisson",
        mean=lam,
        size=r if use_nb else None,
        loglik_poisson=ll_p,
        loglik_nb=ll_nb,
        lr_stat=lr,
        dispersion_index=float(n.var(ddof=1) / lam) if lam > 0 else float("nan"),
        n_years=len(n),
        trend=poisson_trend(counts),
        nb_size=r,
    )


def sample_counts(fit: dict, n_years: int, rng: np.random.Generator, scale: float = 1.0) -> np.ndarray:
    """Draw annual event counts. `scale` multiplies the mean (freq stress); NB keeps its size r."""
    mean = fit["mean"] * scale
    if fit["family"] == "poisson":
        return rng.poisson(mean, n_years)
    r = fit["size"]
    return rng.negative_binomial(r, r / (r + mean), n_years)


def force_family(fit: FrequencyFit, family: str) -> FrequencyFit:
    """Keep a given family on a refit. NB on a sample with Var <= mean sits on the Poisson boundary, so it becomes Poisson."""
    if family == "negbin":
        r = fit_nb_size(fit)
        if np.isfinite(r):
            fit.family, fit.size = "negbin", r
            return fit
    fit.family, fit.size = "poisson", None
    return fit


def fit_nb_size(fit: FrequencyFit) -> float:
    return fit.nb_size if getattr(fit, "nb_size", None) is not None else np.inf
