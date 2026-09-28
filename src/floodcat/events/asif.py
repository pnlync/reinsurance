"""As-if restatement to target-year exposure by state TIV ratio (SPEC §6.2)."""
from __future__ import annotations

import pandas as pd


def asif_factors(exposure: pd.DataFrame, target_year: int, tiv_col: str = "tiv_written") -> pd.DataFrame:
    """factor[s, t] = TIV[s, T] / TIV[s, t]; columns state, year, factor."""
    tiv = exposure.pivot(index="year", columns="state", values=tiv_col)
    f = tiv.loc[target_year] / tiv
    return f.stack().rename("factor").reset_index()


def restate(losses: pd.DataFrame, factors: pd.DataFrame, value_col: str = "loss") -> pd.Series:
    """Multiply losses (columns state, year, value_col) by factor[state, year]; returns the as-if values."""
    m = losses.merge(factors, on=["state", "year"], how="left", validate="many_to_one")
    if m["factor"].isna().any():
        missing = m.loc[m["factor"].isna(), ["state", "year"]].drop_duplicates().values.tolist()
        raise ValueError(f"no as-if factor for {missing}")
    return pd.Series(m[value_col].values * m["factor"].values, index=losses.index)


def cpi_factor(year: pd.Series, cpi: dict, target_year: int) -> pd.Series:
    """CPI-only factor CPI[T] / CPI[t] (sensitivity only)."""
    return year.map(lambda y: cpi[target_year] / cpi[int(y)])
