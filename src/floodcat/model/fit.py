"""M3 step: fit frequency, severity and attritional on the calibration years; diagnostics; fits.json (SPEC §9 M3)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from floodcat.model import attritional, frequency, severity
from floodcat.utils.io import FIGURES_DIR, PROCESSED_DIR, REPORTS_DIR, TABLES_DIR, git_hash, load_config, write_json
from floodcat.utils.plotting import finish


def calibration_data(fit_years: tuple[int, int] | None = None, drop_events: list[str] | None = None,
                     year_sample: list[int] | None = None, catalogue: tuple[pd.DataFrame, pd.DataFrame] | None = None) -> dict:
    """Events (as-if, included) and A_t for the calibration years.

    fit_years: override the calibration window (temporal back-test, calibration-start sensitivity).
    drop_events: event ids removed (leave-one-major-event-out). year_sample: list of years, possibly
    repeated (year bootstrap): a year's events and its attritional move together. catalogue: (events,
    attritional) frames to use instead of the processed files (u0 and CPI-only sensitivities)."""
    port = load_config("portfolio")
    if catalogue is None:
        ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
        att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet")
    else:
        ev, att = catalogue
    att = att.set_index("year")
    y0, y1 = fit_years or (port["calibration"]["start"], port["calibration"]["end"])
    ev = ev[ev["included"] & ev["year"].between(y0, y1)]
    if drop_events:
        ev = ev[~ev["event_id"].isin(drop_events)]
    years = list(range(y0, y1 + 1)) if year_sample is None else list(year_sample)
    counts = ev.groupby("year").size()
    sev = np.concatenate([ev.loc[ev["year"] == y, "loss_asif"].values for y in years]) if years else np.array([])
    return {
        "years": years,
        "counts": pd.Series([int(counts.get(y, 0)) for y in years], index=years),
        "severities": sev,
        "attritional": np.array([att.loc[y, "a_asif"] for y in years]),
        "events": ev,
    }


def top_check(family: str, p: dict, x: np.ndarray, u0: float, top_n: int) -> pd.DataFrame:
    """Top events: fitted quantile at the plotting position (ratio, information only) and the order-statistic
    probability P(k-th largest of n >= observed) = P(Binomial(n, S(x_k | u0)) >= k) used by rule D8."""
    xs = np.sort(x)
    n = len(xs)
    pp = severity.plotting_positions(n)
    fitted = severity.cond_quantile(family, p, u0, pp)
    t = pd.DataFrame({"rank": np.arange(n, 0, -1), "empirical": xs, "prob": pp, "fitted": fitted})
    t["ratio"] = t["fitted"] / t["empirical"]
    exceed = severity.cond_isf_inverse(family, p, u0, xs)
    t["p_order"] = stats.binom.sf(t["rank"] - 1, n, exceed)
    return t.tail(top_n).iloc[::-1].reset_index(drop=True)


def fit_all(data: dict, mod: dict, force: dict | None = None) -> dict:
    """Fit everything with the SPEC §5.1 rules; used by M3 and re-used by M9 refits.

    force: {"frequency": family, "severity": family} keeps the base families on a refit (M9: no
    re-selection unless a fit fails); only the chosen severity family is fitted then."""
    u0 = mod["event_threshold_u0"]
    x = data["severities"]
    freq = frequency.fit_frequency(data["counts"], mod["frequency"]["lr_critical"])
    if force:
        freq = frequency.force_family(freq, force["frequency"])
    cands = {}
    lo, hi = mod["severity"]["top_order_stat_band"]
    for fam in ([force["severity"]] if force else mod["severity"]["candidates"]):
        f = severity.fit_truncated(fam, x, u0)
        tc = top_check(fam, f["params"], x, u0, mod["severity"]["top_n_check"])
        f["top_check"] = tc.round(4).to_dict(orient="records")
        f["tail_ok"] = bool(tc["p_order"].between(lo, hi).all())
        f["mean_finite"] = severity.mean_finite(fam, f["params"])
        f["acceptable"] = bool(f["converged"] and f["tail_ok"] and not f["at_boundary"])
        cands[fam] = f
    ok = [f for f in cands.values() if f["acceptable"]]
    pool = ok if ok else list(cands.values())
    chosen = force["severity"] if force else min(pool, key=lambda f: f["aic"])["family"]
    gpd_thr = float(np.median(x))
    try:
        gpd = severity.fit_gpd(x, gpd_thr)
    except Exception:  # too few exceedances in a resample; only the tail stress uses it
        gpd = {"threshold": gpd_thr, "xi": float("nan"), "beta": float("nan"), "n_exceed": int((x > gpd_thr).sum())}
    n_exceed = gpd["n_exceed"]
    return {
        "u0": u0,
        "n_events": int(len(x)),
        "n_years": int(len(data["years"])),
        "frequency": freq.to_dict(),
        "severity": {
            "candidates": cands,
            "chosen": chosen,
            "params": cands[chosen]["params"],
            "any_acceptable": bool(ok),
            "rationale": _rationale(cands, chosen, ok, lo, hi),
        },
        "gpd": {
            "base_allowed": bool(n_exceed >= mod["gpd"]["min_exceedances"]),
            "min_exceedances": mod["gpd"]["min_exceedances"],
            "tail_stress": gpd,
        },
        "largest_event": float(x.max()),
        "cap": float(mod["event_cap_multiple"] * x.max()),
        "attritional": attritional.fit_attritional(data["attritional"]),
    }


def _rationale(cands, chosen, ok, lo, hi) -> str:
    parts = []
    for fam, f in sorted(cands.items(), key=lambda kv: kv[1]["aic"]):
        why = []
        if not f["converged"]:
            why.append("optimiser did not converge")
        if f["at_boundary"]:
            why.append("parameters at a boundary (degenerate fit)")
        if not f["tail_ok"]:
            bad = [r for r in f["top_check"] if not lo <= r["p_order"] <= hi]
            why.append(f"order-statistic probability outside [{lo}, {hi}] for rank(s) {', '.join(str(r['rank']) for r in bad)}")
        parts.append(f"{fam}: AIC {f['aic']:.2f}, " + ("acceptable" if not why else "; ".join(why)))
    head = (f"Chosen: {chosen}, the lowest AIC among acceptable candidates." if ok
            else f"No candidate passed every check; {chosen} has the lowest AIC and is used with this caveat.")
    return head + " " + " | ".join(parts)


def plots(data: dict, fits: dict, mod: dict) -> None:
    x = np.sort(data["severities"])
    u0 = fits["u0"]
    pp = severity.plotting_positions(len(x))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for fam, f in fits["severity"]["candidates"].items():
        q = severity.cond_quantile(fam, f["params"], u0, pp)
        lab = fam + (" (chosen)" if fam == fits["severity"]["chosen"] else "")
        axes[0].loglog(q, x, "o", ms=4, label=lab)
        grid = np.geomspace(u0, fits["cap"], 200)
        d = severity.dist(fam, f["params"])
        axes[1].loglog(grid, d.sf(grid) / d.sf(u0), label=lab)
    lim = [u0 * 0.9, x.max() * 1.5]
    axes[0].plot(lim, lim, "k--", lw=0.8)
    axes[0].set_xlabel("Fitted conditional quantile (USD m)")
    axes[0].set_ylabel("Empirical as-if event loss (USD m)")
    axes[0].legend(frameon=False)
    axes[1].loglog(x, 1 - pp, "k.", label="empirical")
    axes[1].set_xlabel("Event loss (USD m)")
    axes[1].set_ylabel("P(S > s | S > u0)")
    axes[1].legend(frameon=False)
    finish(fig, axes[0], "Severity diagnostics: QQ plot and conditional survival")
    fig.savefig(FIGURES_DIR / "m3_severity_qq_survival.png", dpi=150)
    plt.close(fig)

    thr = np.quantile(x, np.linspace(0, 0.8, 12))
    me = severity.mean_excess(x, thr)
    stab = [severity.fit_gpd(x, t)["xi"] if (x > t).sum() >= 5 else np.nan for t in thr]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].plot(thr, me, "o-")
    axes[0].set_xlabel("Threshold u (USD m)")
    axes[0].set_ylabel("Mean excess e(u) (USD m)")
    axes[1].plot(thr, stab, "o-")
    axes[1].set_xlabel("Threshold u (USD m)")
    axes[1].set_ylabel("GPD shape ξ (MLE)")
    finish(fig, axes[0], f"GPD diagnostics ({fits['n_events']} events; base needs ≥ {mod['gpd']['min_exceedances']} exceedances)")
    fig.savefig(FIGURES_DIR / "m3_gpd_diagnostics.png", dpi=150)
    plt.close(fig)


def report(fits: dict, data: dict, mod: dict) -> None:
    fr = fits["frequency"]
    sev = fits["severity"]
    port = load_config("portfolio")
    rows = []
    for fam, f in sev["candidates"].items():
        pstr = ", ".join(f"{k} = {v:.4g}" for k, v in f["params"].items())
        rows.append(f"| {fam} | {pstr} | {f['loglik']:.2f} | {f['aic']:.2f} | {f['bic']:.2f} | {'yes' if f['tail_ok'] else 'no'} | {'yes' if f['at_boundary'] else ''} | {'yes' if f['mean_finite'] else 'no'} |")
    top_rows = []
    for i in range(len(sev["candidates"][sev["chosen"]]["top_check"])):
        r0 = sev["candidates"][sev["chosen"]]["top_check"][i]
        cells = [f"{sev['candidates'][fam]['top_check'][i]['fitted']:,.0f} ({sev['candidates'][fam]['top_check'][i]['ratio']:.2f}; p {sev['candidates'][fam]['top_check'][i]['p_order']:.2f})" for fam in sev["candidates"]]
        top_rows.append(f"| {r0['rank']} | {r0['empirical']:,.0f} | {r0['prob']:.3f} | " + " | ".join(cells) + " |")
    counts = data["counts"].values
    year_counts = ", ".join(f"{y}: {c}" for y, c in zip(data["years"], counts))
    tr = fr["trend"]
    g = fits["gpd"]
    text = f"""# Model selection (M3)

