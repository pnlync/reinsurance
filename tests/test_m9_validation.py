"""M9 acceptance tests (SPEC §9 M9)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

OUT = Path(__file__).resolve().parents[1] / "outputs"
PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
needs_val = pytest.mark.skipif(not (OUT / "tables/validation_summary.json").exists(), reason="run `make validate` first")


@pytest.mark.skipif(not (PROC / "event_catalogue.parquet").exists(), reason="run `make events` first")
def test_bootstrap_resamples_whole_years():
    from floodcat.model.fit import calibration_data
    base = calibration_data()
    ev = base["events"]
    years = [2017, 2017, 2010, 2022, 2016]
    d = calibration_data(year_sample=years)
    # every sampled year brings all of its events and its own attritional loss, and nothing else
    expected = np.concatenate([ev.loc[ev["year"] == y, "loss_asif"].values for y in years])
    np.testing.assert_allclose(d["severities"], expected)
    assert list(d["counts"].values) == [int((ev["year"] == y).sum()) for y in years]
    att = pd.read_parquet(PROC / "attritional_by_year.parquet").set_index("year")["a_asif"]
    np.testing.assert_allclose(d["attritional"], [att[y] for y in years])


@needs_val
def test_stresses_reuse_base_contracts():
    from floodcat.capital.run import load_programmes
    from floodcat.validation.scenario import evaluate_scenario  # noqa: F401  (loads the same programmes.csv)
    progs = load_programmes()
    p = pd.read_csv(OUT / "tables/programmes.csv")
    assert [x.programme_id for x in progs] == list(p["programme_id"])
    st = pd.read_csv(OUT / "tables/recommendation_stability.csv")
    assert set(st["balanced_id"]) <= set(p["programme_id"])


@needs_val
def test_base_row_reproduces_m8():
    st = pd.read_csv(OUT / "tables/recommendation_stability.csv").set_index("scenario")
    rec = json.loads((OUT / "recommendation.json").read_text())["recommended"]
    assert st.loc["base", "balanced_id"] == rec["programme_id"]
    assert st.loc["base", "relief"] == pytest.approx(rec["relief"], rel=1e-9)
    assert st.loc["base", "implied_coc"] == pytest.approx(rec["implied_coc"], rel=1e-9)
    s = json.loads((OUT / "tables/validation_summary.json").read_text())
    assert s["base_row_matches_m8"] and s["stress_total"] == 9
    assert s["convergence_recommended"]["within_tolerance"]
    ci = pd.read_csv(OUT / "tables/bootstrap_ci.csv").set_index("metric")
    assert (ci["p05"] <= ci["median"]).all() and (ci["median"] <= ci["p95"]).all()
