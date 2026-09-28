"""M4 acceptance tests (SPEC §9 M4, §11 risk measures)."""
import json

import numpy as np
import pandas as pd
import pytest

from floodcat.model.simulate import simulate
from floodcat.utils import risk_measures as rm
from floodcat.utils.io import PROCESSED_DIR, TABLES_DIR

needs_sim = pytest.mark.skipif(not (PROCESSED_DIR / "ylt.parquet").exists(), reason="run `make simulate` first")

TOY_FITS = {
    "u0": 100.0, "cap": 30_000.0,
    "frequency": {"family": "poisson", "mean": 1.4, "size": None},
    "severity": {"chosen": "lognormal", "params": {"mu": 5.0, "sigma": 1.5}},
    "attritional": {"values": [50.0, 80.0, 120.0], "lognormal": {"mu": 4.3, "sigma": 0.4}},
}


def test_risk_measures_golden():
    x = np.arange(1, 1001, dtype=float)
    assert rm.var(x, 0.995) == 995 and rm.tvar(x, 0.995) == 997.5
    assert rm.var(x, 0.99) == 990 and rm.tvar(x, 0.99) == 995
    np.random.default_rng(0).shuffle(x)
    assert rm.var(x, 0.995) == 995 and rm.tvar(x, 0.995) == 997.5


def test_simulation_structure_on_toy_fit():
    yelt, ylt = simulate(TOY_FITS, 50_000, 7)
    se = np.sqrt(1.4 / 50_000)
    assert abs(ylt["n_events"].mean() - 1.4) < 3 * se
    assert yelt["loss"].min() >= 100.0 and yelt["loss"].max() <= 30_000.0
    np.testing.assert_allclose(yelt.groupby("year_id")["loss"].sum().reindex(ylt["year_id"], fill_value=0).values, ylt["cat_total"].values)
    np.testing.assert_allclose(ylt["gross"], ylt["attritional"] + ylt["cat_total"])
    assert (ylt["max_event"] <= ylt["cat_total"] + 1e-9).all()
    # determinism
    _, ylt_b = simulate(TOY_FITS, 50_000, 7)
    assert ylt["gross"].equals(ylt_b["gross"])


@needs_sim
def test_simulated_counts_and_losses_against_fit():
    fits = json.loads((TABLES_DIR / "fits.json").read_text())
    ylt = pd.read_parquet(PROCESSED_DIR / "ylt.parquet")
    yelt = pd.read_parquet(PROCESSED_DIR / "yelt.parquet")
    n = ylt["n_events"]
    assert abs(n.mean() - fits["frequency"]["mean"]) < 3 * n.std(ddof=1) / np.sqrt(len(n))
    assert yelt["loss"].min() >= fits["u0"] - 1e-9 and yelt["loss"].max() <= fits["cap"] + 1e-9


@needs_sim
def test_oep_below_aep_and_convergence():
    ep = pd.read_csv(TABLES_DIR / "ep_curves.csv")
    assert (ep["oep"] <= ep["aep"] + 1e-9).all()
    conv = json.loads((TABLES_DIR / "convergence_gross.json").read_text())
    assert conv["within_tolerance"], conv
