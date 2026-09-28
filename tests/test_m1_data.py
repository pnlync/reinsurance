"""M1 acceptance tests (SPEC §9 M1)."""
import json

import numpy as np
import pandas as pd
import pytest

from floodcat.data.claims import clean_claims
from floodcat.utils.io import PROCESSED_DIR, TABLES_DIR, load_config

needs_data = pytest.mark.skipif(not (PROCESSED_DIR / "exposure_by_state_year.parquet").exists(), reason="run `make data` first")


def test_clean_claims_rules_on_synthetic_rows():
    raw = pd.DataFrame({
        "id": ["1", "2", "2", "3", "4", "5"],
        "date_of_loss": ["2012-08-29T00:00:00.000Z", "2017-08-27T00:00:00.000Z", "2017-08-27T00:00:00.000Z", "", "2015-05-01T00:00:00.000Z", "2008-01-01T00:00:00.000Z"],
        "year_of_loss": ["2012", "2017", "2017", "2016", "2015", "2008"],
        "flood_event": ["Hurricane Isaac", "Hurricane Harvey", "Hurricane Harvey", "", "", ""],
        "state": ["LA", "TX", "TX", "LA", "FL", "FL"],
        "building_paid": ["100.5", "", "", "10", "-20", "1"],
        "contents_paid": ["50", "30", "30", "", "0", "1"],
        "icc_paid": ["", "0", "0", "0", "5", "1"],
        "building_coverage": ["1000", "200", "200", "100", "100", "100"],
        "contents_coverage": ["0", "0", "0", "0", "0", "0"],
    })
    clean, chk = clean_claims(raw, (2009, 2025))
    assert chk["exact_duplicates_dropped"] == 1
    assert chk["missing_state_or_date_excluded"] == 1
    assert chk["rows_outside_years"] == 1
    assert chk["negative_paid_rows"] == 1
    assert chk["null_paid"] == {"building_paid": 1, "contents_paid": 1, "icc_paid": 1}
    assert list(clean["id"]) == ["1", "2", "4"]
    np.testing.assert_allclose(clean["claim_loss"], [150.5, 30.0, -15.0])


@needs_data
def test_claim_loss_equals_sum_of_parts():
    c = pd.read_parquet(PROCESSED_DIR / "claims_clean.parquet")
    np.testing.assert_allclose(c["claim_loss"], c["building_paid"] + c["contents_paid"] + c["icc_paid"], rtol=0, atol=1e-9)
    assert set(c["state"]) <= set(load_config("portfolio")["states"])


@needs_data
def test_exposure_has_all_states_and_years():
    cfg = load_config("portfolio")
    e = pd.read_parquet(PROCESSED_DIR / "exposure_by_state_year.parquet")
    y0, y1 = cfg["history_years"]
    assert len(e) == len(cfg["states"]) * (y1 - y0 + 1)
    assert set(e["state"]) == set(cfg["states"])
    assert e["tiv_written"].notna().all() and (e["tiv_written"] > 0).all()


@needs_data
def test_written_vs_inforce_reported_2010_2025():
    e = pd.read_parquet(PROCESSED_DIR / "exposure_by_state_year.parquet")
    r = e[e["year"].between(2010, 2025)]["written_to_inforce"]
    assert r.notna().all() and (r > 0).all()


@needs_data
def test_national_2025_meets_crs_order_of_magnitude():
    crs = load_config("portfolio")["crs_check"]
    nat = json.loads((TABLES_DIR / "m1_checks.json").read_text())["national_inforce_2025"]
    assert abs(nat["policies"] / crs["ref_policies"] - 1) <= crs["tolerance"]
    assert abs(nat["tiv"] / crs["ref_coverage_usd"] - 1) <= crs["tolerance"]
