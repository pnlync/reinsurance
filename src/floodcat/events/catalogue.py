"""Historical event catalogue and attritional series on the 2025 as-if basis (SPEC §6.2, M2).

Every claim gets an assigned year t: the event year (calendar year of the event's earliest date of loss)
for claims with a `floodEvent` label, otherwise the claim's own year. Each claim is restated with
factor[state, t], so event and attritional totals add up to the restated total per year exactly.
Money from here on is in USD m (decision D3).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from floodcat.events.asif import asif_factors, cpi_factor, restate
from floodcat.utils.io import load_config

USD_M = 1e6


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def period_of(year: int, port: dict) -> str:
    cal = port["calibration"]
    if cal["start"] <= year <= cal["end"]:
        return "calibration"
    if year in port["holdout"]["years"]:
        return "holdout"
    return "excluded"


def assign_claims(claims: pd.DataFrame, exposure: pd.DataFrame, port: dict) -> pd.DataFrame:
    """Claim-level event label, assigned year and as-if loss (USD m)."""
    c = claims[["id", "state", "date_of_loss", "year", "flood_event", "claim_loss"]].copy()
    c["labelled"] = c["flood_event"] != ""
    first = c[c["labelled"]].groupby("flood_event")["date_of_loss"].min().dt.year
    c["t"] = np.where(c["labelled"], c["flood_event"].map(first), c["year"]).astype(int)
    c["loss_nominal"] = c["claim_loss"] / USD_M
    f = asif_factors(exposure, port["target_year"])
    c["loss_asif"] = restate(c.rename(columns={"t": "year", "year": "claim_year"})[["state", "year", "loss_nominal"]], f, "loss_nominal")
    c["loss_cpi"] = c["loss_nominal"] * cpi_factor(c["t"], port["cpi_u_annual"], port["target_year"])
    return c


def build_events(c: pd.DataFrame, port: dict, u0: float, named_storm_overrides: dict) -> pd.DataFrame:
    """One row per `floodEvent` label (SPEC §9 M2 column list)."""
    ev = c[c["labelled"]]
    g = ev.groupby("flood_event")
    out = pd.DataFrame({
        "name": g.size().index,
        "year": g["t"].first().values,
        "first_date": g["date_of_loss"].min().values,
        "last_date": g["date_of_loss"].max().values,
        "n_claims": g.size().values,
    })
    out["span_days"] = (out["last_date"] - out["first_date"]).dt.days
    pat = re.compile(r"hurricane|tropical storm", re.I)
    out["named_storm"] = [named_storm_overrides.get(n, bool(pat.search(n))) for n in out["name"]]
    for kind in ("nominal", "asif"):
        by_state = ev.pivot_table(index="flood_event", columns="state", values=f"loss_{kind}", aggfunc="sum", fill_value=0.0)
        for s in port["states"]:
            out[f"loss_{kind}_{s}"] = out["name"].map(by_state[s] if s in by_state else {}).fillna(0.0).values
    out["loss_nominal"] = out[[f"loss_nominal_{s}" for s in port["states"]]].sum(axis=1)
    out["loss_cpi"] = out["name"].map(g["loss_cpi"].sum())
    out["loss_asif"] = out[[f"loss_asif_{s}" for s in port["states"]]].sum(axis=1)
    out["included"] = out["loss_asif"] >= u0
    out["period"] = [period_of(y, port) for y in out["year"]]
    out["event_id"] = [f"{y}_{_slug(n)}" for y, n in zip(out["year"], out["name"])]
    cols = ["event_id", "name", "year", "first_date", "last_date", "span_days", "n_claims", "named_storm"]
    cols += [f"loss_nominal_{s}" for s in port["states"]] + [f"loss_asif_{s}" for s in port["states"]]
    cols += ["loss_nominal", "loss_cpi", "loss_asif", "included", "period"]
    return out[cols].sort_values(["year", "first_date"]).reset_index(drop=True)


def build_attritional(c: pd.DataFrame, events: pd.DataFrame, port: dict) -> pd.DataFrame:
    """A_t: non-event claims plus sub-threshold event claims, by assigned year (USD m)."""
    included = set(events.loc[events["included"], "name"])
    att = c[~c["flood_event"].isin(included)]
    y0, y1 = port["history_years"]
    years = pd.Index(range(y0, y1 + 1), name="year")
    g = att.groupby("t")
    out = pd.DataFrame({
        "a_nominal": g["loss_nominal"].sum().reindex(years, fill_value=0.0),
        "a_cpi": g["loss_cpi"].sum().reindex(years, fill_value=0.0),
        "a_asif": g["loss_asif"].sum().reindex(years, fill_value=0.0),
    }).reset_index()
    out["period"] = [period_of(y, port) for y in out["year"]]
    return out


def build(claims: pd.DataFrame, exposure: pd.DataFrame, u0: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (event catalogue, attritional by year, claim assignment)."""
    port = load_config("portfolio")
    mod = load_config("modelling")
    u0 = mod["event_threshold_u0"] if u0 is None else u0
    c = assign_claims(claims, exposure, port)
    events = build_events(c, port, u0, mod.get("named_storm_overrides", {}))
    att = build_attritional(c, events, port)
    included = set(events.loc[events["included"], "name"])
    c["bucket"] = np.where(c["flood_event"].isin(included), "event", "attritional")
    return events, att, c
