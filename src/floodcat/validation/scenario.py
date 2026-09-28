"""Re-run M4-M8 for a changed model or pricing basis on the fixed base contract grid (SPEC §9 M9)."""
from __future__ import annotations

import pandas as pd

from floodcat.capital.programmes import evaluate
from floodcat.capital.run import load_programmes, pricing_params, select
from floodcat.model.simulate import simulate
from floodcat.reinsurance.engine import YearEventTable
from floodcat.utils.io import load_config


def simulate_table(fits: dict, n_years: int, seed: int, run: int = 0, **kw) -> tuple[YearEventTable, pd.Series]:
    yelt, ylt = simulate(fits, n_years, seed, run, **kw)
    return YearEventTable.from_frames(yelt, ylt), ylt["max_event"]


def evaluate_scenario(t: YearEventTable, max_event, *, pricing_overrides: dict | None = None, hurdle: float | None = None,
                      programmes: list | None = None) -> dict:
    """Price, compute metrics and pick the three choices; Balanced at `hurdle` (default: config hurdle)."""
    ri = load_config("reinsurance")
    progs = programmes or load_programmes()
    _, _, m = evaluate(progs, t, max_event.to_numpy(float), pricing_params(ri, pricing_overrides), ri["capital"]["var_level"])
    h = ri["decision"]["hurdle"] if hurdle is None else hurdle
    hs = sorted(set(ri["decision"]["hurdle_sensitivity"]) | {h})
    ri2 = {**ri, "decision": {**ri["decision"], "hurdle_sensitivity": hs}}
    ch = select(m, ri2)
    return {"metrics": m, "balanced": ch["balanced"][h], "choices": ch}


def row(name: str, res: dict, base_id: str) -> dict:
    m = res["metrics"].set_index("programme_id")
    b = res["balanced"]
    r = m.loc[b]
    rb = m.loc[base_id]
    return {"scenario": name, "balanced_id": b, "same_as_base": b == base_id,
            "relief": r["relief"], "relief_pct": r["relief_pct"], "net_cost": r["net_cost"], "implied_coc": r["implied_coc"],
            "base_rec_relief_pct": rb["relief_pct"], "base_rec_net_cost": rb["net_cost"], "base_rec_implied_coc": rb["implied_coc"],
            "gross_ec": r["gross_ec"]}
