"""Claims cleaning and data checks (SPEC §4.3, §9 M1)."""
from __future__ import annotations

import pandas as pd

from floodcat.data import load
from floodcat.utils.io import load_config

PAID = ["building_paid", "contents_paid", "icc_paid"]


def read_raw_claims() -> pd.DataFrame:
    """Claims in the portfolio states with SPEC column names; text fields kept as text, money as float."""
    f = load_config("fields")["claims"]["fields"]
    states = load_config("portfolio")["states"]
    st = ", ".join(f"'{s}'" for s in states)
    cols = ", ".join(f'"{v}" AS {k}' for k, v in f.items())
    df = load.query(f"SELECT {cols} FROM {{claims}} WHERE {f['state']} IN ({st})")
    return df


def clean_claims(raw: pd.DataFrame, years: tuple[int, int]) -> tuple[pd.DataFrame, dict]:
    """Apply the SPEC §4.3 claim-loss convention and the M1 check table. Returns (clean, checks)."""
    df = raw.copy()
    checks: dict = {"rows_raw": len(df)}

    # key uniqueness: drop exact duplicates only
    dup_ids = int(df["id"].duplicated(keep=False).sum())
    exact = int(df.duplicated(keep="first").sum())
    df = df.drop_duplicates(keep="first")
    checks["duplicate_id_rows"] = dup_ids
    checks["exact_duplicates_dropped"] = exact

    # paid fields: blank/null -> 0 (counted), negatives flagged and kept
    nulls = {}
    for c in PAID:
        x = pd.to_numeric(df[c].replace("", None), errors="coerce")
        nulls[c] = int(x.isna().sum())
        df[c] = x.fillna(0.0)
    checks["null_paid"] = nulls
    df["negative_paid"] = (df[PAID] < 0).any(axis=1)
    checks["negative_paid_rows"] = int(df["negative_paid"].sum())
    df["claim_loss"] = df["building_paid"] + df["contents_paid"] + df["icc_paid"]

    for c in ("building_coverage", "contents_coverage"):
        df[c] = pd.to_numeric(df[c].replace("", None), errors="coerce")

    # missing state / date: exclude and report
    df["date_of_loss"] = pd.to_datetime(df["date_of_loss"].replace("", None), errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    missing = df["state"].isin(["", None]) | df["date_of_loss"].isna()
    checks["missing_state_or_date_excluded"] = int(missing.sum())
    df = df[~missing].copy()

    df["year"] = df["date_of_loss"].dt.year.astype(int)
    yol = pd.to_numeric(df["year_of_loss"], errors="coerce")
    checks["year_of_loss_mismatch"] = int((yol != df["year"]).sum())
    df["flood_event"] = df["flood_event"].fillna("").str.strip()

    y0, y1 = years
    checks["rows_outside_years"] = int((~df["year"].between(y0, y1)).sum())
    df = df[df["year"].between(y0, y1)].copy()

    # checks by year
    by = df.groupby("year")
    at_limit = (df["building_coverage"] > 0) & (df["building_paid"] >= 0.99 * df["building_coverage"])
    checks["by_year"] = pd.DataFrame({
        "records": by.size(),
        "zero_claim_loss": by["claim_loss"].apply(lambda s: int((s == 0).sum())),
        "event_labelled": by["flood_event"].apply(lambda s: int((s != "").sum())),
        "at_limit_share": at_limit.groupby(df["year"]).mean(),
        "claim_loss_usd_m": by["claim_loss"].sum() / 1e6,
    })
    checks["rows_clean"] = len(df)

    keep = ["id", "state", "date_of_loss", "year", "flood_event", *PAID, "claim_loss",
            "building_coverage", "contents_coverage", "negative_paid"]
    return df[keep].reset_index(drop=True), checks
