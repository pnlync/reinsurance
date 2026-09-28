# Flood Catastrophe Reinsurance & Capital Optimisation

> For a flood insurer exposed to catastrophe accumulation, what reinsurance programme should it buy, how much should it pay, and how much tail risk and economic capital does that programme remove?

A reinsurance decision study for a stylised Gulf Coast flood portfolio (FL, TX, LA, MS, AL) built from public NFIP data. Historical flood events from {{calibration_start}}–{{calibration_end}} are restated to 2025 exposure (USD {{portfolio_tiv_bn:,.0f}}bn insured value, {{portfolio_policies:,.0f}} insured units) and turned into a stochastic annual loss model of {{n_sims:,}} simulated years. {{n_programmes}} quota-share and catastrophe excess-of-loss programmes are priced on a technical basis and compared on net cost against the 99.5% one-year economic capital proxy they release.

**Answer.** Buy {{recommended_desc}} (`{{recommended_id}}`). It reduces the 99.5% one-year economic capital proxy by **{{relief_pct:.1%}}** (USD {{relief:,.0f}}m) for a net cost of **USD {{net_cost:,.0f}}m a year**, an implied cost of capital of **{{implied_coc:.1%}}**, {{coc_vs_hurdle}} the {{hurdle:.0%}} hurdle. The case rests on the reinsurer's diversification: with none (d = 1) the implied cost of capital rises to {{d10_rec_coc:.1%}} and the same rule picks {{d10_balanced_desc}}.

## 1. Gross catastrophe risk profile

![Modelled OEP and AEP with calibration years](outputs/figures/hero_1_ep_curves.png)

{{n_events_calib}} catastrophe events above USD {{u0:,.0f}}m (as-if) in {{calibration_start}}–{{calibration_end}}, the largest {{largest_event}} (USD {{largest_event_asif:,.0f}}m on 2025 exposure). Frequency {{frequency_family}} ({{frequency_mean:.2f}} events a year); severity left-truncated {{severity_family}}, capped at {{cap_multiple:.0f}}× the largest event. Gross 1-in-200 annual loss USD {{gross_var_995:,.0f}}m; 99.5% economic capital proxy USD {{gross_ec:,.0f}}m. {{cap_sentence}}

## 2. Recommended programme

![Gross vs net AEP for the recommended programme](outputs/figures/hero_2_gross_net.png)

{{tbl_layers}}

Prices are indicative technical premiums: modelled expected loss plus a charge of {{coc_r:.0%}} on {{d:.1f}} × the reinsurer's TVaR capital, grossed up for expenses, net of expected reinstatement premium.

## 3. Cost–capital frontier

![Cost–capital frontier](outputs/figures/hero_3_frontier.png)

{{n_frontier}} of {{n_programmes}} programmes are efficient. Budget-first: {{budget_first_desc}} ({{budget_relief_pct:.0%}} relief for USD {{budget_net_cost:,.0f}}m). Balanced at a {{hurdle:.0%}} hurdle: the recommendation above. Protection-first: {{protection_first_desc}} ({{protection_relief_pct:.0%}} relief for USD {{protection_net_cost:,.0f}}m).

## 4. Validation and market benchmark

{{stress_sentence}} The tail is fragile: without {{eo_event}} gross economic capital falls by {{eo_ec_drop:.0%}}, and a year bootstrap gives a 90% interval of {{relief_pct_p05:.0%}}–{{relief_pct_p95:.0%}} for capital relief and {{implied_coc_p05:.1%}}–{{implied_coc_p95:.1%}} for the implied cost of capital. At attachment probabilities of {{band_ap_lo:.0%}}–{{band_ap_hi:.0%}}, technical rates on line ({{band_rol_min:.1%}}–{{band_rol_max:.1%}}) are below FEMA's 2025 NFIP placement ({{fema_rol_2025:.1%}}), mainly because the model's layers are wider; price multiples of expected loss ({{band_mult_min:.1f}}–{{band_mult_max:.1f}}×) are comparable with FloodSmart Re cat bonds ({{cb_mult_min:.1f}}–{{cb_mult_max:.1f}}×). Benchmarks are order-of-magnitude checks only, never calibration targets.

Full write-up: [`reports/memo.pdf`](reports/memo.pdf). Data checks, event catalogue, model selection and decisions: [`reports/`](reports/). Treaty mechanics are checked independently in [`excel/reinsurance_checks.xlsx`](excel/reinsurance_checks.xlsx).

## Reproduce

```bash
uv sync
make all     # first run downloads and freezes the OpenFEMA data through the API (about an hour), then rebuilds every output
make test
```

Every number above is written by the pipeline to `outputs/` (see `outputs/cv_numbers.json`, git `{{git_hash}}`).

## Data and disclaimer

Data: OpenFEMA NFIP Redacted Claims and NFIP Redacted Policies. This product uses the FEMA OpenFEMA API, but is not endorsed by FEMA. The Federal Government or FEMA cannot vouch for the data or analyses derived from these data after the data have been retrieved from the Agency's website(s). The Gulf Coast portfolio is a stylised insurance portfolio calibrated to the exposure and claims experience observed in the NFIP Gulf states; it is not intended to reproduce the finances of the NFIP itself. Reinsurance prices are indicative technical premiums, not market quotes. Economic capital is a 99.5% one-year proxy, not a Solvency II SCR.
