"""Stress tests and optional sensitivities on the fixed contract grid (SPEC §5.4, §9 M9)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from floodcat.events import catalogue
from floodcat.model.fit import calibration_data, fit_all
from floodcat.utils.io import PROCESSED_DIR, load_config
from floodcat.validation.backtest import base_families
from floodcat.validation.scenario import evaluate_scenario, row, simulate_table

PRICING_KEYS = {"coc_r", "diversification_d"}


def run_stresses(base_fits: dict, base_rec: str) -> tuple[pd.DataFrame, dict]:
    sim = load_config("simulation")
    scen = load_config("stress")["scenarios"]
    t, mx = simulate_table(base_fits, sim["n_years"], sim["seed"])
    base = evaluate_scenario(t, mx)
    rows = [row("base", base, base_rec)]
    results = {"base": base}
    for name, s in scen.items():
        if "hurdle" in s:
            res = evaluate_scenario(t, mx, hurdle=s["hurdle"])
        elif set(s) <= PRICING_KEYS:
            res = evaluate_scenario(t, mx, pricing_overrides=s)
        else:
            kw = {}
            if "frequency_scale" in s:
                kw["frequency_scale"] = s["frequency_scale"]
            if "severity_scale" in s:
                kw["severity_scale"] = s["severity_scale"]
            if s.get("tail") == "gpd_above_median":
                g = dict(base_fits["gpd"]["tail_stress"])
                g["xi"] = g["xi"] + s["xi_shift"]
                kw["tail_gpd"] = g
            ts, mxs = simulate_table(base_fits, sim["n_years"], sim["seed"], **kw)
            res = evaluate_scenario(ts, mxs)
        rows.append(row(name, res, base_rec))
        results[name] = res
    return pd.DataFrame(rows), results


def run_sensitivities(base_fits: dict, base_rec: str) -> pd.DataFrame:
    """Optional sensitivities (SPEC §9 M9): u0 = 250m, CPI-only as-if, calibration from 2010, lognormal attritional."""
    port = load_config("portfolio")
    mod = load_config("modelling")
    sim = load_config("simulation")
    fam = base_families(base_fits)
    claims = pd.read_parquet(PROCESSED_DIR / "claims_clean.parquet")
    exposure = pd.read_parquet(PROCESSED_DIR / "exposure_by_state_year.parquet")
    rows = []

    def go(name: str, data: dict, mod_: dict, **kw):
        fits = fit_all(data, mod_, force=fam)
        t, mx = simulate_table(fits, sim["n_years"], sim["seed"], **kw)
        r = row(name, evaluate_scenario(t, mx), base_rec)
        r["n_events_calib"] = fits["n_events"]
        rows.append(r)

    u0s = mod["event_threshold_sensitivity"]
    ev, att, _ = catalogue.build(claims, exposure, u0=u0s)
    go(f"u0_{u0s}", calibration_data(catalogue=(ev, att)), {**mod, "event_threshold_u0": u0s})

    ev, att, _ = catalogue.build(claims, exposure)
    ev_c = ev.copy()
    ev_c["loss_asif"] = ev_c["loss_cpi"]
    ev_c["included"] = ev_c["loss_asif"] >= mod["event_threshold_u0"]
    # sub-threshold events move to attritional on the CPI basis
    att_c = att.copy()
    moved = ev_c[ev["included"] & ~ev_c["included"]].groupby("year")["loss_cpi"].sum()
    back = ev_c[~ev["included"] & ev_c["included"]].groupby("year")["loss_cpi"].sum()
    att_c["a_asif"] = att_c["a_cpi"] + att_c["year"].map(moved).fillna(0) - att_c["year"].map(back).fillna(0)
    go("cpi_only", calibration_data(catalogue=(ev_c, att_c)), mod)

    if port["calibration"]["start"] < 2010:
        go("calibration_from_2010", calibration_data(fit_years=(2010, port["calibration"]["end"])), mod)

    go("attritional_lognormal", calibration_data(), mod, attritional_method="lognormal")

    # D14: the 1-in-200 sits at the event cap, so test the two assumptions behind it
    fits_ln = fit_all(calibration_data(), mod, force={**fam, "severity": "lognormal"})
    t, mx = simulate_table(fits_ln, sim["n_years"], sim["seed"])
    r = row("severity_lognormal", evaluate_scenario(t, mx), base_rec)
    r["n_events_calib"] = fits_ln["n_events"]
    rows.append(r)
    fits_cap = {**base_fits, "cap": 5.0 * base_fits["largest_event"]}
    t, mx = simulate_table(fits_cap, sim["n_years"], sim["seed"])
    rows.append(row("event_cap_5x", evaluate_scenario(t, mx), base_rec))
    # D15: no reinsurer diversification (d = 1)
    t, mx = simulate_table(base_fits, sim["n_years"], sim["seed"])
    rows.append(row("d_10", evaluate_scenario(t, mx, pricing_overrides={"diversification_d": 1.0}), base_rec))
    return pd.DataFrame(rows)
