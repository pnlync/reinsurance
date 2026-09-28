"""Pipeline steps M6 (pricing), M7 (capital) and M8 (frontier and recommendation)."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

from floodcat.capital import frontier as fr
from floodcat.capital.metrics import net_annual_loss
from floodcat.capital.programmes import NO_RI, dedupe, evaluate, generate, programmes_from_table, programmes_table
from floodcat.reinsurance.engine import YearEventTable, apply_programme
from floodcat.utils import risk_measures as rm
from floodcat.utils.io import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, TABLES_DIR, git_hash, load_config, write_json
from floodcat.utils.plotting import finish


# ---------------------------------------------------------------- shared inputs

def pricing_params(ri: dict, overrides: dict | None = None) -> dict:
    p = ri["pricing"]
    out = {"coc_r": p["coc_r"], "d": p["diversification_d"], "xol_expense": p["xol_expense"], "qs_expense": p["qs_expense"],
           "rate": ri["reinstatement_rate"], "tvar_level": p["tvar_level"]}
    for k, v in (overrides or {}).items():
        out[{"diversification_d": "d"}.get(k, k)] = v
    return out


def base_tables() -> tuple[YearEventTable, np.ndarray, pd.DataFrame]:
    yelt = pd.read_parquet(PROCESSED_DIR / "yelt.parquet")
    ylt = pd.read_parquet(PROCESSED_DIR / "ylt.parquet")
    return YearEventTable.from_frames(yelt, ylt), ylt["max_event"].to_numpy(float), ylt


def history_table(years: range | None = None) -> YearEventTable:
    """Calibration as-if years as a year-event table (for burning cost and the Excel check)."""
    port = load_config("portfolio")
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet").set_index("year")
    years = years or range(port["calibration"]["start"], port["calibration"]["end"] + 1)
    inc = ev[ev["included"] & ev["year"].isin(years)].sort_values(["year", "first_date"])
    yid = (inc["year"] - years[0]).to_numpy(np.int64)
    gross = np.array([att.loc[y, "a_asif"] for y in years]) + np.bincount(yid, weights=inc["loss_asif"], minlength=len(years))
    return YearEventTable(inc["loss_asif"].to_numpy(float), yid, gross)


def load_programmes() -> list:
    return programmes_from_table(pd.read_csv(TABLES_DIR / "programmes.csv"))


# ---------------------------------------------------------------- M6

def run_pricing() -> None:
    ri = load_config("reinsurance")
    t, max_event, _ = base_tables()
    progs, aliases = dedupe(generate(max_event, ri))
    programmes_table(progs).to_csv(TABLES_DIR / "programmes.csv", index=False)
    aliases.to_csv(TABLES_DIR / "programme_aliases.csv", index=False)
    layers, qs, _ = evaluate(progs, t, max_event, pricing_params(ri), history=history_table())
    cols = ["layer_id", "q", "attach", "exhaust", "limit", "c", "n_reinst", "attach_rp", "exhaust_rp", "ap", "ep", "years_hit",
            "burning_cost", "el", "sd", "tvar995", "k_r", "capital_charge", "premium", "exp_reinst_premium", "rol", "multiple", "net_cost"]
    layers[cols].to_csv(TABLES_DIR / "layer_pricing.csv", index=False)
    qs.to_csv(TABLES_DIR / "qs_pricing.csv", index=False)
    plot_rol_vs_ap(layers)
    print(f"priced {len(layers)} layers and {len(qs)} QS shares; {len(progs)} programmes", flush=True)


def plot_rol_vs_ap(layers: pd.DataFrame) -> None:
    d = layers[(layers["q"] == 0) & (layers["c"] == 1.0) & (layers["n_reinst"] == 1)]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for (e, g), col in zip(d.groupby("exhaust_rp"), ("#c0573e", "#2f5d8a", "#3a8a5f", "#8e6bb0")):
        g = g.sort_values("ap")
        ax.plot(g["ap"] * 100, g["rol"] * 100, "o-", color=col, label=f"exhaust 1-in-{e}")
        for _, r in g.iterrows():
            ax.annotate(f"1-in-{r['attach_rp']}", (r["ap"] * 100, r["rol"] * 100), fontsize=7, xytext=(4, -10), textcoords="offset points")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
    ax.set_xlabel("Attachment probability (%, log scale)")
    ax.set_ylabel("Technical rate on line (%)")
    ax.legend(frameon=False, fontsize=8)
    finish(fig, ax, "Indicative technical ROL by layer (QS 0%, 100% placed, 1 reinstatement)")
    fig.savefig(FIGURES_DIR / "m6_rol_vs_ap.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- M7

def run_capital() -> None:
    ri = load_config("reinsurance")
    sim = load_config("simulation")
    t, max_event, _ = base_tables()
    progs = load_programmes()
    _, _, m = evaluate(progs, t, max_event, pricing_params(ri), ri["capital"]["var_level"], net_ep_rps=sim["return_periods"])
    for h in ri["decision"]["hurdle_sensitivity"]:
        m[f"coc_below_h{int(round(h * 100)):02d}"] = m["implied_coc"] < h
    m = m.merge(relief_gap(progs, t, ri), on="programme_id")
    m.to_csv(TABLES_DIR / "programme_metrics.csv", index=False)
    write_json({"limit_monotonicity_violations": limit_monotonicity(m), "git_hash": git_hash()}, TABLES_DIR / "m7_checks.json")
    print(f"programme metrics for {len(m)} programmes", flush=True)


def relief_gap(progs, t: YearEventTable, ri: dict) -> pd.DataFrame:
    """Relief vs 'recovery in the gross 1-in-200 year minus expected recovery' (SPEC §9 M7, reported, no tolerance)."""
    k = int(np.ceil(round(t.n_years * ri["capital"]["var_level"], 9)))
    year = int(np.argsort(t.gross, kind="stable")[k - 1])
    rows = []
    cache: dict = {}
    for p in progs:
        res = apply_programme(t, p, cache)
        rec = res["qs_recovery"] + sum(r["recovery"] for r in res["layers"].values())
        rows.append({"programme_id": p.programme_id, "relief_approx": float(rec[year] - rec.mean())})
    return pd.DataFrame(rows)


def limit_monotonicity(m: pd.DataFrame) -> list[dict]:
    """At fixed q, attachment, placement and reinstatements, more limit (single layer) should not raise EC_net."""
    single = m[m["programme_id"].str.contains("_T0_")].copy()
    parts = single["programme_id"].str.extract(r"QS(\d+)_A(\d+)_E(\d+)_T0_C(\d+)_R(\d+)").astype(int)
    single[["qq", "a", "e", "cc", "n"]] = parts.values
    out = []
    for key, g in single.groupby(["qq", "a", "cc", "n"]):
        g = g.sort_values("e")
        inc = np.diff(g["ec_net"].to_numpy())
        for i in np.flatnonzero(inc > 1e-9):
            out.append({"group": list(map(int, key)), "from": g["programme_id"].iloc[i], "to": g["programme_id"].iloc[i + 1], "ec_increase": float(inc[i])})
    return out


# ---------------------------------------------------------------- M8

def select(m: pd.DataFrame, ri: dict, risk: str = "ec_net") -> dict:
    d = m.rename(columns={risk: "risk"}) if risk != "ec_net" else m.copy()
    if risk != "ec_net":
        d["ec_net"] = d["risk"]
        d["relief"] = d.loc[d["programme_id"] == NO_RI, "ec_net"].iloc[0] - d["ec_net"]
        d["relief_pct"] = d["relief"] / d.loc[d["programme_id"] == NO_RI, "ec_net"].iloc[0]
    hs = ri["decision"]["hurdle_sensitivity"]
    return fr.choices(d, NO_RI, hs, ri["decision"]["budget_min_relief"])


def run_frontier() -> None:
    ri = load_config("reinsurance")
    m = pd.read_csv(TABLES_DIR / "programme_metrics.csv")
    progs = {p.programme_id: p for p in load_programmes()}
    lp = pd.read_csv(TABLES_DIR / "layer_pricing.csv").set_index("layer_id")
    ch = select(m, ri)
    ch_tv = select(m, ri, risk="net_tvar_99")
    h0 = ri["decision"]["hurdle"]
    rec_id = ch["balanced"][h0]

    front = ch["frontier"][["programme_id", "net_cost", "ec_net", "relief", "relief_pct", "implied_coc"]].copy()
    front["on_hull"] = front["programme_id"].isin(ch["hull"]["programme_id"])
    front = front.merge(ch["hull"][["programme_id", "marginal_coc"]], on="programme_id", how="left")
    front.to_csv(TABLES_DIR / "frontier.csv", index=False)

    def summary(pid: str) -> dict:
        r = m.set_index("programme_id").loc[pid]
        p = progs[pid]
        layers = []
        for lay in p.layers:
            l = lp.loc[lay.layer_id]
            layers.append({"layer_id": lay.layer_id, "attach": lay.attach, "exhaust": lay.exhaust, "limit": lay.limit,
                           "attach_rp": lay.attach_rp, "exhaust_rp": lay.exhaust_rp, "ap": float(l["ap"]), "ep": float(l["ep"]),
                           "placement": lay.c, "n_reinst": lay.n_reinst, "premium": float(l["premium"]), "rol": float(l["rol"]),
                           "el": float(l["el"]), "multiple": float(l["multiple"])})
        return {"programme_id": pid, "q": p.q, "layers": layers,
                **{k: float(r[k]) for k in ("premium", "exp_reinst_premium", "exp_recovery", "net_cost", "gross_ec", "ec_net",
                                            "relief", "relief_pct", "implied_coc", "net_mean", "net_var_995", "net_tvar_99")}}

    rec = {
        "recommended": summary(rec_id),
        "rule": f"Balanced at cedent hurdle h = {h0:.0%}",
        "choices": {"budget_first": ch["budget_first"], "protection_first": ch["protection_first"],
                    "balanced": {f"{h:.2f}": pid for h, pid in ch["balanced"].items()}},
        "choice_summaries": {pid: summary(pid) for pid in sorted({ch["budget_first"], ch["protection_first"], *ch["balanced"].values()} - {None})},
        "tvar99_frontier": {"budget_first": ch_tv["budget_first"], "protection_first": ch_tv["protection_first"],
                            "balanced": {f"{h:.2f}": pid for h, pid in ch_tv["balanced"].items()}, "n_frontier": int(len(ch_tv["frontier"]))},
        "n_programmes": int(len(m)),
        "n_frontier": int(len(ch["frontier"])),
        "n_hull": int(len(ch["hull"])),
        "hull": ch["hull"][["programme_id", "net_cost", "ec_net", "relief_pct", "marginal_coc"]].to_dict(orient="records"),
        "git_hash": git_hash(),
    }
    write_json(rec, OUTPUTS_DIR / "recommendation.json")
    hero_2(progs[rec_id], ri)
    hero_3(m, ch, rec_id)
    print(f"{len(m)} programmes, {len(ch['frontier'])} on frontier; Balanced(10%) = {rec_id}", flush=True)


def hero_2(prog, ri: dict) -> None:
    t, max_event, _ = base_tables()
    progs = [prog]
    layers, qs, _ = evaluate(progs, t, max_event, pricing_params(ri))
    prices = layers.set_index("layer_id").to_dict(orient="index")
    res = apply_programme(t, prog)
    qp = qs.iloc[0]["premium"] if len(qs) else 0.0
    net = net_annual_loss(t.gross, res["qs_recovery"], qp, res["layers"], prices, ri["reinstatement_rate"])
    rp = np.geomspace(1.2, 1000, 300)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rp, [rm.var(t.gross, 1 - 1 / r) / 1e3 for r in rp], color="#2f5d8a", lw=2, label="Gross annual loss")
    ax.plot(rp, [rm.var(net, 1 - 1 / r) / 1e3 for r in rp], color="#3a8a5f", lw=2, label="Net of recommended programme (incl. premiums)")
    ax.axvline(200, color="0.5", ls=":", lw=1)
    ax.annotate("1-in-200", (200, ax.get_ylim()[1] * 0.95), fontsize=8, color="0.4", ha="right")
    ax.set_xscale("log")
    ax.set_xticks([2, 5, 10, 20, 50, 100, 200, 500, 1000])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Return period (years, log scale)")
    ax.set_ylabel("Annual loss (USD bn)")
    ax.legend(frameon=False, loc="upper left")
    finish(fig, ax, f"Gross vs net AEP: {prog.programme_id}")
    fig.savefig(FIGURES_DIR / "hero_2_gross_net.png", dpi=150)
    plt.close(fig)


def hero_3(m: pd.DataFrame, ch: dict, rec_id: str) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for q, col in zip(sorted(m["q"].unique()), ("#9aa7b4", "#c9a66b", "#b77fa6")):
        d = m[m["q"] == q]
        ax.scatter(d["net_cost"], d["ec_net"] / 1e3, s=12, color=col, alpha=0.7, label=f"QS {q:.0%}")
    f = ch["frontier"]
    ax.plot(f["net_cost"], f["ec_net"] / 1e3, color="k", lw=1.2, label="Cost–capital frontier")
    labels = {ch["budget_first"]: "Budget-first", ch["protection_first"]: "Protection-first", rec_id: "Balanced (h = 10%)"}
    mi = m.set_index("programme_id")
    for pid, lab in labels.items():
        if pid is None:
            continue
        x, y = mi.loc[pid, "net_cost"], mi.loc[pid, "ec_net"] / 1e3
        ax.scatter([x], [y], s=90, facecolor="none", edgecolor="#c0392b", lw=2, zorder=5)
        right = x > 0.75 * m["net_cost"].max()
        ax.annotate(f"{lab}\n{pid}", (x, y), fontsize=8, xytext=(-12, 14) if right else (10, 8), textcoords="offset points",
                    ha="right" if right else "left")
    ax.set_xlabel("Net cost of reinsurance (USD m per year)")
    ax.set_ylabel("99.5% one-year economic capital proxy, net (USD bn)")
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    finish(fig, ax, f"Cost–capital frontier: {len(m)} programmes")
    fig.savefig(FIGURES_DIR / "hero_3_frontier.png", dpi=150)
    plt.close(fig)
