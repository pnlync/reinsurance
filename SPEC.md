# SPEC: Flood Catastrophe Reinsurance & Capital Optimisation

A reinsurance decision study for a stylised Gulf Coast flood portfolio built from public NFIP data. Historical flood events from 2009–2023 are restated to 2025 exposure and turned into a stochastic annual loss model. Quota share and catastrophe excess-of-loss programmes are applied to the simulated years, priced on a technical basis, and compared on net cost against the 99.5% one-year economic capital they release. The output is a cost–capital frontier and a recommended programme, tested for robustness and compared in magnitude with FEMA's public reinsurance placements.

The whole project answers one question:

> For a flood insurer exposed to catastrophe accumulation, what reinsurance programme should it buy, how much should it pay, and how much tail risk and economic capital does that programme remove?

This file is the contract for the coding agent. The companion guide (Chinese, "Flood Catastrophe Reinsurance & Capital Optimisation — Final Guide") explains every concept, module by module, and contains the worked toy example used in section 11. If this file is unclear, contradicts itself or looks wrong, stop and ask. Do not guess. **Do not add any feature that is not in this file; if something seems necessary, ask first.**

Disclaimer to carry in the README and every report:

> Data: OpenFEMA NFIP Redacted Claims and NFIP Redacted Policies. This product uses the FEMA OpenFEMA API, but is not endorsed by FEMA. The Federal Government or FEMA cannot vouch for the data or analyses derived from these data after the data have been retrieved from the Agency's website(s). The Gulf Coast portfolio is a stylised insurance portfolio calibrated to the exposure and claims experience observed in the NFIP Gulf states; it is not intended to reproduce the finances of the NFIP itself. Reinsurance prices are indicative technical premiums, not market quotes. Economic capital is a 99.5% one-year proxy, not a Solvency II SCR.

---

## 1. How we work

1. One module at a time, in the order of section 9 (M0, M1, ...). Do not start the next module until the user replies "continue".
2. Before coding a module, explain it in Chinese (max 300 words): the business question it answers, inputs, outputs, key formulas, the judgement calls involved, common mistakes. Wait for the user's OK.
3. Write the module's acceptance tests first (`tests/test_m<n>_*.py`, pytest). After implementing, report each test as PASS or FAIL with the numbers.
4. Show 3–5 key numbers and at most 2 charts, each with one sentence saying whether it looks reasonable and why.
5. Ask the module's teach-back questions (listed per module) and correct the user's answers.
6. Commit once per module with the message `M<n>: <module name>`.
7. Gates (section 9) end with the user answering the gate questions in the guide.
8. All parameters live in `config/*.yaml`. No hard-coded numbers in `src/` except mathematical constants.

## 2. Business questions

1. What does the Gulf Coast reference portfolio look like at 2025 exposure (policies, total insured value, premium by state)?
2. Which historical flood events hit it, and what would each cost on the 2025 portfolio?
3. What is the portfolio's gross catastrophe risk profile (OEP, AEP, VaR, TVaR, economic capital)?
4. What do quota share, Cat XoL layers and layered towers recover, and what is an indicative technical price for each?
5. For each programme: net cost, capital relief, implied cost of capital.
6. Which programmes are efficient, which should management choose under different risk appetites, and does the recommendation survive validation and stress?
7. How do the modelled layer prices compare in magnitude with FEMA's public placements?

Framing for all reports: **the subject is the reinsurance decision.** Data engineering, validation and the market benchmark support it and never lead the story. Never write "optimal programme", "validated catastrophe model", "vendor-grade", "Solvency II SCR" or "market quote".

## 3. Scope

In scope: NFIP claims and policies for FL, TX, LA, MS, AL; state × year exposure; event catalogue from `floodEvent`; as-if restatement by state TIV ratio; annual loss model L = A + ΣS (frequency, severity, attritional); 100,000-year simulation with event hierarchy; OEP / AEP; no reinsurance, quota share, Cat XoL single layer, two-layer tower, placement (coinsurance), 0 or 1 reinstatement, QS-inures-first; burning cost; modelled expected loss; technical premium; gross vs net metrics; 99.5% one-year economic capital proxy; capital relief; net cost; implied cost of capital; programme grid from OEP return periods; cost–capital Pareto frontier; Budget-first / Balanced / Protection-first; temporal holdout; leave-one-major-event-out; year bootstrap; stress tests; FEMA traditional reinsurance benchmark; Excel check of treaty mechanics; memo, README, `cv_numbers.json`.

Explicitly out of scope (do not implement, do not suggest): Danish Fire data; any link to other projects (no reserving data, no `one_year_cdr_sims.csv`, no reserve risk, no enterprise aggregation, no copulas, no ADC/LPT); a second cedent; pre-2009 exposure reconstruction; per-risk XoL; git-tag "blind lock"; development of open events (chain ladder or similar); calibrating the model to vendor figures; full Solvency II SCR; IFRS 17; AWS or distributed computing; machine learning; climate or physical hazard models; web development beyond an optional static page.

Optional (only where marked in section 9): FloodSmart Re apples-to-apples comparison; credibility blend; CPI-only as-if; u₀ sensitivity; calibration from 2010; counterparty haircut; static Quarto page.

