"""M11 step: cv_numbers.json, README.md and the memo (SPEC §9 M11).

Every public number is read from outputs/ here. README and memo are rendered from templates in
reports/templates/ whose only numbers are {{key:format}} placeholders filled from this dictionary.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess

import pandas as pd

from floodcat.utils.io import FIGURES_DIR, OUTPUTS_DIR, PROCESSED_DIR, REPORTS_DIR, ROOT, TABLES_DIR, git_hash, load_config, write_json

TEMPLATES = REPORTS_DIR / "templates"


def _j(name: str) -> dict:
    return json.loads((TABLES_DIR / name).read_text())


def _structure(pid: str) -> str:
    return re.sub(r"_C\d+", "", pid)


def describe(pid: str, rec: dict | None = None) -> str:
    """Plain-English description of a programme ID."""
    if pid == "QS0_XS0":
        return "no reinsurance"
    m = re.match(r"QS(\d+)_XS0", pid)
    if m:
        return f"{m.group(1)}% quota share only"
    m = re.match(r"QS(\d+)_A(\d+)_E(\d+)_T(\d+)_C(\d+)_R(\d+)", pid)
    q, a, e, t, c, n = map(int, m.groups())
    lay = f"1-in-{a} to 1-in-{e} Cat XoL" + (f" split at 1-in-{t}" if t else "") + f", {c}% placed, {'one reinstatement' if n else 'no reinstatement'}"
    return (f"{q}% quota share + " if q else "") + lay


def collect() -> dict:
    port = load_config("portfolio")
    sim = load_config("simulation")
    ri = load_config("reinsurance")
    fits = _j("fits.json")
    rec = json.loads((OUTPUTS_DIR / "recommendation.json").read_text())
    val = _j("validation_summary.json")
    bench = _j("benchmark_summary.json")
    m1 = _j("m1_checks.json")
    gm = pd.read_csv(TABLES_DIR / "gross_metrics.csv").iloc[0]
    ep = pd.read_csv(TABLES_DIR / "ep_curves.csv").set_index("return_period")
    ci = pd.read_csv(TABLES_DIR / "bootstrap_ci.csv").set_index("metric")
    st = pd.read_csv(TABLES_DIR / "recommendation_stability.csv").set_index("scenario")
    sens = pd.read_csv(TABLES_DIR / "sensitivities.csv").set_index("scenario")
    eo = pd.read_csv(TABLES_DIR / "event_out.csv").iloc[0]
    ho = pd.read_csv(TABLES_DIR / "holdout.csv")
    metrics = pd.read_csv(TABLES_DIR / "programme_metrics.csv").set_index("programme_id")
    ev = pd.read_parquet(PROCESSED_DIR / "event_catalogue.parquet")
    att = pd.read_parquet(PROCESSED_DIR / "attritional_by_year.parquet")
    portfolio = pd.read_parquet(PROCESSED_DIR / "portfolio_2025.parquet").set_index("state")
    cal = ev[(ev["period"] == "calibration") & ev["included"]].sort_values("loss_asif", ascending=False)
    r = rec["recommended"]
    h = ri["decision"]["hurdle"]
    ch = rec["choices"]
    bf, pf = metrics.loc[ch["budget_first"]], metrics.loc[ch["protection_first"]]
    gross_ec = float(gm["ec_995"])
    prem = float(portfolio.loc["Total", "premium"] / 1e6)
    lay = r["layers"][0] if r["layers"] else None
    count = ho[ho["item"].str.startswith("event count")].iloc[0]
    ian = ho[ho["item"] == "largest event (test)"].iloc[0]
    held_structure = val.get("stress_structure_held")
    return {
        "git_hash": git_hash(),
        "today": pd.Timestamp.today().strftime("%-d %B %Y"),
        "calibration_start": port["calibration"]["start"], "calibration_end": port["calibration"]["end"],
        "n_calib_years": port["calibration"]["end"] - port["calibration"]["start"] + 1,
        "n_events_calib": int(len(cal)),
        "largest_event": cal.iloc[0]["name"], "largest_event_year": int(cal.iloc[0]["year"]), "largest_event_asif": float(cal.iloc[0]["loss_asif"]),
        "second_event": cal.iloc[1]["name"], "second_event_asif": float(cal.iloc[1]["loss_asif"]),
        "calib_event_total_bn": float(cal["loss_asif"].sum() / 1e3),
        "attritional_mean": float(att[att["period"] == "calibration"]["a_asif"].mean()),
        "u0": fits["u0"], "u0_sens": load_config("modelling")["event_threshold_sensitivity"],
        "n_sims": sim["n_years"], "seed": sim["seed"],
        "n_programmes": rec["n_programmes"], "n_grid_ids": int(len(pd.read_csv(TABLES_DIR / "programme_aliases.csv")) + rec["n_programmes"]),
        "n_frontier": rec["n_frontier"], "n_hull": rec["n_hull"],
        "portfolio_tiv_bn": float(portfolio.loc["Total", "tiv"] / 1e9), "portfolio_policies": float(portfolio.loc["Total", "policies"]),
        "portfolio_premium_m": prem, "fl_tiv_share": float(portfolio.loc["FL", "tiv"] / portfolio.loc["Total", "tiv"]),
        "frequency_family": fits["frequency"]["family"].capitalize(), "frequency_mean": fits["frequency"]["mean"],
        "dispersion": fits["frequency"]["dispersion_index"], "lr_stat": fits["frequency"]["lr_stat"],
        "severity_family": {"loglogistic": "log-logistic", "lognormal": "lognormal", "burr12": "Burr XII"}[fits["severity"]["chosen"]],
        "severity_shape": fits["severity"]["params"].get("shape_c", float("nan")),
        "cap": fits["cap"], "cap_multiple": load_config("modelling")["event_cap_multiple"],
        "gross_mean": float(gm["mean"]), "gross_aal_cat": float(gm["aal_cat"]), "gross_var_995": float(gm["var_995"]),
        "gross_ec": gross_ec, "gross_tvar_99": float(gm["tvar_99"]), "share_capped": float(gm["share_capped"]),
        "conv_diff": _j("convergence_gross.json")["rel_diff"],
        "oep_10": float(ep.loc[10, "oep"]), "oep_20": float(ep.loc[20, "oep"]), "oep_100": float(ep.loc[100, "oep"]), "oep_200": float(ep.loc[200, "oep"]),
        "aep_100": float(ep.loc[100, "aep"]), "aep_200": float(ep.loc[200, "aep"]),
        "recommended_id": r["programme_id"], "recommended_desc": describe(r["programme_id"]),
        "rec_q": r["q"],
        "rec_attach": lay["attach"] if lay else 0.0, "rec_exhaust": lay["exhaust"] if lay else 0.0,
        "rec_placement": lay["placement"] if lay else 0.0,
        "relief_pct": r["relief_pct"], "relief": r["relief"], "net_cost": r["net_cost"], "implied_coc": r["implied_coc"],
        "premium": r["premium"], "exp_recovery": r["exp_recovery"], "ec_net": r["ec_net"],
        "premium_share_of_portfolio": r["premium"] / prem,
        "hurdle": h, "coc_vs_hurdle": "below" if r["implied_coc"] < h else "above",
        "tcr_gross": h * gross_ec, "tcr_rec": r["net_cost"] + h * r["ec_net"],
        "tcr_budget": float(bf["net_cost"] + h * bf["ec_net"]),
        "expected_margin": prem - float(gm["mean"]),
        "coc_min": float(metrics["implied_coc"].min()), "coc_max": float(metrics["implied_coc"].max()),
        "coc_r": ri["pricing"]["coc_r"], "d": ri["pricing"]["diversification_d"], "coc_r_d": ri["pricing"]["coc_r"] * ri["pricing"]["diversification_d"],
        "budget_first_id": ch["budget_first"], "budget_first_desc": describe(ch["budget_first"]),
        "budget_relief_pct": float(bf["relief_pct"]), "budget_net_cost": float(bf["net_cost"]), "budget_coc": float(bf["implied_coc"]),
        "protection_first_id": ch["protection_first"], "protection_first_desc": describe(ch["protection_first"]),
        "protection_relief_pct": float(pf["relief_pct"]), "protection_net_cost": float(pf["net_cost"]),
        "balanced_08_id": ch["balanced"]["0.08"], "balanced_12_id": ch["balanced"]["0.12"],
        "last_marginal_coc": float(pd.DataFrame(rec["hull"])["marginal_coc"].iloc[-1]),
        "stress_held": val["stress_held"], "stress_total": val["stress_total"], "stress_structure_held": held_structure,
        "conv_rec_diff": val["convergence_recommended"]["rel_diff"],
        "relief_pct_p05": float(ci.loc["relief_pct", "p05"]), "relief_pct_p95": float(ci.loc["relief_pct", "p95"]),
        "implied_coc_p05": float(ci.loc["implied_coc", "p05"]), "implied_coc_p95": float(ci.loc["implied_coc", "p95"]),
        "gross_ec_p05": float(ci.loc["gross_ec", "p05"]), "gross_ec_p95": float(ci.loc["gross_ec", "p95"]),
        "n_boot": int(ci.loc["relief", "n_ok"]),
        "eo_event": eo["removed_event"], "eo_gross_ec": float(eo["gross_ec_995"]), "eo_ec_change": float(eo["gross_ec_995"] / gross_ec - 1), "eo_ec_drop": float(1 - eo["gross_ec_995"] / gross_ec),
        "eo_balanced_desc": describe(eo["balanced_id"]), "eo_rec_relief_pct": float(eo["base_rec_relief_pct"]), "eo_rec_coc": float(eo["base_rec_implied_coc"]),
        "ho_count_obs": int(count["observed"]), "ho_count_mean": float(count["model_mean"]), "ho_count_pct": float(count["percentile"]),
        "ho_ian_rp": float(ian["model_return_period"]), "ho_largest_name": ian["note"],
        "d10_rec_coc": float(sens.loc["d_10", "base_rec_implied_coc"]), "d10_balanced_desc": describe(sens.loc["d_10", "balanced_id"]),
        "ln_balanced_desc": describe(sens.loc["severity_lognormal", "balanced_id"]),
        "cap5_balanced_desc": describe(sens.loc["event_cap_5x", "balanced_id"]),
        "fema_rol_2025": bench["fema_rol"]["2025"], "fema_rol_2024": bench["fema_rol"]["2024"], "fema_rol_2023": bench["fema_rol"]["2023"],
        "band_rol_min": bench["model_band"]["rol_min"], "band_rol_max": bench["model_band"]["rol_max"],
        "band_mult_min": bench["model_band"]["multiple_min"], "band_mult_max": bench["model_band"]["multiple_max"],
        "cb_mult_min": min(bench["cat_bond_multiple"].values()), "cb_mult_max": max(bench["cat_bond_multiple"].values()),
        "national_policies_2025": m1["national_inforce_2025"]["policies"], "national_tiv_2025_tn": m1["national_inforce_2025"]["tiv"] / 1e12,
        "claims_rows": m1["claims_checks"]["rows_clean"],
        "cap_sentence": ("The 1-in-200 event sits at the event cap, so the far tail is an assumption, and is tested below."
                         if float(ep.loc[200, "oep"]) >= 0.999 * fits["cap"] else
                         "The 1-in-200 event is below the event cap."),
        "stress_sentence": _stress_sentence(st, r["programme_id"]),
        **_next_step(rec),
        **_burning_cost_example(),
        **_config_constants(ri, port, sim),
        "dedupe_reason": (" (exhaustion at 1-in-200 and 1-in-250 coincide because both event losses sit at the cap)"
                          if float(ep.loc[200, "oep"]) >= 0.999 * fits["cap"] and float(ep.loc[250, "oep"]) >= 0.999 * fits["cap"] else ""),
        "excel_cells": _j("excel_check.json")["n_cells"], "excel_max_diff": _j("excel_check.json")["max_rel_diff"],
        "aic_spread": max(c["aic"] for c in fits["severity"]["candidates"].values()) - min(c["aic"] for c in fits["severity"]["candidates"].values()),
    }


def _config_constants(ri: dict, port: dict, sim: dict) -> dict:
    """Constants quoted in the text, read from config and market data rather than typed into templates."""
    plc = pd.read_csv(ROOT / "data" / "market" / "placements.csv")
    recent = plc[plc["year"] >= 2023]
    hs = ri["decision"]["hurdle_sensitivity"]
    return {
        "xol_expense": ri["pricing"]["xol_expense"], "qs_expense": ri["pricing"]["qs_expense"],
        "budget_min_relief": ri["decision"]["budget_min_relief"], "lr_critical": load_config("modelling")["frequency"]["lr_critical"],
        "h_lo": min(hs), "h_hi": max(hs), "reinst_rate": ri["reinstatement_rate"],
        "fit0": port["backtest"]["fit"][0], "fit1": port["backtest"]["fit"][1], "test0": port["backtest"]["test"][0], "test1": port["backtest"]["test"][1],
        "holdout0": min(port["holdout"]["years"]), "holdout1": max(port["holdout"]["years"]),
        "conv_years": sim["convergence"]["n_years"],
        "qs_shares": " or ".join(f"{q:.0%}" for q in ri["pure_quota_share"]),
        "attach_rps": ", ".join(str(x) for x in ri["attachment_rp"][:-1]) + f" or {ri['attachment_rp'][-1]}",
        "exhaust_rps": ", ".join(str(x) for x in ri["exhaustion_rp"][:-1]) + f" or {ri['exhaustion_rp'][-1]}",
        "split_rps": " or ".join(f"1-in-{x}" for x in ri["tower_split_rp"]),
        "placements": " or ".join(f"{c:.0%}" for c in ri["placement"]),
        "fema_attach_bn": float(recent["layer_low_usd_bn"].min()), "fema_share_lo": float(recent["share"].min()), "fema_share_hi": float(recent["share"].max()),
        "fema_y0": int(recent["year"].min()), "fema_y1": int(recent["year"].max()),
        "band_ap_lo": _j("benchmark_summary.json")["model_band"]["ap_range"][0], "band_ap_hi": _j("benchmark_summary.json")["model_band"]["ap_range"][1],
    }


def _next_step(rec: dict) -> dict:
    hull = pd.DataFrame(rec["hull"])
    i = hull.index[hull["programme_id"] == rec["recommended"]["programme_id"]][0]
    if i + 1 < len(hull):
        nxt = hull.iloc[i + 1]
        return {"next_step_sentence": f"the next step ({describe(nxt['programme_id'])}) costs {nxt['marginal_coc']:.1%} per unit of capital released"}
    return {"next_step_sentence": "no further step on the hull adds protection"}


def _burning_cost_example() -> dict:
    lp = pd.read_csv(TABLES_DIR / "layer_pricing.csv")
    lo = lp[(lp["q"] == 0) & (lp["c"] == 1.0) & (lp["n_reinst"] == 1)].sort_values(["attach", "exhaust"]).iloc[0]
    return {"bc_layer": f"1-in-{lo['attach_rp']} to 1-in-{lo['exhaust_rp']}", "bc_value": float(lo["burning_cost"]), "bc_el": float(lo["el"]),
            "bc_years_hit": int(lo["years_hit"])}


def _stress_sentence(st: pd.DataFrame, rec_id: str) -> str:
    s = st[st.index != "base"]
    exact = int((s["balanced_id"] == rec_id).sum())
    same_struct = int((s["balanced_id"].map(_structure) == _structure(rec_id)).sum())
    n = len(s)
    out = f"The exact contract held in {exact} of {n} stress scenarios and its layer structure in {same_struct} of {n}"
    if same_struct == n and exact < n:
        out += "; the others change only the placement share"
    return out + "."


def md_table(header: list[str], rows: list[list[str]], widths: list[int]) -> str:
    """Pipe table; separator dash counts set relative column widths when cells wrap (pandoc rule)."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("-" * w for w in widths) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def html_table(header: list[str], rows: list[list[str]], numeric: set[int]) -> str:
    """Same table for the web page; numeric columns right-aligned (site.css `.n`)."""
    def cell(tag: str, i: int, v: str) -> str:
        v = html.escape(v).replace("`", "")
        return f"<{tag}{' class=\"n\"' if i in numeric else ''}>{v}</{tag}>"
    head = "<tr>" + "".join(cell("th", i, h) for i, h in enumerate(header)) + "</tr>"
    body = "".join("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table>{head}{body}</table></div>'


SCENARIO_NAMES = {
    "freq_125": "Event frequency × 1.25", "sev_115": "Event severity × 1.15", "tail_heavy": "Heavier tail (GPD above median, ξ + 0.1)",
    "coc_08": "Reinsurer CoC 8%", "coc_12": "Reinsurer CoC 12%", "d_03": "Diversification d = 0.3", "d_07": "Diversification d = 0.7",
    "h_08": "Cedent hurdle 8%", "h_12": "Cedent hurdle 12%", "u0_250": "Event threshold USD 250m", "cpi_only": "CPI-only as-if",
    "calibration_from_2010": "Calibration from 2010", "attritional_lognormal": "Lognormal attritional",
    "severity_lognormal": "Lognormal severity", "event_cap_5x": "Event cap 5× largest event", "d_10": "No diversification (d = 1)",
}


def table_data(nums: dict) -> dict:
    """name -> (header, rows, markdown column widths, numeric column indices), all built from outputs."""
    rec = json.loads((OUTPUTS_DIR / "recommendation.json").read_text())
    metrics = pd.read_csv(TABLES_DIR / "programme_metrics.csv").set_index("programme_id")
    st = pd.read_csv(TABLES_DIR / "recommendation_stability.csv")
    sens = pd.read_csv(TABLES_DIR / "sensitivities.csv")
    top = pd.read_csv(TABLES_DIR / "top_events.csv")
    ep = pd.read_csv(TABLES_DIR / "ep_curves.csv")
    lp = pd.read_csv(TABLES_DIR / "layer_pricing.csv")
    out = {}

    r = rec["recommended"]
    rows = []
    if r["q"] > 0:
        qs = pd.read_csv(TABLES_DIR / "qs_pricing.csv").set_index("q").loc[r["q"]]
        rows.append([f"Quota share {r['q']:.0%}", "–", "–", "all losses", "–", f"{r['q']:.0%}", "–", f"{qs['premium']:,.0f}", "–", "–"])
    for i, l in enumerate(r["layers"], 1):
        rows.append([f"Cat XoL {i}", f"{l['attach']:,.0f}", f"{l['exhaust']:,.0f}", f"1-in-{l['attach_rp']} to 1-in-{l['exhaust_rp']}", f"{l['ap']:.1%}",
                     f"{l['placement']:.0%}", str(l["n_reinst"]), f"{l['premium']:,.0f}", f"{l['rol']:.1%}", f"{l['multiple']:.1f}×"])
    out["layers"] = (["Treaty", "Attach (USD m)", "Exhaust (USD m)", "Return periods", "AP", "Share", "Reinst.", "Premium (USD m)", "ROL", "Multiple"],
                     rows, [16, 10, 10, 18, 7, 7, 7, 10, 7, 8], {1, 2, 4, 5, 6, 7, 8, 9})

    rows = []
    for lab, pid in (("Budget-first", rec["choices"]["budget_first"]), (f"Balanced (h = {nums['hurdle']:.0%})", nums["recommended_id"]),
                     ("Protection-first", rec["choices"]["protection_first"])):
        m = metrics.loc[pid]
        rows.append([lab, describe(pid), f"{m['net_cost']:,.0f}", f"{m['ec_net']:,.0f}", f"{m['relief_pct']:.1%}", f"{m['implied_coc']:.1%}"])
    out["choices"] = (["Choice", "Programme", "Net cost (USD m)", "Net EC (USD m)", "Relief", "Implied CoC"], rows, [14, 46, 12, 12, 8, 9], {2, 3, 4, 5})

    rows = []
    for h in rec["hull"]:
        mc = "–" if pd.isna(h["marginal_coc"]) else f"{h['marginal_coc']:.1%}"
        rows.append([describe(h["programme_id"]), f"{h['net_cost']:,.0f}", f"{h['ec_net'] / 1e3:,.1f}", f"{h['relief_pct']:.0%}", mc])
    out["hull"] = (["Hull point", "Net cost (USD m)", "Net EC (USD bn)", "Relief", "Marginal CoC"], rows, [52, 12, 12, 8, 10], {1, 2, 3, 4})

    rows = []
    for df in (st[st["scenario"] != "base"], sens):
        for s in df.itertuples():
            same = "yes" if s.same_as_base else ("placement only" if _structure(s.balanced_id) == _structure(nums["recommended_id"]) else "no")
            rows.append([SCENARIO_NAMES.get(s.scenario, s.scenario), f"`{s.balanced_id}`", same, f"{s.base_rec_relief_pct:.0%} / {s.base_rec_implied_coc:.1%}"])
    out["stress"] = (["Scenario", "Balanced choice", "Same contract", "Recommended: relief / CoC"], rows, [30, 34, 14, 18], {3})

    rows = [[f"{e.name}{' (holdout)' if e.period == 'holdout' else ''}", str(e.year), f"{e.loss_nominal:,.0f}", f"{e.loss_asif:,.0f}"]
            for e in top.head(6).itertuples()]
    out["events"] = (["Event", "Year", "Nominal (USD m)", "As-if 2025 (USD m)"], rows, [30, 8, 14, 14], {1, 2, 3})

    out["ep"] = (["Return period"] + [str(x) for x in ep["return_period"]],
                 [["OEP (USD bn)"] + [f"{x / 1e3:.1f}" for x in ep["oep"]], ["AEP (USD bn)"] + [f"{x / 1e3:.1f}" for x in ep["aep"]]],
                 [14] + [7] * len(ep), set(range(1, len(ep) + 1)))

    d = lp[(lp["q"] == 0) & (lp["c"] == 1.0) & (lp["n_reinst"] == 1)].sort_values(["attach", "exhaust"])
    rows = [[f"1-in-{l.attach_rp} to 1-in-{l.exhaust_rp}", f"{l.attach:,.0f}–{l.exhaust:,.0f}", f"{l.ap:.1%}", str(l.years_hit),
             f"{l.burning_cost:,.0f}", f"{l.el:,.0f}", f"{l.premium:,.0f}", f"{l.rol:.1%}", f"{l.multiple:.1f}×"] for l in d.itertuples()]
    out["pricing"] = (["Layer", "USD m", "AP", "Years hit", "Burning cost", "Modelled EL", "Premium", "ROL", "Multiple"],
                      rows, [18, 16, 7, 7, 10, 10, 9, 7, 8], {1, 2, 3, 4, 5, 6, 7, 8})
    return out


def tables(nums: dict) -> dict:
    """{{tbl_*}} Markdown tables for the memo and {{html_*}} tables for the web page."""
    out = {}
    for name, (header, rows, widths, numeric) in table_data(nums).items():
        out[f"tbl_{name}"] = md_table(header, rows, widths)
        out[f"html_{name}"] = html_table(header, rows, numeric)
    return out


def fill(template: str, nums: dict) -> str:
    """Replace {{key}} / {{key:fmt}} placeholders; an unknown key raises KeyError."""
    def sub(m):
        key, fmt = m.group(1), m.group(2)
        v = nums[key]
        return format(v, fmt) if fmt else str(v)
    return re.sub(r"\{\{(\w+)(?::([^}]*))?\}\}", sub, template)


def run() -> None:
    nums = collect()
    write_json(nums, OUTPUTS_DIR / "cv_numbers.json")
    allvals = {**nums, **tables(nums)}
    (ROOT / "README.md").write_text(fill((TEMPLATES / "README.md.tpl").read_text(), allvals))
    (REPORTS_DIR / "memo.qmd").write_text(fill((TEMPLATES / "memo.qmd.tpl").read_text(), allvals))
    figs = REPORTS_DIR / "_figures"          # Typst cannot read files outside the memo's folder
    figs.mkdir(exist_ok=True)
    for f in ("hero_1_ep_curves.png", "hero_2_gross_net.png", "hero_3_frontier.png"):
        shutil.copy(FIGURES_DIR / f, figs / f)
    build_site(allvals)
    if shutil.which("quarto"):
        res = subprocess.run(["quarto", "render", "memo.qmd"], cwd=REPORTS_DIR, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-2000:])
    shutil.copy(REPORTS_DIR / "memo.pdf", SITE_DIR / "memo.pdf")
    print(f"cv_numbers.json ({len(nums)} keys), README.md, reports/memo.pdf and site/ written", flush=True)


SITE_DIR = ROOT / "site"
SITE_CHARTS = ["hero_1_ep_curves.png", "hero_2_gross_net.png", "hero_3_frontier.png", "m1_tiv_by_state.png",
               "m3_severity_qq_survival.png", "m6_rol_vs_ap.png", "m10_rol_vs_ap_benchmark.png"]


def build_site(vals: dict) -> None:
    """Static project page for GitHub Pages (site/), filled from the same numbers as README and memo."""
    charts = SITE_DIR / "assets" / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    for f in SITE_CHARTS:
        shutil.copy(FIGURES_DIR / f, charts / f)
    shutil.copy(ROOT / "excel" / "reinsurance_checks.xlsx", SITE_DIR / "assets" / "reinsurance_checks.xlsx")
    (SITE_DIR / "index.html").write_text(fill((TEMPLATES / "site.html.tpl").read_text(), vals))
