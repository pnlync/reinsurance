"""M6 acceptance tests: SPEC §11 toy pricing golden values and pricing properties."""
import numpy as np
import pytest

from floodcat.reinsurance.engine import apply_programme
from floodcat.reinsurance.pricing import layer_probabilities, price_layer
from toy import PRICING, programme, toy_max_event, toy_table

ATOL = 1e-6


def toy_price(n=1, c=1.0, **over):
    res = apply_programme(toy_table(), programme(c=c, n=n))["layers"]["L50x60"]
    return price_layer(res["recovery"], res["f"], c * 50.0, **{**PRICING, **over})


def test_toy_pricing_golden():
    p = toy_price()
    assert p["el"] == pytest.approx(8.5, abs=ATOL)
    assert p["tvar995"] == pytest.approx(50, abs=ATOL)
    assert p["k_r"] == pytest.approx(41.5, abs=ATOL)
    assert p["capital_charge"] == pytest.approx(2.075, abs=ATOL)
    assert p["target"] == pytest.approx(11.75, abs=ATOL)
    assert p["mean_f"] == pytest.approx(0.17, abs=ATOL)
    assert p["premium"] == pytest.approx(10.042735, abs=ATOL)
    assert p["rol"] == pytest.approx(0.200855, abs=ATOL)
    assert p["multiple"] == pytest.approx(1.382353, abs=ATOL)
    assert p["net_cost"] == pytest.approx(3.25, abs=ATOL)
    pr = layer_probabilities(toy_max_event(), 0.0, 60.0, 110.0)
    assert pr["ap"] == pytest.approx(0.3) and pr["ep"] == pytest.approx(0.1)


def test_no_reinstatement_reduces_to_simple_formula():
    p = toy_price(n=0)
    assert p["premium"] == pytest.approx(11.75, abs=ATOL)
    assert p["premium"] == pytest.approx((p["el"] + p["capital_charge"]) / (1 - PRICING["expense"]), abs=ATOL)


def test_net_cost_identity_and_premium_above_el():
    for n in (0, 1):
        for c in (0.8, 1.0):
            p = toy_price(n=n, c=c)
            assert p["premium"] + p["exp_reinst_premium"] >= p["el"]
            assert p["net_cost"] == pytest.approx(PRICING["expense"] * p["target"] + PRICING["coc_r"] * PRICING["d"] * p["k_r"], abs=ATOL)


def test_rol_and_multiple_monotone_on_synthetic_layers():
    rng = np.random.default_rng(11)
    n_years = 200_000
    n = rng.poisson(1.5, n_years)
    s = np.exp(rng.normal(5, 1.2, n.sum()))
    yid = np.repeat(np.arange(n_years), n)
    from floodcat.reinsurance.cat_xol import apply_cat_xol
    exhaust = 3000.0
    rols, mults = [], []
    for a in (200, 400, 800, 1500):
        r = apply_cat_xol(s, yid, n_years, a, exhaust - a, 1.0, 1)
        p = price_layer(r["recovery"], r["f"], exhaust - a, **PRICING)
        rols.append(p["rol"]); mults.append(p["multiple"])
    assert all(np.diff(rols) < 0), rols
    assert all(np.diff(mults) > 0), mults


from pathlib import Path

import pandas as pd

LP = Path(__file__).resolve().parents[1] / "outputs/tables/layer_pricing.csv"


@pytest.mark.skipif(not LP.exists(), reason="run `make pricing` first")
def test_grid_pricing_properties():
    lp = pd.read_csv(LP)
    assert (lp["premium"] + lp["exp_reinst_premium"] >= lp["el"] - 1e-9).all()
    # ROL decreasing in attachment for fixed exhaustion, and multiple increasing as AP falls
    for _, g in lp.groupby(["q", "exhaust_rp", "c", "n_reinst"]):
        g = g.sort_values("attach")
        assert (np.diff(g["rol"]) < 0).all(), g[["layer_id", "rol"]]
    for _, g in lp.groupby(["q", "exhaust_rp", "c", "n_reinst"]):
        g = g.sort_values("ap", ascending=False)
        assert (np.diff(g["multiple"]) > 0).all(), g[["layer_id", "multiple"]]
    np.testing.assert_allclose(lp["net_cost"], 0.10 * (lp["premium"] + lp["exp_reinst_premium"]) + 0.10 * 0.5 * lp["k_r"], rtol=1e-9)