## 4. Data, dates and conventions

### 4.1 Sources

| Item | Value |
|---|---|
| Claims | OpenFEMA "NFIP Redacted Claims" — v3 (`NfipClaims`) if complete, else v2 (`FimaNfipClaims`). Pages: https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3 , https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2 |
| Policies | OpenFEMA "NFIP Redacted Policies" — v3 (`NfipPolicies`) if complete, else v2 (`FimaNfipPolicies`). Pages: https://www.fema.gov/openfema-data-page/nfip-redacted-policies-v3 , https://www.fema.gov/openfema-data-page/fima-nfip-redacted-policies-v2 |
| Field dictionary | `https://www.fema.gov/api/open/v1/OpenFemaDataSetFields?$filter=openFemaDataSet eq '<name>' and datasetVersion eq <v>` |
| Access | Prefer the bulk file (parquet if offered) from the dataset page. Otherwise the API `https://www.fema.gov/api/open/v<v>/<EntityName>` with `$select` (needed fields only), `$filter` by state, and paging. Record the exact URLs used. |

Download into `data/raw/`, record file name, URL, dataset version, download date, row count and SHA-256 in `data/raw/MANIFEST`. The raw files are frozen: later FEMA refreshes are not pulled in.

Expected fields (v2 names; confirm against the dictionary for the version used and record the mapping in `config/fields.yaml`; if a field is missing or renamed, stop and report):

| Dataset | Field | Use |
|---|---|---|
| Claims | `id` | record key (check uniqueness) |
| Claims | `dateOfLoss`, `yearOfLoss` | event dating, calendar year |
| Claims | `floodEvent` | event label (blank = no named event) |
| Claims | `state` | state filter, state split |
| Claims | `amountPaidOnBuildingClaim`, `amountPaidOnContentsClaim`, `amountPaidOnIncreasedCostOfComplianceClaim` | claim loss |
| Claims | `totalBuildingInsuranceCoverage`, `totalContentsInsuranceCoverage` | data checks (share at limit) |
| Policies | `propertyState` | state |
| Policies | `policyEffectiveDate`, `policyTerminationDate` | exposure year; in force = effective ≤ d < termination |
| Policies | `totalBuildingInsuranceCoverage`, `totalContentsInsuranceCoverage` | TIV |
| Policies | premium field (e.g. `totalInsurancePremiumOfThePolicy`) | portfolio premium (context only) |
| Policies | `policyCount` | policy count |
| Policies | policy term identifier, if any | de-duplication of written exposure |

Units: USD, nominal, as reported. Outputs in USD millions to one decimal unless stated.

### 4.2 Dates and periods (`config/portfolio.yaml`)

| Item | Value |
|---|---|
| States | FL, TX, LA, MS, AL |
| Target exposure year T | 2025 |
| Calibration period | 2009–2023 (M1 may change the start to 2010, see M1) |
| Holdout / discussion | 2024–2025 (2024 flagged immature; never used in calibration) |
| Temporal back-test | fit 2009–2018, test 2019–2023 |
| Event year | calendar year of the earliest `dateOfLoss` in the event |

### 4.3 Conventions

- Claim loss for claim i: `claim_loss = building_paid + contents_paid + icc_paid`; nulls treated as 0 and counted in `data_checks.md`; negative values flagged, kept, and counted.
- Only claims in the five states are used. An event's loss is the sum over the five states only.
- Every loss used in modelling is on the 2025 as-if basis unless its column name ends in `_nominal` or `_cpi`.
- Empirical risk measures on a sample x_1..x_n sorted ascending as x_(1) ≤ ... ≤ x_(n):

```
VaR_p(x)  = x_(ceil(n * p))
TVaR_p(x) = mean of { x_(i) : i >= ceil(n * p) }
EC_99.5   = VaR_0.995(L) - mean(L)
OEP(y)    = share of years with max event loss > y
AEP(y)    = share of years with annual loss > y
return period of an exceedance probability e = 1 / e
OEP^-1(e) = VaR_(1-e) of the annual maximum event loss (years with no event have maximum 0)
```

- Seeds in `config/simulation.yaml`. Every simulated output records its seed and the git hash.
- Every public number is written by the pipeline into `outputs/`; nothing is typed by hand into the README, memo or CV.

## 5. Configuration files

### 5.1 `config/modelling.yaml`

| Item | Value |
|---|---|
| Event threshold u₀ | USD 100m as-if 2025 loss in the five states (candidate 250m; user confirms in M2; 250m is a sensitivity) |
| Frequency candidates | Poisson; Negative Binomial |
| Frequency rule | Poisson unless the likelihood-ratio statistic 2(ℓ_NB − ℓ_Pois) > 2.71 (5% test with boundary correction) |
| Severity candidates | lognormal, log-logistic (Fisk), Burr XII; all fitted with left truncation at u₀ |
| Severity rule | lowest AIC among candidates whose tail QQ plot and fitted vs empirical quantiles (top 5 events) are acceptable; judgement written in `reports/model_selection.md` |
| GPD rule | body + GPD may be the base only if at least 25 events exceed the GPD threshold and the mean excess plot and parameter-stability plot support it; otherwise GPD is used only in the tail stress |
| Event cap | each simulated event capped at 3 × the largest as-if calibration event; report the share of simulated events capped |
| Attritional | base: bootstrap of calibration-year as-if A_t; sensitivity: lognormal by moments |

