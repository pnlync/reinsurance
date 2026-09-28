"""M5 acceptance tests: identities and SPEC §11 golden values."""
import json
from pathlib import Path

import numpy as np
import pytest

from floodcat.reinsurance.cat_xol import apply_cat_xol, event_recovery
from floodcat.reinsurance.engine import apply_programme
from floodcat.reinsurance.quota_share import apply_quota_share
from toy import N_YEARS, programme, toy_table

ATOL = 1e-6


def test_toy_recoveries_and_reinstated_fraction():
    res = apply_programme(toy_table(), programme())["layers"]["L50x60"]
    np.testing.assert_allclose(res["recovery"], [0, 0, 5, 0, 0, 50, 0, 30, 0, 0], atol=ATOL)
    np.testing.assert_allclose(res["f"], [0, 0, 0.1, 0, 0, 1, 0, 0.6, 0, 0], atol=ATOL)
    assert res["recovery"].mean() == pytest.approx(8.5, abs=ATOL)   # burning cost


def test_toy_variants():
    t = toy_table()
    r0 = apply_programme(t, programme(n=0))["layers"]["L50x60"]
    np.testing.assert_allclose(r0["recovery"], [0, 0, 5, 0, 0, 50, 0, 30, 0, 0], atol=ATOL)
    r8 = apply_programme(t, programme(c=0.8))["layers"]["L50x60"]
    np.testing.assert_allclose(r8["recovery"], [0, 0, 4, 0, 0, 40, 0, 24, 0, 0], atol=ATOL)
    np.testing.assert_allclose(r8["f"], [0, 0, 0.1, 0, 0, 1, 0, 0.6, 0, 0], atol=ATOL)
    rq = apply_programme(t, programme(q=0.2))
    np.testing.assert_allclose(rq["qs_recovery"], 0.2 * t.gross, atol=ATOL)
    assert rq["qs_recovery"].mean() == pytest.approx(8.5, abs=ATOL)
    np.testing.assert_allclose(rq["layers"]["L50x60"]["recovery"], [0, 0, 0, 0, 0, 50, 0, 12, 0, 0], atol=ATOL)
    assert rq["layers"]["L50x60"]["recovery"].mean() == pytest.approx(6.2, abs=ATOL)


@pytest.mark.parametrize("events, n, R, f", [([140, 100], 0, 50, 0), ([140, 100], 1, 90, 1), ([140, 140, 140], 1, 100, 1)])
def test_annual_cap(events, n, R, f):
    res = apply_cat_xol(np.array(events, float), np.zeros(len(events), np.int64), 1, 60.0, 50.0, 1.0, n)
    assert res["recovery"][0] == pytest.approx(R, abs=ATOL) and res["f"][0] == pytest.approx(f, abs=ATOL)


def test_identities_on_random_events():
    rng = np.random.default_rng(3)
    s = rng.lognormal(4, 1.5, 20_000)
    yid = rng.integers(0, 5_000, 20_000)
    A, L, c = 80.0, 200.0, 0.8
    r = event_recovery(s, A, L, c)
    assert (r >= 0).all() and (r <= np.minimum(s, c * L) + 1e-12).all()
    assert (r[s <= A] == 0).all()
    np.testing.assert_allclose(r[s >= A + L], c * L)
    for n in (0, 1):
        R = apply_cat_xol(s, yid, 5_000, A, L, c, n)["recovery"]
        assert (R <= (1 + n) * c * L + 1e-9).all()
    np.testing.assert_allclose(apply_quota_share(s, 0.1), 0.1 * s)


def test_capped_event_recovery_consumes_cap_in_order():
    from floodcat.reinsurance.cat_xol import capped_event_recovery
    s = np.array([140, 140, 140, 65, 8, 90, 55], float)
    y = np.array([0, 0, 0, 1, 1, 2, 2])
    r = capped_event_recovery(s, y, 60, 50, 1.0, 1)
    np.testing.assert_allclose(r, [50, 50, 0, 5, 0, 30, 0])
    tot = apply_cat_xol(s, y, 3, 60, 50, 1.0, 1)["recovery"]
    np.testing.assert_allclose(np.bincount(y, weights=r), tot)


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "outputs/tables/excel_check.json").exists(), reason="run `make engine` first")
def test_excel_matches_python_within_001_percent():
    r = json.loads((Path(__file__).resolve().parents[1] / "outputs/tables/excel_check.json").read_text())
    assert r["pass"] and r["max_rel_diff"] <= 1e-4 and r["n_cells"] > 50
