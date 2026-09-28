"""Year-event simulation: YELT / YLT, OEP / AEP, gross metrics and convergence (SPEC §9 M4).

Each simulated year draws N, then N event losses from the truncated severity (scaled for stresses,
then capped), then attritional A. Event losses are i.i.d., so the draw order is itself a random
order within the year; reinstatements consume layers in that order.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker  # noqa: F401  (log-axis tick labels)
import numpy as np
import pandas as pd

from floodcat.model import attritional, frequency, severity
from floodcat.utils import risk_measures as rm
from floodcat.utils.io import FIGURES_DIR, PROCESSED_DIR, TABLES_DIR, git_hash, load_config, write_json
from floodcat.utils.plotting import finish

# independent random streams per component, derived deterministically from the config seed
STREAM_N, STREAM_S, STREAM_A = 1, 2, 3


def rngs(seed: int, run: int = 0) -> dict:
    return {k: np.random.default_rng([seed, run, s]) for k, s in (("n", STREAM_N), ("s", STREAM_S), ("a", STREAM_A))}


def simulate(fits: dict, n_years: int, seed: int, run: int = 0, *, frequency_scale: float = 1.0,
             severity_scale: float = 1.0, tail_gpd: dict | None = None, attritional_method: str = "bootstrap") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (yelt, ylt). YELT: year_id, event_seq, loss. YLT: year_id, n_events, attritional, cat_total, gross, max_event."""
    r = rngs(seed, run)
    n = frequency.sample_counts(fits["frequency"], n_years, r["n"], scale=frequency_scale)
    total = int(n.sum())
    sev = fits["severity"]
    if tail_gpd is None:
        s = severity.sample(sev["chosen"], sev["params"], fits["u0"], total, r["s"])
    else:
        s = severity.sample_body_gpd(sev["chosen"], sev["params"], fits["u0"], tail_gpd, total, r["s"])
    s = np.minimum(s * severity_scale, fits["cap"])
    a = attritional.sample_attritional(fits["attritional"], n_years, r["a"], attritional_method)

    year_id = np.repeat(np.arange(n_years), n)
    start = np.repeat(np.cumsum(n) - n, n)
    event_seq = np.arange(total) - start
    yelt = pd.DataFrame({"year_id": year_id.astype(np.int32), "event_seq": event_seq.astype(np.int16), "loss": s})

    cat_total = np.bincount(year_id, weights=s, minlength=n_years)
    max_event = np.zeros(n_years)
    np.maximum.at(max_event, year_id, s)
    ylt = pd.DataFrame({"year_id": np.arange(n_years, dtype=np.int32), "n_events": n.astype(np.int16), "attritional": a,
                        "cat_total": cat_total, "gross": a + cat_total, "max_event": max_event})
    return yelt, ylt


def ep_table(ylt: pd.DataFrame, rps: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "return_period": rps,
        "exceedance_prob": [1 / r for r in rps],
        "oep": [rm.return_level(ylt["max_event"].values, r) for r in rps],
        "aep": [rm.return_level(ylt["gross"].values, r) for r in rps],
    })


def gross_metrics(ylt: pd.DataFrame) -> dict:
    g = ylt["gross"].values
    return {
        "mean": float(g.mean()), "sd": float(g.std(ddof=1)),
        "aal_cat": float(ylt["cat_total"].mean()), "mean_attritional": float(ylt["attritional"].mean()),
        "var_99": rm.var(g, 0.99), "var_995": rm.var(g, 0.995), "tvar_99": rm.tvar(g, 0.99),
        "ec_995": rm.economic_capital(g, 0.995),
        "mean_n_events": float(ylt["n_events"].mean()),
    }


def batch_se(values: np.ndarray, n_batches: int, stat) -> float:
    b = np.array_split(values, n_batches)
    est = np.array([stat(x) for x in b])
    return float(est.std(ddof=1) / np.sqrt(n_batches))


