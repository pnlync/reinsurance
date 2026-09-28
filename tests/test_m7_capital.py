"""M7 acceptance tests: SPEC §11 toy capital golden values."""
import numpy as np
import pytest

from floodcat.capital.metrics import net_annual_loss, programme_metrics
from floodcat.reinsurance.engine import apply_programme
from floodcat.reinsurance.pricing import price_layer
from floodcat.utils import risk_measures as rm
from toy import PRICING, programme, toy_table

ATOL = 1e-6


def test_toy_gross_net_and_capital_golden():
    t = toy_table()
    res = apply_programme(t, programme())
    lay = res["layers"]["L50x60"]
    prices = {"L50x60": price_layer(lay["recovery"], lay["f"], 50.0, **PRICING)}
    assert t.gross.mean() == pytest.approx(42.5) and rm.var(t.gross, 0.995) == 145
    assert rm.economic_capital(t.gross) == pytest.approx(102.5)
    net = net_annual_loss(t.gross, res["qs_recovery"], 0.0, res["layers"], prices, PRICING["rate"])
    np.testing.assert_allclose(net, [22.042735, 10.042735, 79.047009, 40.042735, 10.042735, 110.085470, 30.042735, 131.068376, 10.042735, 15.042735], atol=ATOL)
    m = programme_metrics(t.gross, net, None, res["layers"], prices, PRICING["rate"])
    assert m["net_mean"] == pytest.approx(45.75, abs=ATOL)
    assert m["net_var_995"] == pytest.approx(131.068376, abs=ATOL)
    assert m["ec_net"] == pytest.approx(85.318376, abs=ATOL)
    assert m["relief"] == pytest.approx(17.181624, abs=ATOL)
    assert m["relief_pct"] == pytest.approx(0.167626, abs=ATOL)
    assert m["implied_coc"] == pytest.approx(0.189156, abs=ATOL)
    assert m["net_cost"] == pytest.approx(3.25, abs=ATOL)


def test_no_reinsurance_gives_zero_relief_and_cost():
    t = toy_table()
    m = programme_metrics(t.gross, t.gross.copy(), None, {}, {}, 1.0)
    assert m["relief"] == 0 and m["net_cost"] == 0 and np.isnan(m["implied_coc"])


import json
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "outputs"


@pytest.mark.skipif(not (OUT / "tables/programme_metrics.csv").exists(), reason="run `make capital` first")
def test_grid_metrics():
    m = pd.read_csv(OUT / "tables/programme_metrics.csv").set_index("programme_id")
    assert m.loc["QS0_XS0", "relief"] == 0 and m.loc["QS0_XS0", "net_cost"] == 0
    assert (m.drop("QS0_XS0")["relief"] > 0).all()
    np.testing.assert_allclose(m["gross_ec"], m["gross_ec"].iloc[0])
    chk = json.loads((OUT / "tables/m7_checks.json").read_text())
    assert "limit_monotonicity_violations" in chk   # reported; only reinstatement premiums can cause them
    for v in chk["limit_monotonicity_violations"]:
        assert v["group"][3] > 0, v
    assert m["relief_approx"].notna().all()