### 5.2 `config/simulation.yaml`

| Item | Value |
|---|---|
| Years (base) | 100,000 |
| Convergence check | 200,000; tolerance 2% on gross VaR 99.5 and on the recommended programme's capital relief |
| Batches for standard errors | 20 |
| Seed | 20261001 (bootstrap and stresses derive seeds deterministically from it) |
| Bootstrap | B = 200 replicates × 20,000 years |

### 5.3 `config/reinsurance.yaml`

| Item | Value |
|---|---|
| Quota share q | 0, 0.10, 0.20 (pure QS programmes: 0.10, 0.20 with no XoL) |
| Attachment return periods (OEP) | 5, 10, 20, 50 |
| Exhaustion return periods (OEP) | 50, 100, 200, 250; must exceed the attachment return period |
| Structure | single layer; or two-layer tower split at return period 50 or 100 where strictly between attachment and exhaustion |
| Placement c | 0.80, 1.00 (same c for both layers of a tower) |
| Reinstatements n | 0, 1; reinstatement rate 100%, pro rata as to amount |
| Inuring | QS first; XoL applies to (1 − q) × event loss; attritional losses are not covered by XoL |
| Rounding | attachments and exhaustion points rounded to the nearest USD 10m after computation |
| Reinsurer cost of capital CoC_R | 0.10 (stress 0.08, 0.12) |
| Diversification factor d | 0.5 (stress 0.3, 0.7) |
| XoL expense load e | 0.10 of premium |
| QS expense load e_QS | 0.03 of premium |
| Cedent hurdle h | 0.10 (decision sensitivity 0.08, 0.12) |
| Budget-first minimum relief | 25% of gross EC |

### 5.4 `config/stress.yaml`

| Scenario | Change |
|---|---|
| freq_125 | event frequency parameter × 1.25 (λ; for NB scale the mean, keep the dispersion) |
| sev_115 | every simulated event loss × 1.15 (before the cap) |
| tail_heavy | severity replaced by body + GPD above the median calibration event, ξ = ξ̂ + 0.1 |
| coc_08, coc_12 | CoC_R = 0.08, 0.12 |
| d_03, d_07 | d = 0.3, 0.7 |
| h_08, h_12 | cedent hurdle 0.08, 0.12 (Balanced rule only) |

## 6. Data rules

### 6.1 Exposure (`src/floodcat/data/policies.py`)

- **Written TIV** (base): for state s and year t, the sum of building + contents coverage over policy records with `policyEffectiveDate` in year t, de-duplicated to one record per policy term if the data contain endorsements or corrections (describe the rule used in `data_checks.md`). Also policy count and premium on the same basis.
- **In-force TIV** (check): at 31 December of each year from 2010, the sum over records with effective ≤ date < termination.
- Written TIV is used for every as-if ratio so all years use the same definition. If 2009 written TIV is inconsistent with the 2010+ relationship between written and in-force TIV, set the calibration start to 2010, record the decision in `config/portfolio.yaml` and `reports/data_checks.md`.
- National 2025 totals (all states) must be of the same order as CRS R44593: more than 4.5m policies and more than USD 1.3tn coverage at 31 December 2025.

### 6.2 Events and attritional (`src/floodcat/events/`)

```
S_nominal[e, s]   = sum of claim_loss for claims with floodEvent = e in state s
factor[s, t]      = TIV_written[s, T] / TIV_written[s, t]
S_asif[e, s]      = S_nominal[e, s] * factor[s, t(e)]
S_asif[e]         = sum over the five states of S_asif[e, s]
event included    if S_asif[e] >= u0; otherwise its claims go to attritional
A_asif[t]         = sum over s of (non-event claims + sub-threshold event claims)[s, t] * factor[s, t]
```

- No CPI in the base case. A CPI-only column (`_cpi`, CPI-U annual average to 2025) is kept for the optional sensitivity only.
- `named_storm` flag = event name matches `hurricane|tropical storm` (case-insensitive), then reviewed by hand; the flag is used only in the M10 bonus.
- Record for every event: name, year, first and last loss date, span in days, claim count, nominal and as-if loss by state, total. Flag spans over 7 days for discussion (hours-clause point); do not split events.

## 7. Market benchmark data (`data/market/`, benchmark only)

`placements.csv` (FEMA traditional reinsurance; per layer):

| year | layer_low_usd_bn | layer_high_usd_bn | share | limit_usd_m | total_premium_usd_m | n_reinsurers | source |
|---|---|---|---|---|---|---|---|
| 2025 | 7 | 9 | 0.120334 | | 139.9 (total) | 27 | Artemis 2025-01-16 |
| 2025 | 9 | 11 | 0.258584 (derived from total limit 757.835) | | | | |
| 2024 | 7 | 9 | 0.089125 | | 121.1 (total) | 18 | Artemis 2024-01-05 |
| 2024 | 9 | 11 | 0.220625 | | | | |
| 2023 | 7 | 9 | 0.085625 | | 90.2 (total) | 18 | Artemis 2023-01-11 |
| 2023 | 9 | 11 | 0.165625 | | | | |
| 2019 | 4 | 6 | 0.14 | | 186 (total) | | FEMA press release |
| 2019 | 6 | 8 | 0.256 | | | | |
| 2019 | 8 | 10 | 0.266 | | | | |

