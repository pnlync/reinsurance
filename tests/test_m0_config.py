"""M0 acceptance tests (SPEC §9 M0)."""
import copy
from pathlib import Path

import pytest

from floodcat.utils.io import CONFIG_NAMES, ConfigError, _VALIDATORS, load_config, valid_layer_pairs

SRC = Path(__file__).resolve().parents[1] / "src" / "floodcat"


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_configs_load_and_validate(name):
    assert isinstance(load_config(name), dict)


def test_spec_values():
    sim = load_config("simulation")
    assert sim["n_years"] == 100_000 and sim["seed"] == 20261001 and sim["n_batches"] == 20
    ri = load_config("reinsurance")
    assert ri["pricing"]["coc_r"] == 0.10 and ri["pricing"]["diversification_d"] == 0.5
    assert ri["pricing"]["xol_expense"] == 0.10 and ri["pricing"]["qs_expense"] == 0.03
    assert ri["decision"]["budget_min_relief"] == 0.25
    port = load_config("portfolio")
    assert port["states"] == ["FL", "TX", "LA", "MS", "AL"] and port["target_year"] == 2025


def test_layer_pairs_filter_exhaustion_above_attachment():
    ri = load_config("reinsurance")
    pairs = valid_layer_pairs(ri)
    assert all(e > a for a, e in pairs)
    assert (50, 50) not in pairs and (10, 50) in pairs
    assert len(pairs) == 4 * 4 - 1  # only (50, 50) is dropped


@pytest.mark.parametrize(
    "name, path, bad",
    [
        ("reinsurance", ("quota_share",), [0.0, 1.5]),
        ("reinsurance", ("placement",), [0.0]),
        ("reinsurance", ("reinstatements",), [-1]),
        ("reinsurance", ("pricing", "coc_r"), 1.2),
        ("simulation", ("n_years",), 100_001),
        ("portfolio", ("calibration", "end"), 2030),
        ("modelling", ("event_threshold_u0",), -5),
    ],
)
def test_invalid_values_rejected(name, path, bad):
    cfg = copy.deepcopy(load_config(name))
    node = cfg
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = bad
    with pytest.raises(ConfigError):
        _VALIDATORS[name](cfg)


def test_only_load_reads_raw_data():
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if p.name != "load.py" and "data/raw" in p.read_text()
    ]
    assert offenders == []
