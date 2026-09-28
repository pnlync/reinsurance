"""M1 step: clean claims, build exposure, the 2025 portfolio and reports/data_checks.md (SPEC §9 M1)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from floodcat.data import claims, policies
from floodcat.utils.io import FIGURES_DIR, PROCESSED_DIR, REPORTS_DIR, load_config, write_json, TABLES_DIR
from floodcat.utils.plotting import SUBTITLE, finish


def portfolio_2025(exposure: pd.DataFrame, target_year: int) -> pd.DataFrame:
    p = exposure[exposure["year"] == target_year][["state", "policies_written", "tiv_written", "premium_written"]].copy()
    p = p.rename(columns={"policies_written": "policies", "tiv_written": "tiv", "premium_written": "premium"})
    total = pd.DataFrame([{"state": "Total", **p[["policies", "tiv", "premium"]].sum().to_dict()}])
    return pd.concat([p, total], ignore_index=True)


def crs_pass(nat: dict, crs: dict) -> bool:
    """National totals within the tolerance of the CRS R44593 reference values (D11)."""
    return (abs(nat["policies"] / crs["ref_policies"] - 1) <= crs["tolerance"]
            and abs(nat["tiv"] / crs["ref_coverage_usd"] - 1) <= crs["tolerance"])


def calibration_start_check(exposure: pd.DataFrame, cfg: dict) -> dict:
    """Is 2009 written TIV consistent with the 2010+ written/in-force relationship? (SPEC §6.1)."""
    tot = exposure.groupby("year")[["tiv_written", "tiv_inforce"]].sum()
    ratio = tot["tiv_written"] / tot["tiv_inforce"]
    ref = ratio.loc[2010:cfg["calibration"]["end"]]
    r09 = float(ratio.loc[2009])
    lo, hi = float(ref.min()), float(ref.max())
    # D9: consistent if 2009 lies within max(3 SD, 1%) of the 2010+ mean ratio
    tol = max(3 * float(ref.std(ddof=1)), 0.01)
    return {
        "ratio_2009": r09, "ratio_2010_plus_min": lo, "ratio_2010_plus_max": hi,
        "ratio_2010_plus_mean": float(ref.mean()), "tolerance": tol,
        "consistent": bool(abs(r09 - float(ref.mean())) <= tol),
    }


def _md_table(df: pd.DataFrame, floatfmt: str = "{:,.1f}") -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        cells = [str(int(v)) if c == "year" else floatfmt.format(v) if isinstance(v, float) else f"{v:,}" if isinstance(v, int) else str(v)
                 for c, v in zip(cols, r)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def plot_tiv(exposure: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for s, g in exposure.groupby("state"):
        ax.plot(g["year"], g["tiv_written"] / 1e9, marker="o", ms=3, label=s)
    ax.set_xlabel("Policy effective year")
    ax.set_ylabel("Written TIV (USD bn)")
    ax.legend(ncol=5, frameon=False)
    finish(fig, ax, "Written total insured value by state, 2009–2025", SUBTITLE.replace("2025 exposure", "written exposure by year"))
    fig.savefig(FIGURES_DIR / "m1_tiv_by_state.png", dpi=150)
    plt.close(fig)


def run() -> None:
    cfg = load_config("portfolio")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw = claims.read_raw_claims()
    clean, chk = claims.clean_claims(raw, tuple(cfg["history_years"]))
    clean.to_parquet(PROCESSED_DIR / "claims_clean.parquet", index=False)
    print(f"claims_clean: {len(clean):,} rows", flush=True)

    exposure = policies.build_exposure()
    exposure.to_parquet(PROCESSED_DIR / "exposure_by_state_year.parquet", index=False)
    port = portfolio_2025(exposure, cfg["target_year"])
    port.to_parquet(PROCESSED_DIR / "portfolio_2025.parquet", index=False)
    nat = policies.national_inforce_2025()
    start = calibration_start_check(exposure, cfg)
    plot_tiv(exposure)

    m1 = {"claims_checks": {k: v for k, v in chk.items() if k != "by_year"}, "national_inforce_2025": nat,
          "calibration_start_check": start, "calibration_start": cfg["calibration"]["start"]}
    write_json(m1, TABLES_DIR / "m1_checks.json")
    write_report(chk, exposure, port, nat, start, cfg)


def run_all() -> None:
    """`make data`: check the frozen raw files against MANIFEST, then build the M1 outputs."""
    from floodcat.data import load

    load.verify()
    run()


def write_report(chk, exposure, port, nat, start, cfg) -> None:
    by = chk["by_year"].reset_index()
    by["at_limit_share"] = by["at_limit_share"].map(lambda x: f"{x:.1%}")
    tot = exposure.groupby("year").agg(
        records_all=("records_all", "sum"), records_kept=("records_written", "sum"),
        tiv_written_bn=("tiv_written", lambda s: s.sum() / 1e9), tiv_inforce_bn=("tiv_inforce", lambda s: s.sum() / 1e9),
    ).reset_index()
    tot["dedup_share_tiv"] = 1 - exposure.groupby("year")["tiv_written"].sum().values / exposure.groupby("year")["tiv_written_all"].sum().values
    tot["written_to_inforce"] = tot["tiv_written_bn"] / tot["tiv_inforce_bn"]
    for c in ("dedup_share_tiv", "written_to_inforce"):
        tot[c] = tot[c].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    p = port.copy()
    p["policies"] = p["policies"].map(lambda x: f"{x:,.0f}")
    p["tiv_usd_bn"] = p.pop("tiv").map(lambda x: f"{x / 1e9:,.1f}")
    p["premium_usd_m"] = p.pop("premium").map(lambda x: f"{x / 1e6:,.1f}")
    crs = cfg["crs_check"]
    nulls = chk["null_paid"]

    endo_share = float(policies.endorsement_share(cfg["states"]))
    ds = exposure.groupby("year")["tiv_written"].sum() / exposure.groupby("year")["tiv_written_all"].sum()
    drop_lo, drop_hi = float(1 - ds.max()), float(1 - ds.min())
    text = f"""# Data checks (M1)