Generated by `make model`. Calibration {port['calibration']['start']}–{port['calibration']['end']}, as-if 2025, USD m, u₀ = {fits['u0']:,}.

## Frequency

Included events per year: {year_counts}.

- Mean {fr['mean']:.3f}, dispersion index Var/Mean = {fr['dispersion_index']:.3f} over {fr['n_years']} years.
- Poisson log-likelihood {fr['loglik_poisson']:.3f}; NB log-likelihood {fr['loglik_nb']:.3f}{'' if fr['size'] is None else f" (size r = {fr['size']:.3f})"}; LR = 2(ℓ_NB − ℓ_Pois) = {fr['lr_stat']:.3f} vs critical value {mod['frequency']['lr_critical']}.
- **Chosen: {fr['family']}** (SPEC §5.1 rule).
- Trend check (Poisson GLM on year, reported only): slope {tr.get('slope_per_year', float('nan')):+.3f} per year, p = {tr.get('p_value', float('nan')):.3f}.

## Severity (left-truncated at u₀)

| Family | Parameters | log-lik | AIC | BIC | Top-{mod['severity']['top_n_check']} tail OK | At boundary | Finite mean |
|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

Top events: fitted conditional quantile at the event's plotting position i/(n + 1), then in brackets the ratio fitted / empirical (information only) and p = P(k-th largest of n events ≥ observed) under the fit:

