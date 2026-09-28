"""M3 acceptance tests (SPEC §9 M3, §11 truncated-MLE recovery)."""
import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from floodcat.model import frequency, severity
from floodcat.utils.io import TABLES_DIR


def test_truncated_lognormal_mle_recovers_parameters():
    rng = np.random.default_rng(20261001)
    x = rng.lognormal(5.0, 1.2, 50_000)
    u0 = np.exp(5.0)
    kept = x[x > u0]
    fit = severity.fit_truncated("lognormal", kept, u0)
    assert fit["params"]["mu"] == pytest.approx(5.0, rel=0.03)
    assert fit["params"]["sigma"] == pytest.approx(1.2, rel=0.03)


def test_truncated_loglik_matches_definition():
    x = np.array([120.0, 150.0, 400.0, 2000.0])
    p = {"mu": 4.5, "sigma": 1.5}
    d = stats.lognorm(s=1.5, scale=np.exp(4.5))
    expected = sum(np.log(d.pdf(xi) / d.sf(100.0)) for xi in x)
    assert severity.trunc_loglik("lognormal", p, x, 100.0) == pytest.approx(expected, rel=1e-10)


def test_truncated_samples_above_u0_and_quantiles_consistent():
    rng = np.random.default_rng(1)
    p = {"shape_c": 1.5, "shape_d": 0.8, "scale": 300.0}
    s = severity.sample("burr12", p, 100.0, 20_000, rng)
    assert s.min() >= 100.0
    q = severity.cond_quantile("burr12", p, 100.0, np.array([0.5]))[0]
    assert np.mean(s <= q) == pytest.approx(0.5, abs=0.015)


def test_poisson_mle_is_sample_mean():
    counts = pd.Series([1, 0, 2, 1, 3, 0, 1], index=range(2009, 2016))
    fit = frequency.fit_frequency(counts, 2.71)
    assert fit.mean == pytest.approx(counts.mean())
    grid = np.linspace(0.5, 2.5, 2001)
    ll = [frequency.poisson_loglik(counts.values, g) for g in grid]
    assert grid[int(np.argmax(ll))] == pytest.approx(counts.mean(), abs=1e-3)


def test_nb_reduces_to_poisson_as_dispersion_vanishes():
    n = np.arange(0, 15)
    for r in (1e6, 1e8):
        np.testing.assert_allclose(frequency.nb_logpmf(n, 2.3, r), stats.poisson.logpmf(n, 2.3), atol=1e-4)


def test_nb_chosen_only_when_lr_exceeds_critical_value():
    under = pd.Series([1, 1, 1, 2, 1, 1, 2, 1], index=range(8))        # var < mean: Poisson boundary
    over = pd.Series([0, 0, 0, 6, 0, 1, 0, 7, 0, 0, 5, 0], index=range(12))
    f1 = frequency.fit_frequency(under, 2.71)
    f2 = frequency.fit_frequency(over, 2.71)
    assert f1.family == "poisson" and f1.lr_stat == 0.0
    assert f2.family == "negbin" and f2.lr_stat > 2.71


@pytest.mark.skipif(not (TABLES_DIR / "fits.json").exists(), reason="run `make model` first")
def test_chosen_family_recorded_with_rationale():
    fits = json.loads((TABLES_DIR / "fits.json").read_text())
    assert fits["severity"]["chosen"] in fits["severity"]["candidates"]
    assert fits["frequency"]["family"] in ("poisson", "negbin")
    assert len(fits["severity"]["rationale"]) > 20
