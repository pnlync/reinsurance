"""M2 acceptance tests (SPEC §9 M2, §11 as-if toy)."""
import numpy as np
import pandas as pd
import pytest

from floodcat.events.asif import asif_factors, restate
from floodcat.utils.io import PROCESSED_DIR, load_config

needs_data = pytest.mark.skipif(not (PROCESSED_DIR / "event_catalogue.parquet").exists(), reason="run `make events` first")


def test_asif_toy():
    exposure = pd.DataFrame({
        "state": ["TX", "TX", "LA", "LA"], "year": [2012, 2025, 2012, 2025], "tiv_written": [200.0, 300.0, 100.0, 80.0],
    })
    f = asif_factors(exposure, 2025)
    losses = pd.DataFrame({"state": ["TX", "LA"], "year": [2012, 2012], "loss": [100.0, 50.0]})
    s = restate(losses, f)
    assert s.tolist() == pytest.approx([150.0, 40.0], abs=1e-6)
    assert s.sum() == pytest.approx(190.0, abs=1e-6)


def test_factor_is_one_in_target_year():
    exposure = pd.read_parquet(PROCESSED_DIR / "exposure_by_state_year.parquet") if (PROCESSED_DIR / "exposure_by_state_year.parquet").exists() else pytest.skip("run `make data` first")
    f = asif_factors(exposure, load_config("portfolio")["target_year"])
    assert np.allclose(f.loc[f["year"] == 2025, "factor"], 1.0)


@needs_data
def test_state_losses_sum_to_total():
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    states = load_config("portfolio")["states"]
    for kind in ("nominal", "asif"):
        np.testing.assert_allclose(ev[[f"loss_{kind}_{s}" for s in states]].sum(axis=1), ev[f"loss_{kind}"], rtol=1e-12)
    np.testing.assert_allclose(ev.loc[ev["year"] == 2025, "loss_asif"], ev.loc[ev["year"] == 2025, "loss_nominal"], rtol=1e-12)


@needs_data
def test_every_claim_in_exactly_one_bucket_and_totals_reconcile():
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet").set_index("year")
    asg = pd.read_parquet(PROCESSED_DIR / "claim_assignment.parquet")
    claims = pd.read_parquet(PROCESSED_DIR / "claims_clean.parquet")
    assert len(asg) == len(claims) and asg["id"].is_unique
    assert set(asg["bucket"]) <= {"event", "attritional"}
    included = set(ev.loc[ev["included"], "name"])
    assert (asg["bucket"].eq("event") == asg["flood_event"].isin(included)).all()
    inc = ev[ev["included"]].groupby("year")[["loss_nominal", "loss_asif"]].sum()
    tot = asg.groupby("t")[["loss_nominal", "loss_asif"]].sum()
    for kind, a in (("nominal", "a_nominal"), ("asif", "a_asif")):
        lhs = inc[f"loss_{kind}"].reindex(tot.index, fill_value=0) + att[a].reindex(tot.index)
        np.testing.assert_allclose(lhs, tot[f"loss_{kind}"], rtol=1e-9)