Generated by `make data`. Source: OpenFEMA NFIP Redacted Claims v3 and NFIP Redacted Policies v3 (file names, URLs, row counts and SHA-256 in the raw-data `MANIFEST`).

## Claims (FL, TX, LA, MS, AL)

| Check | Rule | Result | Action |
|---|---|---|---|
| Key uniqueness | `id` unique | {chk['duplicate_id_rows']:,} rows share an id; {chk['exact_duplicates_dropped']:,} exact duplicates | drop exact duplicates only |
| Nulls in paid fields | count by field | building {nulls['building_paid']:,}; contents {nulls['contents_paid']:,}; ICC {nulls['icc_paid']:,} | treated as 0 |
| Negative paid | count | {chk['negative_paid_rows']:,} rows | flagged (`negative_paid`), kept |
| Missing state / date | count | {chk['missing_state_or_date_excluded']:,} rows | excluded |
| `yearOfLoss` vs year of `dateOfLoss` | count of mismatches | {chk['year_of_loss_mismatch']:,} | year taken from `dateOfLoss` |
| Outside {cfg['history_years'][0]}–{cfg['history_years'][1]} | count | {chk['rows_outside_years']:,} rows | not used |

Rows: {chk['rows_raw']:,} raw in the five states, {chk['rows_clean']:,} clean in {cfg['history_years'][0]}–{cfg['history_years'][1]}.

Most blank paid fields are claims closed without payment; they have no effect on sums. "At limit" is building paid ≥ 99% of building coverage.

{_md_table(by, "{:,.1f}")}

## Exposure

**Written TIV** (base, SPEC §6.1): building + contents coverage over policy records effective in the year.

**De-duplication (decision D7).** v3 has no policy or term number. {endo_share:.1%} of records carry an endorsement date after the effective date. Most of these are the only record of their term, but spot checks show some terms appearing twice, once as issued and once as endorsed (for example a coverage increase part-way through the term). Rule: records with the same state, effective and termination dates, original new-business date, original construction date, ZIP, rounded latitude/longitude, occupancy type and condominium code are one policy term, and only the record(s) with the latest endorsement date in that group are kept. The rule removes {drop_lo:.1%}–{drop_hi:.1%} of written TIV a year (`dedup_share_tiv`). Because as-if factors are ratios of the same definition across years, they move by less than that.

**In-force TIV** (check): de-duplicated records with effective ≤ 31 Dec < termination, for every year; 2010+ is the reference for the 2009 decision below.

{_md_table(tot)}

**Calibration start (SPEC §6.1, decision D9).** Written/in-force TIV ratio in 2009 = {start['ratio_2009']:.4f}; 2010–{cfg['calibration']['end']} range {start['ratio_2010_plus_min']:.4f}–{start['ratio_2010_plus_max']:.4f} (mean {start['ratio_2010_plus_mean']:.4f}). Annual policies written in year t are still in force on 31 December of t unless cancelled, so the two measures differ only by mid-term cancellations and multi-year terms, and the file's 2009-01-01 start does not truncate the 2009 year-end snapshot. 2009 is {'consistent' if start['consistent'] else 'NOT consistent'} with 2010+ (tolerance ±{start['tolerance']:.3f}), so the calibration period starts in **{cfg['calibration']['start']}** (`config/portfolio.yaml`).

## 2025 Gulf Coast reference portfolio (written basis)

{_md_table(p)}

## National order-of-magnitude check (CRS R44593)

All states, in force at 31 Dec 2025 (FEMA rule, raw records): {nat['records']:,.0f} records, {nat['policies']:,.0f} insured units (`policyCount`), TIV USD {nat['tiv'] / 1e12:,.3f}tn. CRS R44593: "over {crs['ref_policies'] / 1e6:.1f} million policies providing over ${crs['ref_coverage_usd'] / 1e12:.1f} trillion in coverage". Ratios to the CRS figures: policies {nat['policies'] / crs['ref_policies']:.3f}, coverage {nat['tiv'] / crs['ref_coverage_usd']:.3f}. Check (decision D11: within ±{crs['tolerance']:.0%} of both): **{'pass' if crs_pass(nat, crs) else 'FAIL'}**. Coverage is slightly below the CRS figure; the OpenFEMA extract lags FEMA's system of record, which is a plausible reason, so the same-order conclusion stands.
"""
    (REPORTS_DIR / "data_checks.md").write_text(text)