Compute limit = share × (high − low) and check the yearly totals: 2025 757.8, 2024 619.5, 2023 502.5, 2019 1,324 (USD m). ROL = total premium ÷ total limit (2025 18.5%, 2024 19.5%, 2023 18.0%, 2019 14.0%). Check whether a 2026 placement has been announced; add it only from a primary or trade source.

`cat_bonds.csv` (FloodSmart Re; initial values at issue; national NFIP, named storm only, per occurrence, indemnity, 3-year):

| series | class | size_usd_m | attach_usd_bn | exhaust_usd_bn | ap | el | spread | modelling_agent |
|---|---|---|---|---|---|---|---|---|
| 2024-1 | A | 475 | 9 | 11 | 0.0579 | 0.0501 | 0.14 | KatRisk |
| 2024-1 | B | 100 | 8 | 9 | 0.0682 | 0.0629 | 0.1725 | KatRisk |
| 2023-1 | A | (verify) | 8 | 10 | 0.0625 | 0.0535 | 0.1625 | (verify) |

Sources: https://www.artemis.bm/deal-directory/floodsmart-re-ltd-series-2024-1/ and https://www.artemis.bm/deal-directory/floodsmart-re-ltd-series-2023-1/ . These files never feed M3–M9.

## 8. Technical definitions used across modules

Layer recovery for event e (after QS), placement c, attachment A, limit L, reinstatements n:

```
S'_e        = (1 - q) * S_e
r_e         = c * min(max(S'_e - A, 0), L)
annual cap  = (1 + n) * c * L                 recoveries accumulate in event order; stop at the cap
R_year      = min(sum_e r_e, (1 + n) * c * L)
f_year      = min(R_year / (c * L), n)        reinstated fraction of the layer
RP_year     = P * rate * f_year               reinstatement premium paid by the cedent
```

Quota share: `R_QS = q * (A_year + sum_e S_e)`.

Pricing (per layer; C = simulated annual layer recovery):

```
EL      = mean(C)
K_R     = TVaR_0.995(C) - EL
target  = (EL + CoC_R * d * K_R) / (1 - e)                 expected total premium income
P       = target / (1 + rate * mean(f))                    upfront premium
ROL     = P / (c * L)
multiple= (P + P * rate * mean(f)) / EL
P_QS    = (q * mean(L_gross) + CoC_R * d * K_QS) / (1 - e_QS),   K_QS = TVaR_0.995(q * L_gross) - q * mean(L_gross)
```

Programme metrics:

```
L_net      = L_gross - R_QS - sum_layers R + P_QS + sum_layers (P + RP)
EC         = VaR_0.995(L) - mean(L)
relief     = EC_gross - EC_net
relief_pct = relief / EC_gross
net_cost   = sum over treaties of (P + mean(RP) - mean(R))       (QS: P_QS - q * mean(L_gross))
implied_coc= net_cost / relief                                    (undefined if relief <= 0; report NA)
```

Frontier and choices:

```
dominated   programme i if some j has net_cost_j <= net_cost_i and EC_j <= EC_i with one strict
frontier    non-dominated programmes, sorted by net_cost
hull        lower convex hull of the frontier in (net_cost, EC_net) space, starting at no reinsurance
marginal CoC between consecutive hull points k-1, k = (net_cost_k - net_cost_(k-1)) / (relief_k - relief_(k-1))
Budget-first     = cheapest frontier programme with relief_pct >= budget_min_relief
Balanced(h)      = last hull point whose marginal CoC <= h (walking from no reinsurance)
Protection-first = frontier programme with the lowest EC_net
```

Programme ID in return-period terms, e.g. `QS10_A10_E200_T100_C100_R1` (QS 10%, attach 1-in-10, exhaust 1-in-200, tower split at 1-in-100, placement 100%, one reinstatement; `T0` = single layer; `XS0` = no XoL). The dollar terms of every ID are fixed from the base model and stored in `outputs/tables/programmes.csv`; validation and stress scenarios re-evaluate the same dollar contracts.

## 9. Modules

Gates: 1 after M2, 2 after M4, 3 after M6 (CV v1), 4 after M8, 5 after M11 (final CV).

### M0 Setup

- Python ≥ 3.11 with pandas, duckdb, pyarrow, numpy, scipy, statsmodels, matplotlib, pyyaml, openpyxl, pytest; `pyproject.toml`; package `floodcat` under `src/`.
- Repo skeleton (section 10); `Makefile` with targets `data events model simulate engine pricing capital frontier validate benchmark report all test`.
- All `config/*.yaml` with the values of section 5; `config/fields.yaml` stub.
- Only `floodcat.data.load` may read `data/raw/`.
- Tests: configs load and validate (types, ranges, exhaustion > attachment filter); static check that no module other than `load.py` contains the string `data/raw`.
- Teach-back: what is the one business question? What is explicitly out of scope and why?

