"""Year bootstrap of parameter uncertainty for the recommended contract (SPEC §9 M9).

Calibration years are resampled with replacement; a year's events and its attritional loss move
together. Each replicate is refitted (base families), simulated for 20,000 years, and the base
recommended contract is re-priced and re-evaluated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from floodcat.capital.programmes import NO_RI, evaluate
from floodcat.capital.run import load_programmes, pricing_params
from floodcat.model.fit import calibration_data, fit_all
from floodcat.utils.io import load_config
from floodcat.validation.backtest import base_families
from floodcat.validation.scenario import simulate_table


def resample_years(years: list[int], rng: np.random.Generator) -> list[int]:
    return list(rng.choice(years, size=len(years), replace=True))


def run_bootstrap(base_fits: dict, rec_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    port = load_config("portfolio")
    mod = load_config("modelling")
    sim = load_config("simulation")
    ri = load_config("reinsurance")
    years = list(range(port["calibration"]["start"], port["calibration"]["end"] + 1))
    progs = [p for p in load_programmes() if p.programme_id in (NO_RI, rec_id)]
    rng = np.random.default_rng([sim["seed"], 900])
    rows = []
    for b in range(sim["bootstrap"]["replicates"]):
        ys = resample_years(years, rng)
        data = calibration_data(year_sample=ys)
        row = {"replicate": b, "n_events": int(len(data["severities"]))}
        try:
            if len(data["severities"]) < 2:
                raise ValueError("fewer than 2 events in the resample")
            fits = fit_all(data, mod, force=base_families(base_fits))
            t, mx = simulate_table(fits, sim["bootstrap"]["n_years"], sim["seed"], run=1000 + b)
            _, _, m = evaluate(progs, t, mx.to_numpy(float), pricing_params(ri), ri["capital"]["var_level"])
            r = m.set_index("programme_id").loc[rec_id]
            row.update({"ok": True, "relief": r["relief"], "relief_pct": r["relief_pct"], "implied_coc": r["implied_coc"],
                        "net_cost": r["net_cost"], "gross_ec": r["gross_ec"]})
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)[:200]})
        rows.append(row)
    reps = pd.DataFrame(rows)
    ok = reps[reps["ok"]]
    ci = pd.DataFrame([{"metric": k, "p05": ok[k].quantile(0.05), "median": ok[k].median(), "p95": ok[k].quantile(0.95),
                        "n_ok": len(ok), "n_failed": int((~reps["ok"]).sum())}
                       for k in ("relief", "relief_pct", "implied_coc", "net_cost", "gross_ec")])
    return ci, reps
