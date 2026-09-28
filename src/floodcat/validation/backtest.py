"""Temporal holdout and leave-one-major-event-out (SPEC §9 M9)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from floodcat.model.fit import calibration_data, fit_all
from floodcat.model.simulate import simulate
from floodcat.utils import risk_measures as rm
from floodcat.utils.io import PROCESSED_DIR, load_config
from floodcat.validation.scenario import evaluate_scenario, row, simulate_table


def base_families(fits: dict) -> dict:
    return {"frequency": fits["frequency"]["family"], "severity": fits["severity"]["chosen"]}


def observed_years(years: list[int]) -> pd.DataFrame:
    """As-if event count, annual loss and largest event for given years (events >= u0 only)."""
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet").set_index("year")
    inc = ev[ev["included"]]
    rows = []
    for y in years:
        e = inc[inc["year"] == y]
        rows.append({"year": y, "n_events": len(e), "annual_loss": float(att.loc[y, "a_asif"] + e["loss_asif"].sum()),
                     "largest_event": float(e["loss_asif"].max()) if len(e) else 0.0,
                     "largest_event_name": e.sort_values("loss_asif").iloc[-1]["name"] if len(e) else ""})
    return pd.DataFrame(rows)


def mid_percentile(sample: np.ndarray, x: float) -> float:
    return float(np.mean(sample < x) + 0.5 * np.mean(sample == x))


def holdout(base_fits: dict) -> pd.DataFrame:
    port = load_config("portfolio")
    mod = load_config("modelling")
    sim = load_config("simulation")
    fit_years = tuple(port["backtest"]["fit"])
    t0, t1 = port["backtest"]["test"]
    fits = fit_all(calibration_data(fit_years=fit_years), mod, force=base_families(base_fits))
    _, ylt = simulate(fits, sim["n_years"], sim["seed"], run=10)
    n = ylt["n_events"].to_numpy()
    k = t1 - t0 + 1
    sums = n[: len(n) // k * k].reshape(-1, k).sum(axis=1)
    test = observed_years(list(range(t0, t1 + 1)))
    disc = observed_years(port["holdout"]["years"])
    rows = [{"item": f"event count {t0}-{t1}", "year": f"{t0}-{t1}", "observed": int(test["n_events"].sum()),
             "model_mean": float(fits["frequency"]["mean"] * k), "percentile": mid_percentile(sums, test["n_events"].sum()),
             "model_return_period": np.nan, "note": f"fit {fit_years[0]}-{fit_years[1]}: {fits['n_events']} events, mean {fits['frequency']['mean']:.3f}/yr"}]
    g, mx = ylt["gross"].to_numpy(), ylt["max_event"].to_numpy()
    for kind, df in (("test", test), ("discussion", disc)):
        for r in df.itertuples():
            immature = r.year in port["holdout"]["immature"]
            rows.append({"item": f"annual as-if loss ({kind})", "year": str(r.year), "observed": r.annual_loss,
                         "model_mean": float(g.mean()), "percentile": float(np.mean(g <= r.annual_loss)),
                         "model_return_period": 1 / max(np.mean(g > r.annual_loss), 1 / len(g)),
                         "note": "immature (paid to date)" if immature else ""})
    for kind, df in (("test", test), ("discussion", disc)):
        big = df.sort_values("largest_event").iloc[-1]
        ex = np.mean(mx > big["largest_event"])
        rows.append({"item": f"largest event ({kind})", "year": str(big["year"]), "observed": big["largest_event"],
                     "model_mean": np.nan, "percentile": float(np.mean(mx <= big["largest_event"])),
                     "model_return_period": 1 / ex if ex > 0 else np.inf, "note": big["largest_event_name"]})
    return pd.DataFrame(rows)


def event_out(base_fits: dict, base_rec: str) -> tuple[pd.DataFrame, dict]:
    mod = load_config("modelling")
    sim = load_config("simulation")
    cal = calibration_data()
    ev = cal["events"].sort_values("loss_asif")
    top = ev.iloc[-1]
    fits = fit_all(calibration_data(drop_events=[top["event_id"]]), mod, force=base_families(base_fits))
    t, mx = simulate_table(fits, sim["n_years"], sim["seed"])
    res = evaluate_scenario(t, mx)
    r = row(f"without {top['name']}", res, base_rec)
    r.update({"removed_event": top["name"], "removed_loss_asif": float(top["loss_asif"]),
              "gross_var_995": rm.var(t.gross, 0.995), "gross_ec_995": rm.economic_capital(t.gross),
              "severity_params": fits["severity"]["params"], "frequency_mean": fits["frequency"]["mean"]})
    return pd.DataFrame([r]), fits
