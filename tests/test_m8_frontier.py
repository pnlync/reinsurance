"""M8 acceptance tests: SPEC §11 frontier golden test."""
import numpy as np
import pandas as pd
import pytest

from floodcat.capital.frontier import choices, dominated

PTS = pd.DataFrame({
    "programme_id": ["P0", "P1", "P2", "P3", "P4", "P5"],
    "net_cost": [0, 1.2, 3.0, 2.9, 4.0, 4.6],
    "ec_net": [100, 80, 85, 60, 50, 47],
})
PTS["relief"] = 100 - PTS["ec_net"]
PTS["relief_pct"] = PTS["relief"] / 100
PTS["implied_coc"] = PTS["net_cost"] / PTS["relief"].replace(0, np.nan)


def test_frontier_golden():
    assert list(PTS.loc[dominated(PTS), "programme_id"]) == ["P2"]
    ch = choices(PTS, "P0", [0.08, 0.10, 0.12], 0.25)
    assert list(ch["frontier"]["programme_id"]) == ["P0", "P1", "P3", "P4", "P5"]
    assert list(ch["hull"]["programme_id"]) == ["P0", "P1", "P3", "P4", "P5"]
    np.testing.assert_allclose(ch["hull"]["marginal_coc"].iloc[1:], [0.06, 0.085, 0.11, 0.20], atol=1e-9)
    assert ch["balanced"] == {0.08: "P1", 0.10: "P3", 0.12: "P4"}
    assert ch["budget_first"] == "P3"
    assert ch["protection_first"] == "P5"
    assert PTS.set_index("programme_id").loc["P3", "implied_coc"] == pytest.approx(0.0725)


def test_frontier_ec_strictly_decreasing():
    rng = np.random.default_rng(5)
    df = pd.DataFrame({"programme_id": [f"X{i}" for i in range(300)], "net_cost": rng.uniform(0, 10, 300), "ec_net": rng.uniform(40, 100, 300)})
    df.loc[0, ["net_cost", "ec_net"]] = [0, 100]
    df["relief_pct"] = (100 - df["ec_net"]) / 100
    ch = choices(df, "X0", [0.1], 0.25)
    f = ch["frontier"]
    assert (np.diff(f["net_cost"]) > 0).all() and (np.diff(f["ec_net"]) < 0).all()
    ids = set(f["programme_id"])
    assert ch["budget_first"] in ids and ch["protection_first"] in ids and ch["balanced"][0.1] in ids


import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "outputs"


@pytest.mark.skipif(not (OUT / "recommendation.json").exists(), reason="run `make frontier` first")
def test_real_frontier_and_choices():
    f = pd.read_csv(OUT / "tables/frontier.csv")
    assert (np.diff(f["net_cost"]) > 0).all() and (np.diff(f["ec_net"]) < 0).all()
    rec = json.loads((OUT / "recommendation.json").read_text())
    ids = set(f["programme_id"])
    ch = rec["choices"]
    assert ch["budget_first"] in ids and ch["protection_first"] in ids
    assert all(pid in ids for pid in ch["balanced"].values())
    assert rec["recommended"]["programme_id"] == ch["balanced"]["0.10"]
    p = pd.read_csv(OUT / "tables/programmes.csv")
    for i in (1, 2):
        sub = p[p[f"layer{i}_id"].notna()]
        assert (sub[f"layer{i}_exhaust"] > sub[f"layer{i}_attach"]).all()
        assert (sub[f"layer{i}_exhaust_rp"] > sub[f"layer{i}_attach_rp"]).all()
