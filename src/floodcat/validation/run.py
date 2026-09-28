"""M9 step: convergence of the recommendation, temporal holdout, leave-one-major-event-out, year bootstrap, stresses."""
from __future__ import annotations

import json
import re

import pandas as pd

from floodcat.capital.programmes import NO_RI, evaluate
from floodcat.capital.run import load_programmes, pricing_params
from floodcat.utils.io import OUTPUTS_DIR, TABLES_DIR, git_hash, load_config, write_json
from floodcat.validation import backtest, bootstrap, stress
from floodcat.validation.scenario import simulate_table


def structure(pid: str) -> str:
    return re.sub(r"_C\d+", "", pid)


def recommended_convergence(fits: dict, rec_id: str, base_relief: float) -> dict:
    sim = load_config("simulation")
    ri = load_config("reinsurance")
    t, mx = simulate_table(fits, sim["convergence"]["n_years"], sim["seed"], run=1)
    progs = [p for p in load_programmes() if p.programme_id in (NO_RI, rec_id)]
    _, _, m = evaluate(progs, t, mx.to_numpy(float), pricing_params(ri), ri["capital"]["var_level"])
    r = float(m.set_index("programme_id").loc[rec_id, "relief"])
    d = abs(r / base_relief - 1)
    return {"relief_base": base_relief, "relief_check": r, "n_years_check": sim["convergence"]["n_years"], "rel_diff": d,
            "tolerance": sim["convergence"]["tolerance"], "within_tolerance": bool(d <= sim["convergence"]["tolerance"])}


def run() -> None:
    fits = json.loads((TABLES_DIR / "fits.json").read_text())
    rec = json.loads((OUTPUTS_DIR / "recommendation.json").read_text())
    rec_id = rec["recommended"]["programme_id"]

    conv = recommended_convergence(fits, rec_id, rec["recommended"]["relief"])
    print(f"recommended relief convergence: {conv['rel_diff']:.2%}", flush=True)
    ho = backtest.holdout(fits)
    ho.to_csv(TABLES_DIR / "holdout.csv", index=False)
    print("holdout done", flush=True)
    eo, _ = backtest.event_out(fits, rec_id)
    eo.drop(columns=["severity_params"]).to_csv(TABLES_DIR / "event_out.csv", index=False)
    print(f"event-out: Balanced = {eo.iloc[0]['balanced_id']}", flush=True)
    st, _ = stress.run_stresses(fits, rec_id)
    st.to_csv(TABLES_DIR / "recommendation_stability.csv", index=False)
    print(st[["scenario", "balanced_id", "same_as_base"]].to_string(index=False), flush=True)
    sens = stress.run_sensitivities(fits, rec_id)
    sens.to_csv(TABLES_DIR / "sensitivities.csv", index=False)
    print(sens[["scenario", "balanced_id", "same_as_base"]].to_string(index=False), flush=True)
    ci, reps = bootstrap.run_bootstrap(fits, rec_id)
    ci.to_csv(TABLES_DIR / "bootstrap_ci.csv", index=False)
    reps.to_csv(TABLES_DIR / "bootstrap_replicates.csv", index=False)
    print(ci.to_string(index=False), flush=True)

    stressed = st[st["scenario"] != "base"]
    write_json({
        "recommended": rec_id,
        "convergence_recommended": conv,
        "stress_held": int(stressed["same_as_base"].sum()),
        "stress_total": int(len(stressed)),
        # same layer structure (QS share, attachment, exhaustion, tower split, reinstatements), placement ignored
        "stress_structure_held": int((stressed["balanced_id"].map(structure) == structure(rec_id)).sum()),
        "base_row_matches_m8": bool(st.iloc[0]["balanced_id"] == rec_id),
        "git_hash": git_hash(),
    }, TABLES_DIR / "validation_summary.json")
