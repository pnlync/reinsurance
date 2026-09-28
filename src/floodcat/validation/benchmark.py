"""M10 market benchmark: FEMA traditional placements and FloodSmart Re cat bonds (SPEC §7, §9 M10).

Order-of-magnitude comparison only. Nothing here feeds M3-M9, and no other module imports this one.
Comparison is by attachment probability, not dollars: FEMA's tower covers the national NFIP and all
floods; FloodSmart Re covers named storms only.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd

from floodcat.utils.io import FIGURES_DIR, MARKET_DIR, OUTPUTS_DIR, TABLES_DIR, write_json
from floodcat.utils.plotting import finish

AP_BAND = (0.04, 0.09)


def fema_placements() -> tuple[pd.DataFrame, pd.DataFrame]:
    p = pd.read_csv(MARKET_DIR / "placements.csv")
    p["limit_usd_m"] = p["share"] * (p["layer_high_usd_bn"] - p["layer_low_usd_bn"]) * 1000
    y = p.groupby("year").agg(total_limit_usd_m=("limit_usd_m", "sum"), total_premium_usd_m=("total_premium_usd_m", "sum"),
                              attachment_usd_bn=("layer_low_usd_bn", "min"), exhaustion_usd_bn=("layer_high_usd_bn", "max"),
                              n_layers=("share", "size"), min_share=("share", "min"), max_share=("share", "max")).reset_index()
    y["rol"] = y["total_premium_usd_m"] / y["total_limit_usd_m"]
    return p, y


def cat_bonds() -> pd.DataFrame:
    c = pd.read_csv(MARKET_DIR / "cat_bonds.csv")
    c["multiple"] = c["spread"] / c["el"]
    return c


def run() -> None:
    p, fema = fema_placements()
    cb = cat_bonds()
    lp = pd.read_csv(TABLES_DIR / "layer_pricing.csv")
    rec = json.loads((OUTPUTS_DIR / "recommendation.json").read_text())
    band = lp[lp["ap"].between(*AP_BAND)]

    rows = [{"source": "FEMA traditional", "id": str(r.year), "attach": f"USD {r.attachment_usd_bn:g}bn", "ap": None, "el": None,
             "rol_or_spread": r.rol, "multiple": None, "note": f"{r.n_layers} layers, shares {r.min_share:.1%}–{r.max_share:.1%}, limit USD {r.total_limit_usd_m:,.1f}m"}
            for r in fema.itertuples()]
    rows += [{"source": "FloodSmart Re", "id": f"{r.series} {r['class']}", "attach": f"USD {r.attach_usd_bn:g}–{r.exhaust_usd_bn:g}bn", "ap": r.ap,
              "el": r.el, "rol_or_spread": r.spread, "multiple": r.multiple, "note": f"named storm only, {r.modelling_agent}"}
             for _, r in cb.iterrows()]
    rows += [{"source": "Model (technical)", "id": r.layer_id, "attach": f"USD {r.attach:,.0f}m", "ap": r.ap, "el": r.el / (r.c * r.limit),
              "rol_or_spread": r.rol, "multiple": r.multiple, "note": f"{r.attach_rp}–{r.exhaust_rp} yr, c {r.c:.0%}, n {r.n_reinst}"}
             for r in band.itertuples()]
    out = pd.DataFrame(rows)
    out.to_csv(TABLES_DIR / "benchmark.csv", index=False)

    summary = {
        "fema_rol": {str(r.year): r.rol for r in fema.itertuples()},
        "fema_limit_usd_m": {str(r.year): r.total_limit_usd_m for r in fema.itertuples()},
        "cat_bond_multiple": {f"{r.series} {r['class']}": r.multiple for _, r in cb.iterrows()},
        "model_band": {"ap_range": AP_BAND, "n_layers": int(len(band)),
                       "rol_min": float(band["rol"].min()) if len(band) else None, "rol_max": float(band["rol"].max()) if len(band) else None,
                       "rol_median": float(band["rol"].median()) if len(band) else None,
                       "multiple_min": float(band["multiple"].min()) if len(band) else None, "multiple_max": float(band["multiple"].max()) if len(band) else None,
                       "multiple_median": float(band["multiple"].median()) if len(band) else None},
        "recommended_layers": [{k: l[k] for k in ("layer_id", "ap", "rol", "multiple", "placement")} for l in rec["recommended"]["layers"]],
        "bonus_floodsmart_apples_to_apples": "not run: the pipeline has no named-storm filter in config, so it would need code changes (SPEC §9 M10)",
    }
    write_json(summary, TABLES_DIR / "benchmark_summary.json")
    plot(lp, fema, cb)
    print(f"benchmark: {len(band)} model layers with AP in {AP_BAND}; FEMA ROL 2025 {summary['fema_rol']['2025']:.1%}", flush=True)


def plot(lp: pd.DataFrame, fema: pd.DataFrame, cb: pd.DataFrame) -> None:
    d = lp[(lp["q"] == 0) & (lp["n_reinst"] == 1) & (lp["c"] == 1.0)]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(d["ap"] * 100, d["rol"] * 100, s=25, color="#2f5d8a", label="Model layers: technical ROL (QS 0%, c 100%, 1 reinst.)")
    ax.scatter(cb["ap"] * 100, cb["spread"] * 100, s=60, marker="D", color="#c0573e", label="FloodSmart Re: spread (named storm, national)")
    for _, r in cb.iterrows():
        ax.annotate(f"{r.series} {r['class']}", (r.ap * 100, r.spread * 100), fontsize=7, xytext=(4, 4), textcoords="offset points")
    for r in fema[fema["year"] >= 2023].itertuples():
        ax.hlines(r.rol * 100, AP_BAND[0] * 100, AP_BAND[1] * 100, colors="#3a8a5f", lw=1.5)
        ax.annotate(f"FEMA {r.year} ROL", (AP_BAND[1] * 100, r.rol * 100), fontsize=7, xytext=(3, -3), textcoords="offset points", color="#3a8a5f")
    ax.axvspan(AP_BAND[0] * 100, AP_BAND[1] * 100, color="0.9", zorder=0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%g"))
    ax.set_xlabel("Attachment probability (%, log scale)")
    ax.set_ylabel("Rate on line / spread (%, log scale)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    finish(fig, ax, "Technical ROL vs public market benchmarks (order of magnitude only)")
    fig.savefig(FIGURES_DIR / "m10_rol_vs_ap_benchmark.png", dpi=150)
    plt.close(fig)