### M1 Data and portfolio

- Download and freeze claims and policies (section 4.1); write `MANIFEST`; fill `config/fields.yaml` from the dictionary.
- Claims: filter the five states; compute `claim_loss`; checks in `reports/data_checks.md`:

| Check | Rule | Action |
|---|---|---|
| Key uniqueness | `id` unique | report duplicates; drop exact duplicates only |
| Nulls in paid fields | count by field | treat as 0 |
| Zero `claim_loss` | count by year | keep (no effect on sums) |
| Negative paid | count | flag, keep |
| Missing state / date | count | exclude, report |
| At limit | building paid ≥ 99% of building coverage | report share by year (context for limits) |
| Records by year | 2009–2025 counts | report |

- Policies: written TIV, policy count and premium by state × year (6.1); in-force TIV at year end from 2010; the 2009 decision.
- Portfolio 2025: by state and total (policies, TIV, premium).
- Outputs: `data/processed/claims_clean.parquet`, `exposure_by_state_year.parquet`, `portfolio_2025.parquet`, `reports/data_checks.md`, figure of TIV by state 2009–2025.
- Tests: `claim_loss` equals the sum of its parts row by row; exposure table has 5 states × all years with no gaps; national 2025 totals meet the CRS order-of-magnitude check; written vs in-force ratio reported for 2010–2025.
- Teach-back: why paid and not damage? Why TIV and not policy count? Why 2025 and not 2026?

### M2 Event catalogue and as-if

- Build the event table and attritional series (6.2) for 2009–2025; split calibration / holdout.
- Present the sorted list of as-if event losses; the user confirms u₀.
- Top-10 table: nominal, CPI-only and as-if losses; share of each year's loss from its largest event.
- Outputs: `data/processed/event_catalogue.parquet` (columns: `event_id, name, year, first_date, last_date, span_days, n_claims, named_storm, loss_nominal_<ST>, loss_asif_<ST>, loss_nominal, loss_cpi, loss_asif, included, period`), `attritional_by_year.parquet` (`year, a_nominal, a_asif, period`), `outputs/tables/top_events.csv`, `reports/events.md`.
- Tests: toy as-if case (section 11) reproduced; for every event, sum of state losses equals total; factor = 1 for 2025; every claim is assigned to exactly one of {included event, attritional}; sum of included event losses + attritional equals total claim loss per year (nominal and as-if).
- Teach-back: why TIV ratio and not CPI? What does "one occurrence" mean and how is it approximated here? Why is Katrina not in the calibration? What does the as-if factor assume?

**Gate 1.**

### M3 Loss model

- Frequency: counts of included events per calibration year (years with no event count as 0). Mean, variance, dispersion index; Poisson and NB MLE; rule of 5.1. Trend check: Poisson GLM of count on year; report only.
- Severity: left-truncated MLE at u₀ for each candidate (write the likelihood explicitly; do not rely on untruncated `scipy.stats.fit`):

```
loglik(theta) = sum_e [ log f(S_e; theta) - log(1 - F(u0; theta)) ]
```

  AIC, BIC, QQ plots (whole range and top 10 events), fitted vs empirical quantiles, fitted 1-in-50 / 100 / 200 single-event levels (via M4 once available). GPD diagnostics (mean excess, parameter stability, number of exceedances). Apply the rules of 5.1 and write `reports/model_selection.md`.
- Attritional: bootstrap sample of calibration as-if A_t; lognormal by moments for the sensitivity.
- Outputs: `outputs/tables/fits.json` (chosen and candidate families, parameters, log-likelihoods, AIC/BIC, n), diagnostic figures.
- Tests: truncated-MLE recovery test (section 11); Poisson MLE equals the sample mean; NB reduces to Poisson as dispersion → 0 (numerical check); chosen family recorded with rationale.
- Teach-back: what does over-dispersion mean for catastrophes? Why is GPD not the default here? Why truncated likelihood? Where does 1-in-200 information come from with 15 years?

### M4 Simulation

- For each simulated year: draw N; draw N event losses from the truncated severity (apply the cap); random order within the year; draw A. Store YELT and YLT (parquet).
- OEP and AEP at return periods 5, 10, 20, 50, 100, 200, 250; AAL; gross mean, SD, VaR 99, VaR 99.5, TVaR 99, EC.
- Convergence: rerun with 200,000 years; batch standard errors.
- Hero chart 1: modelled OEP and AEP (log return-period axis) with the 15 calibration years' empirical points.
- Outputs: `data/processed/yelt.parquet` (`year_id, event_seq, loss`), `ylt.parquet` (`year_id, n_events, attritional, cat_total, gross, max_event`), `outputs/tables/ep_curves.csv`, `outputs/tables/gross_metrics.csv`, `outputs/figures/hero_1_ep_curves.png`.
- Tests: simulated mean N within 3 standard errors of the fitted mean; simulated event losses all ≥ u₀ and ≤ cap; risk-measure estimators on x = 1..1000 give VaR_0.995 = 995 and TVaR_0.995 = 997.5; OEP ≤ AEP at every level; convergence within tolerance.
- Teach-back: OEP vs AEP; why the event hierarchy must be kept; how you know 100,000 years is enough.

