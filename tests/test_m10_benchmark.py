"""M10 acceptance tests (SPEC §7, §9 M10)."""
from pathlib import Path

import pytest

from floodcat.validation.benchmark import cat_bonds, fema_placements

SRC = Path(__file__).resolve().parents[1] / "src" / "floodcat"


def test_fema_limits_and_rols_reproduce_spec():
    _, y = fema_placements()
    y = y.set_index("year")
    for year, limit, rol in ((2025, 757.8, 0.185), (2024, 619.5, 0.195), (2023, 502.5, 0.180), (2019, 1324, 0.140)):
        assert y.loc[year, "total_limit_usd_m"] == pytest.approx(limit, abs=0.05 if year != 2019 else 0.5)
        assert y.loc[year, "rol"] == pytest.approx(rol, abs=0.0005)


def test_cat_bond_multiples():
    c = cat_bonds().set_index(["series", "class"])
    assert c.loc[("2024-1", "A"), "multiple"] == pytest.approx(0.14 / 0.0501)
    assert 2.5 < c["multiple"].min() and c["multiple"].max() < 3.2


def test_benchmark_not_imported_by_model_code():
    offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
                 if p.name not in ("benchmark.py", "pipeline.py") and "benchmark" in p.read_text() and "import" in p.read_text()
                 and ("from floodcat.validation.benchmark" in p.read_text() or "validation import benchmark" in p.read_text())]
    assert offenders == []