def hero_1(ylt: pd.DataFrame, calib: pd.DataFrame) -> None:
    """Modelled OEP / AEP with the calibration years' empirical points (SPEC §9 M4)."""
    n = len(ylt)
    rp = np.geomspace(1.2, 1000, 300)
    oep = [rm.var(ylt["max_event"].values, 1 - 1 / r) for r in rp]
    aep = [rm.var(ylt["gross"].values, 1 - 1 / r) for r in rp]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rp, np.array(aep) / 1e3, color="#2f5d8a", lw=2, label="AEP (annual loss), model")
    ax.plot(rp, np.array(oep) / 1e3, color="#c0573e", lw=2, label="OEP (largest event), model")
    m = len(calib)
    for col, c, lab in (("gross", "#2f5d8a", "AEP, calibration years"), ("max_event", "#c0573e", "OEP, calibration years")):
        v = np.sort(calib[col].values)[::-1]
        erp = (m + 1) / np.arange(1, m + 1)
        keep = v > 0
        ax.plot(erp[keep], v[keep] / 1e3, "o", mfc="white", color=c, ms=6, label=lab)
    ax.set_xscale("log")
    ax.set_xlabel("Return period (years, log scale)")
    ax.set_ylabel("Loss (USD bn)")
    ax.set_xticks([2, 5, 10, 20, 50, 100, 200, 500, 1000])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.legend(frameon=False)
    finish(fig, ax, f"Gross catastrophe risk profile: {n:,} simulated years")
    fig.savefig(FIGURES_DIR / "hero_1_ep_curves.png", dpi=150)
    plt.close(fig)


def calibration_years_table() -> pd.DataFrame:
    """Historical as-if annual loss and largest event for the calibration years (empirical EP points)."""
    port = load_config("portfolio")
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet").set_index("year")
    years = range(port["calibration"]["start"], port["calibration"]["end"] + 1)
    inc = ev[ev["included"]]
    cat = inc.groupby("year")["loss_asif"].sum()
    mx = inc.groupby("year")["loss_asif"].max()
    return pd.DataFrame({"year": list(years), "attritional": [att.loc[y, "a_asif"] for y in years],
                         "cat_total": [cat.get(y, 0.0) for y in years], "max_event": [mx.get(y, 0.0) for y in years]}).assign(
        gross=lambda d: d["attritional"] + d["cat_total"])


def run() -> None:
    import json

    sim = load_config("simulation")
    fits = json.loads((TABLES_DIR / "fits.json").read_text())
    yelt, ylt = simulate(fits, sim["n_years"], sim["seed"])
    yelt.to_parquet(PROCESSED_DIR / "yelt.parquet", index=False)
    ylt.to_parquet(PROCESSED_DIR / "ylt.parquet", index=False)

    ep = ep_table(ylt, sim["return_periods"])
    ep.to_csv(TABLES_DIR / "ep_curves.csv", index=False)
    gm = gross_metrics(ylt)
    gm["se_var_995"] = batch_se(ylt["gross"].values, sim["n_batches"], lambda x: rm.var(x, 0.995))
    gm["se_mean"] = batch_se(ylt["gross"].values, sim["n_batches"], np.mean)
    gm["share_capped"] = float((yelt["loss"] >= fits["cap"]).mean())

    _, ylt2 = simulate(fits, sim["convergence"]["n_years"], sim["seed"], run=1)
    v1, v2 = gm["var_995"], rm.var(ylt2["gross"].values, 0.995)
    conv = {"n_years_base": sim["n_years"], "n_years_check": sim["convergence"]["n_years"], "var_995_base": v1,
            "var_995_check": v2, "rel_diff": abs(v2 / v1 - 1), "tolerance": sim["convergence"]["tolerance"]}
    conv["within_tolerance"] = bool(conv["rel_diff"] <= conv["tolerance"])
    gm.update({"seed": sim["seed"], "n_years": sim["n_years"], "git_hash": git_hash()})
    pd.DataFrame([gm]).to_csv(TABLES_DIR / "gross_metrics.csv", index=False)
    write_json(conv, TABLES_DIR / "convergence_gross.json")
    hero_1(ylt, calibration_years_table())
    print(f"gross mean {gm['mean']:,.1f}  VaR99.5 {gm['var_995']:,.1f}  EC {gm['ec_995']:,.1f}  conv diff {conv['rel_diff']:.2%}", flush=True)