**Gate 2.**

### M5 Reinsurance engine and Excel check

- Functions in `floodcat.reinsurance`: `apply_quota_share`, `apply_cat_xol` (per-event recovery, annual cap, reinstated fraction), `apply_programme` (inuring, several layers, returns per-year recoveries and f per layer). Vectorised over the YELT (group by year, cumulative sums in event order). The same functions run on the historical as-if event table for burning cost.
- Excel `excel/reinsurance_checks.xlsx` (built with openpyxl, live formulas): sheet `toy` (section 11 toy), sheet `history` (calibration as-if events through two sample layers — q = 0, c = 1, n = 1, attach 1-in-10 to exhaust 1-in-50, and attach 1-in-50 to exhaust 1-in-200 — with per-event recovery, annual cap, reinstated fraction, burning cost). Recalculate with LibreOffice headless and compare with Python.
- Tests: identities (0 ≤ r ≤ min(S', c·L); S' ≤ A ⇒ r = 0; S' ≥ A + L ⇒ r = c·L; QS recovery = q × loss; n = 0 ⇒ annual recovery ≤ c·L; annual recovery ≤ (1 + n)·c·L); toy golden values (section 11); annual-cap cases (section 11); Excel within 0.01%.
- Teach-back: work through the toy by hand; what happens if the inuring order is reversed; why coinsurance.

### M6 Pricing

- Generate the grid's layers with `floodcat.capital.programmes` (the same generator M8 uses; M4's OEP fixes the dollar terms). For every layer: burning cost on calibration as-if years with the number of years the layer is hit; modelled EL, AP, exhaustion probability, SD, TVaR 99.5; K_R; technical premium with reinstatements; ROL; multiple. Same for each QS share.
- Burning cost and modelled EL are reported side by side; pricing uses modelled EL. Credibility blending is optional (appendix only).
- Outputs: `outputs/tables/layer_pricing.csv` (`layer_id, attach, exhaust, c, n_reinst, ap, ep, years_hit, burning_cost, el, sd, tvar995, k_r, capital_charge, premium, exp_reinst_premium, rol, multiple`), figure ROL vs AP.
- Tests: toy pricing golden values (section 11); premium ≥ EL for every layer; ROL decreasing in attachment for fixed exhaustion; multiple increasing as AP falls; with n = 0 the formula reduces to P = (EL + charge)/(1 − e); net cost identity net_cost = e·target + CoC_R·d·K_R.
- Teach-back: burning cost vs modelled EL; why premium ≠ EL; why TVaR for the reinsurer's capital; what d represents and why it decides whether reinsurance can ever be worth buying.

**Gate 3.** CV v1 (heading date "Sep 2026 – Present" + bullets 1–2).

### M7 Gross vs net and economic capital

- For every programme: per-year L_net; mean, SD, VaR 99, VaR 99.5, TVaR 99, OEP/AEP at the standard return periods for net; premium, expected reinstatement premium, expected recovery, net cost, EC, relief, relief %, implied CoC; implied CoC compared with h = 8 / 10 / 12%.
- Outputs: `outputs/tables/programme_metrics.csv` (one row per programme ID).
- Tests: no reinsurance ⇒ relief = 0, net cost = 0; toy capital golden values (section 11); adding limit at fixed attachment never increases EC_net (check on the grid; report violations, which can only come from reinstatement premiums); relief approximately equals recovery in the gross 1-in-200 year minus expected recovery (report the gap, no tolerance).
- Teach-back: EC vs SCR; why a fixed premium does not change EC; why net cost subtracts expected recovery; what an implied CoC of 7% means.

### M8 Programme design and frontier

- Generate the grid (5.3): attachment and exhaustion as `(1 − q) × OEP⁻¹(1/RP)` of the gross event loss, rounded; towers; placements; reinstatements; plus no reinsurance and pure QS. Report the number of programmes N (a CV number).
- Frontier (EC_net and, separately, TVaR 99 net), convex hull, marginal CoC, the three choices, Balanced at h = 8 / 10 / 12%.
- Recommendation: Balanced at h = 10% unless the results clearly argue otherwise; the memo explains the choice in 4–5 paragraphs and presents it as a layer table (attach, exhaust, AP, placement, reinstatement, premium, ROL).
- Hero chart 2: gross vs net AEP for the recommended programme. Hero chart 3: all programmes, frontier, the three choices labelled.
- Outputs: `outputs/tables/programmes.csv` (ID and dollar terms), `frontier.csv`, `outputs/recommendation.json`, `outputs/figures/hero_2_gross_net.png`, `hero_3_frontier.png`.
- Tests: frontier golden test (section 11); every choice lies on the frontier; frontier EC strictly decreasing as net cost increases; grid contains no exhaustion ≤ attachment.
- Teach-back: why design layers by return period; what "dominated" means; why no single optimum; how the recommendation moves between h = 8% and 12%.

**Gate 4.**

### M9 Validation and stress

- Convergence (already in M4) repeated for the recommended programme's relief.
- Temporal holdout: refit M3 on 2009–2018 (same rules, no re-selection of families unless a fit fails), simulate 100,000 years, and for 2019–2023 report: total event count vs the distribution of a 5-year sum (percentile); each year's as-if annual loss as a percentile of the modelled AEP; the model return period of the largest 2019–2023 event. Report 2024–2025 observations as discussion only (2024 immature).
- Leave-one-major-event-out: remove the largest as-if calibration event (from severity data and its year's count), refit, rerun M4–M8 on the fixed contract grid; report gross VaR 99.5, EC, the Balanced pick, relief and implied CoC of the base recommendation.
- Year bootstrap: resample calibration years with replacement (events and attritional of a year move together), B = 200; refit; 20,000 years; re-price and re-evaluate the base recommended contract; 90% intervals for relief, relief % and implied CoC.
- Stresses (5.4): rerun M6–M8 on the fixed contract grid; for each, record whether the Balanced pick equals the base ID.
- Optional sensitivities: u₀ = 250m, CPI-only as-if, calibration from 2010, credibility blend, lognormal attritional.
- Outputs: `outputs/tables/holdout.csv`, `event_out.csv`, `bootstrap_ci.csv`, `recommendation_stability.csv` (`scenario, balanced_id, same_as_base, relief, relief_pct, net_cost, implied_coc`).
- `cv_numbers.json` keys: `stress_held`, `stress_total`.
- Tests: bootstrap resamples whole years (check that no event appears without its year's attritional); stresses re-use the base contract dollar terms; base scenario row reproduces M8.
- Teach-back: why bootstrap by year; what removing the largest event did; what a 5-year holdout can and cannot show; which assumption would change the recommendation.

### M10 Market benchmark

- From `placements.csv`: ROL by year, structure (attachment, shares).
- From `layer_pricing.csv`: layers with AP between 4% and 9%; compare technical ROL and multiple with FEMA's ROL and with FloodSmart Re spread ÷ EL. Compare the recommended structure with FEMA's (high attachment, small shares, two layers). Wording: "broadly compare"; never adjust the model to match.
- Bonus (only if the pipeline already accepts a state list, target year and named-storm filter from config without code changes): national, target year 2024, named storms only; modelled AP and EL for FloodSmart Re 2024-1 A and B.
- Outputs: `outputs/tables/benchmark.csv`, figure ROL vs AP (memo only, not README).
- Tests: FEMA limits and ROLs reproduce section 7; benchmark code reads no model parameter back into M3–M9 (static check: `benchmark.py` is not imported by any other module).
- Teach-back: why compare by attachment probability rather than dollars; why not calibrate to the vendor; why FEMA raised its attachment.

### M11 Reporting

- README: the business question, three hero charts, the recommended programme table, one paragraph on validation and benchmark, data credit and disclaimer, `make all`.
- `reports/memo.qmd` → PDF, English, 4–6 pages: 1 Executive summary (what to buy, why); 2 Portfolio & catastrophe model; 3 Reinsurance structure & pricing; 4 Capital & programme decision; 5 Validation, sensitivities & market benchmark; 6 Limitations (section 13).
- `outputs/cv_numbers.json`: every number in the CV, README and memo with the git hash. Keys at least: `n_events_calib`, `n_sims`, `n_programmes`, `relief_pct`, `net_cost`, `implied_coc`, `stress_held`, `stress_total`, `calibration_start`.
- Optional static Quarto page with the memo and the three hero charts.
- Tests: `make all` from a clean clone reproduces `cv_numbers.json`; every number in the README and memo is found in `outputs/`.

**Gate 5.** Final CV.

## 10. Repository

```
flood-cat-reinsurance/
  README.md  SPEC.md  Makefile  pyproject.toml
  config/     portfolio.yaml  modelling.yaml  simulation.yaml  reinsurance.yaml
              stress.yaml  fields.yaml
  data/       raw/ (+ MANIFEST)  processed/  market/ (placements.csv, cat_bonds.csv)
  src/floodcat/
              data/        load.py  claims.py  policies.py  portfolio.py
              events/      catalogue.py  asif.py
              model/       frequency.py  severity.py  attritional.py  simulate.py
              reinsurance/ quota_share.py  cat_xol.py  reinstatement.py  pricing.py
              capital/     metrics.py  programmes.py  frontier.py
              validation/  backtest.py  bootstrap.py  stress.py  benchmark.py
              utils/       risk_measures.py  io.py  plotting.py
  tests/      test_m0_config.py ... test_m11_reporting.py, fixtures/toy_yelt.csv
  notebooks/  01_data_and_portfolio ... 07_validation (presentation only; no logic)
  excel/      reinsurance_checks.xlsx
  reports/    data_checks.md  events.md  model_selection.md  memo.qmd
  outputs/    figures/  tables/  recommendation.json  cv_numbers.json
  site/       optional
```

## 11. Golden values and fixtures

Tolerance 1e-6 unless stated.

**Toy YELT** (`tests/fixtures/toy_yelt.csv`; USD m; attritional 0; event order as listed):

| Year | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Events | 12 | — | 65, 8 | 30 | — | 140 | 20 | 55, 90 | — | 5 |

Layer 50 xs 60, c = 1, n = 1, rate 100%:

| Quantity | Expected |
|---|---|
| Annual recovery by year | 0, 0, 5, 0, 0, 50, 0, 30, 0, 0 |
| Reinstated fraction f by year | 0, 0, 0.1, 0, 0, 1, 0, 0.6, 0, 0 |
| Burning cost = EL | 8.5 |
| AP (P(max > 60)), EP (P(max ≥ 110)) | 0.3, 0.1 |
| AEP(100) | 0.2 |
| TVaR_0.995(C) (n = 10 ⇒ the maximum) | 50 |
| K_R | 41.5 |
| Capital charge (CoC_R 0.10, d 0.5) | 2.075 |
| Target (e = 0.10) | 11.75 |
| mean(f) | 0.17 |
| Upfront premium P | 10.042735 |
| ROL | 0.200855 |
| Multiple | 1.382353 |
| Net cost | 3.25 |
| Gross mean, VaR_0.995, EC | 42.5, 145, 102.5 |
| Net annual loss by year | 22.042735, 10.042735, 79.047009, 40.042735, 10.042735, 110.085470, 30.042735, 131.068376, 10.042735, 15.042735 |
| Net mean, VaR_0.995, EC | 45.75, 131.068376, 85.318376 |
| Relief, relief %, implied CoC | 17.181624, 0.167626, 0.189156 |

Variants on the same toy:

| Case | Expected |
|---|---|
| n = 0, same layer | recoveries unchanged (0, 0, 5, 0, 0, 50, 0, 30, 0, 0); P = 11.75 |
| c = 0.8, n = 1 | recoveries 0, 0, 4, 0, 0, 40, 0, 24, 0, 0; f unchanged |
| QS q = 0.2 inuring, then 50 xs 60, c = 1, n = 1 | QS recovery = 0.2 × annual loss (mean 8.5); XoL recoveries 0, 0, 0, 0, 0, 50, 0, 12, 0, 0; burning cost 6.2 |

**Annual cap** (layer 50 xs 60, c = 1): events [140, 100] → n = 0: R = 50, f = 0; n = 1: R = 90, f = 1. Events [140, 140, 140], n = 1: R = 100, f = 1.

**As-if toy**: event in 2012 with TX loss 100 and LA loss 50; TIV TX 200 (2012) → 300 (2025), LA 100 → 80 ⇒ as-if 150 + 40 = 190.

**Risk measures**: x = 1, 2, ..., 1000 ⇒ VaR_0.995 = 995, TVaR_0.995 = 997.5, VaR_0.99 = 990, TVaR_0.99 = 995.

**Truncated MLE recovery**: 50,000 draws from lognormal(μ = 5, σ = 1.2) kept only above u₀ = e⁵ (about half survive; seed fixed); truncated lognormal MLE recovers μ and σ within 3%. (With 5,000 draws σ misses 3% in about 40% of seeds, so do not shrink the sample.)

**Frontier** (net cost, EC_net; EC_gross = 100):

| Point | Net cost | EC_net | Relief |
|---|---|---|---|
| P0 (no RI) | 0 | 100 | 0 |
| P1 | 1.2 | 80 | 20 |
| P2 | 3.0 | 85 | 15 |
| P3 | 2.9 | 60 | 40 |
| P4 | 4.0 | 50 | 50 |
| P5 | 4.6 | 47 | 53 |

Expected: P2 dominated; frontier P0, P1, P3, P4, P5; marginal CoC 6%, 8.5%, 11%, 20%; Balanced(8%) = P1, Balanced(10%) = P3, Balanced(12%) = P4; Budget-first (relief ≥ 25%) = P3; Protection-first = P5; implied CoC of P3 = 7.25%.

## 12. Output and labelling rules

- README shows only three figures: hero 1 (OEP/AEP), hero 2 (gross vs net AEP, recommended), hero 3 (frontier). Other figures go to the memo or `outputs/figures/`.
- Every figure subtitle: "Gulf Coast reference portfolio (FL, TX, LA, MS, AL), 2025 exposure, USD". Return-period axes on a log scale.
- Name things consistently: "indicative technical premium", "99.5% one-year economic capital proxy", "capital relief", "implied cost of capital", "cost–capital frontier".
- No company presented as real; FEMA and FloodSmart Re are named only as sources of public benchmark data.

## 13. Limitations to state

Historical-event model, not a vendor catastrophe model (no hazard, hydraulics or vulnerability modules); 15 calibration years, so the 1-in-200 tail rests on distributional assumptions and has wide parameter uncertainty; pre-2009 events (Katrina, Ike) excluded for lack of consistent exposure data; as-if adjusts only for state-level insured value (no within-state geography, building standards, mitigation or Risk Rating 2.0 mix changes); 2024–2025 immature and excluded, no development of open events; events defined by FEMA's `floodEvent` label rather than a treaty hours clause; attritional assumed independent of catastrophe events; paid claims exclude loss adjustment expense; prices are indicative technical premiums with assumed cost of capital and diversification; economic capital is an internal proxy covering this portfolio's insurance risk only (no reinsurer default, market or operational risk) and is not a Solvency II SCR; the portfolio is stylised; market benchmarks cover the national NFIP (all floods for FEMA's tower, named storms only for FloodSmart Re) and support only order-of-magnitude comparison.
