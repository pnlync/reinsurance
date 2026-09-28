"""Exposure by state x year: written TIV (base) and year-end in-force TIV (check) (SPEC §6.1, M1).

v3 has no policy or term number, so an endorsement cannot be linked to its original record directly.
De-duplication rule (reports/data_checks.md, decision D7): records that share the same property and
term key (state, effective date, termination date, original new-business date, original construction
date, ZIP, rounded latitude/longitude, occupancy type, condominium code) are one policy term, and only
the record(s) with the latest endorsement date in that group are kept. Groups without endorsements
are untouched, so distinct policies on the same key are only merged when an endorsement shows that
one of them was superseded.
"""
from __future__ import annotations

import pandas as pd

from floodcat.data import load
from floodcat.utils.io import load_config

TERM_KEY = [
    "propertyState", "policyEffectiveDate", "policyTerminationDate", "originalNBDate",
    "originalConstructionDate", "reportedZipCode", "latitude", "longitude", "occupancyType",
    "condominiumCoverageTypeCode",
]


def _typed_policies_sql(states: list[str]) -> str:
    st = ", ".join(f"'{s}'" for s in states)
    return f"""
        SELECT *,
               CAST(substr(policyEffectiveDate, 1, 10) AS DATE)  AS eff,
               CAST(substr(policyTerminationDate, 1, 10) AS DATE) AS term,
               CAST(substr(coalesce(nullif(endorsementEffectiveDate, ''), policyEffectiveDate), 1, 10) AS DATE) AS endo,
               coalesce(try_cast(totalBuildingInsuranceCoverage AS DOUBLE), 0)
                 + coalesce(try_cast(totalContentsInsuranceCoverage AS DOUBLE), 0)      AS tiv,
               coalesce(try_cast(totalInsurancePremiumOfThePolicy AS DOUBLE), 0)       AS premium,
               coalesce(try_cast(policyCount AS DOUBLE), 0)                            AS pcount
        FROM {{policies}}
        WHERE propertyState IN ({st})
    """


def _dedup_sql(states: list[str]) -> str:
    key = ", ".join(TERM_KEY)
    return f"""
        SELECT * FROM ({_typed_policies_sql(states)})
        QUALIFY endo = max(endo) OVER (PARTITION BY {key})
    """


def written_exposure(states: list[str], years: tuple[int, int]) -> pd.DataFrame:
    """Written policies, TIV and premium by state x effective year, de-duplicated, plus the raw TIV."""
    y0, y1 = years
    agg = """propertyState AS state, year(eff) AS year, count(*) AS records, sum(pcount) AS policies,
             sum(tiv) AS tiv, sum(premium) AS premium"""
    where = f"WHERE year(eff) BETWEEN {y0} AND {y1} GROUP BY 1, 2"
    d = load.query(f"SELECT {agg} FROM ({_dedup_sql(states)}) {where}")
    a = load.query(f"SELECT {agg} FROM ({_typed_policies_sql(states)}) {where}")
    d = d.rename(columns={"records": "records_written", "policies": "policies_written", "tiv": "tiv_written", "premium": "premium_written"})
    a = a.rename(columns={"records": "records_all", "tiv": "tiv_written_all"})[["state", "year", "records_all", "tiv_written_all"]]
    return d.merge(a, on=["state", "year"], how="outer")


def inforce_exposure(states: list[str], years: tuple[int, int]) -> pd.DataFrame:
    """Policies and TIV in force at 31 December (effective <= d < termination), de-duplicated records."""
    y0, y1 = years
    cal = f"SELECT make_date(y, 12, 31) AS d FROM range({y0}, {y1 + 1}) t(y)"
    return load.query(f"""
        SELECT p.propertyState AS state, year(c.d) AS year, sum(p.pcount) AS policies_inforce, sum(p.tiv) AS tiv_inforce
        FROM ({_dedup_sql(states)}) p JOIN ({cal}) c ON p.eff <= c.d AND c.d < p.term
        GROUP BY 1, 2
    """)


def national_inforce_2025() -> dict:
    """All-state policies and TIV in force at 31 Dec 2025 (FEMA rule on raw records) for the CRS check."""
    r = load.query("""
        SELECT count(*) AS records, sum(coalesce(try_cast(policyCount AS DOUBLE), 0)) AS policies,
               sum(coalesce(try_cast(totalBuildingInsuranceCoverage AS DOUBLE), 0)
                   + coalesce(try_cast(totalContentsInsuranceCoverage AS DOUBLE), 0)) AS tiv
        FROM {national}
        WHERE CAST(substr(policyEffectiveDate, 1, 10) AS DATE) <= DATE '2025-12-31'
          AND CAST(substr(policyTerminationDate, 1, 10) AS DATE) > DATE '2025-12-31'
    """).iloc[0]
    return {k: float(v) for k, v in r.items()}


def build_exposure() -> pd.DataFrame:
    """State x year exposure table for the history years (SPEC §6.1)."""
    cfg = load_config("portfolio")
    states, years = cfg["states"], tuple(cfg["history_years"])
    w = written_exposure(states, years)
    i = inforce_exposure(states, years)
    grid = pd.MultiIndex.from_product([states, range(years[0], years[1] + 1)], names=["state", "year"]).to_frame(index=False)
    out = grid.merge(w, on=["state", "year"], how="left").merge(i, on=["state", "year"], how="left")
    out["written_to_inforce"] = out["tiv_written"] / out["tiv_inforce"]
    out["dedup_share_tiv"] = 1 - out["tiv_written"] / out["tiv_written_all"]
    return out


def endorsement_share(states: list[str]) -> float:
    """Share of policy records whose endorsement date is after the effective date."""
    return float(load.query(f"SELECT avg(CASE WHEN endo > eff THEN 1.0 ELSE 0.0 END) AS s FROM ({_typed_policies_sql(states)})").iloc[0, 0])