| Rank | Empirical | Position | {' | '.join(sev['candidates'])} |
|---|---|---|{'---|' * len(sev['candidates'])}
{chr(10).join(top_rows)}

**Rule (SPEC §5.1, decision D8):** lowest AIC among candidates that converged, are not degenerate, and for which each of the top {mod['severity']['top_n_check']} events is unremarkable under the fit: p inside [{mod['severity']['top_order_stat_band'][0]}, {mod['severity']['top_order_stat_band'][1]}]. The quantile ratio alone is misleading for n = {fits['n_events']}: the largest of 20 events is very variable, so a fitted quantile at half the observed value can still be entirely consistent with the data.

**{sev['rationale']}**

Figures: `outputs/figures/m3_severity_qq_survival.png`, `outputs/figures/m3_gpd_diagnostics.png`.

## GPD

{fits['n_events']} events in total; GPD as the base needs at least {g['min_exceedances']} exceedances of the GPD threshold, so **GPD is {'allowed' if g['base_allowed'] else 'not used as the base'}**. It is used in the `tail_heavy` stress: above the median calibration event (USD {g['tail_stress']['threshold']:,.0f}m, {g['tail_stress']['n_exceed']} exceedances) ξ̂ = {g['tail_stress']['xi']:.3f}, β̂ = {g['tail_stress']['beta']:,.1f}; the stress uses ξ̂ + 0.1.

## Event cap and attritional

- Largest as-if calibration event USD {fits['largest_event']:,.1f}m; each simulated event is capped at {mod['event_cap_multiple']:g}× = USD {fits['cap']:,.1f}m.
- Attritional A_t: mean USD {fits['attritional']['mean']:,.1f}m, SD USD {fits['attritional']['sd']:,.1f}m; base = bootstrap of the {len(fits['attritional']['values'])} calibration values, sensitivity = lognormal by moments (μ = {fits['attritional']['lognormal']['mu']:.3f}, σ = {fits['attritional']['lognormal']['sigma']:.3f}).
"""
    (REPORTS_DIR / "model_selection.md").write_text(text)


def run() -> None:
    mod = load_config("modelling")
    data = calibration_data()
    fits = fit_all(data, mod)
    fits["git_hash"] = git_hash()
    write_json(fits, TABLES_DIR / "fits.json")
    plots(data, fits, mod)
    report(fits, data, mod)
    print(f"frequency {fits['frequency']['family']} mean {fits['frequency']['mean']:.3f}; severity {fits['severity']['chosen']}", flush=True)
