# Decision log

The owner gave the agent full discretion over this project on 28 Sep 2026. Every judgement call that SPEC leaves open, or where the agent departs from SPEC, is recorded here with its reason.

| # | Module | Decision | Why |
|---|---|---|---|
| D1 | M0 | Python 3.12 (SPEC says ≥ 3.11) | uv's 3.11 build is killed by macOS on this machine; same setup as the sibling project |
| D2 | M0 | Repo is `reinsurance`, package `floodcat` (SPEC §10 calls the repo `flood-cat-reinsurance`) | GitHub repo already created under that name |
| D3 | M0 | All modelling money is in USD m; raw claims/exposure stay in USD until the event catalogue | SPEC golden values and outputs are in USD m; one unit from M2 onward avoids 1e6 slips |
| D4 | M0 | Makefile targets call `python -m floodcat.pipeline <step>`; `make all` runs the steps in order | One entry point, easy to reproduce from a clean clone |
| D5 | M0 | Data-source URLs and dataset versions live in `config/fields.yaml` | SPEC lists no separate data config; fields.yaml already holds the version-specific mapping |
| D6 | M1 | OpenFEMA v3 (`NfipClaims`, `NfipPolicies`), pulled through the API with keyset paging (state slices for claims, state × month for policies), each slice checked against the API record count | v3 is complete (claims 2.73m, policies 74.7m rows); the bulk parquet files on fema.gov refuse scripted clients (HTTP 403), and SPEC §4.1 allows the API route |
| D7 | M1 | Endorsement de-duplication: same property-and-term key → keep the record(s) with the latest endorsement date | v3 has no policy/term number; some terms appear twice (issued + endorsed). The rule removes 0.5–1.2% of written TIV a year and only acts where an endorsement proves a record was superseded |
| D8 | M3 | Severity tail acceptable if, for each of the top 5 events, P(k-th largest of n ≥ observed) under the fit is in [0.05, 0.95]; degenerate (boundary) fits are not acceptable. First draft used 'fitted quantile at plotting position within ×2', which rejected every family | SPEC asks for a judgement on the top-5 fit; for n = 20 the top order statistics are so variable that a fixed ratio rule rejects fits that are fully consistent with the data (Harvey p = 0.30, Ian p = 0.14 under the log-logistic) |
| D9 | M1 | Calibration starts in 2009: 2009 written/in-force ratio 1.0000 vs 2010–2023 mean 0.9998 (tolerance max(3 SD, 1%)) | Annual policies written in t are in force on 31 Dec t unless cancelled, so the file's 2009-01-01 start does not truncate 2009 |
| D10 | M9 | Refits in the back-test, event-out, bootstrap and sensitivities keep the base frequency and severity families | SPEC: "no re-selection of families unless a fit fails"; differences can then be attributed to the data, not to a family switch |
| D11 | M1 | National check passes if within ±10% of the CRS figures (4.5m policies, USD 1.3tn): 4.68m insured units (1.040), USD 1.289tn (0.992) | SPEC's purpose is "same order"; coverage is 0.8% under "over $1.3tn", plausibly because the OpenFEMA extract lags FEMA's system of record |
| D12 | M2 | u₀ = USD 100m confirmed (20 calibration events; 14 at the 250m sensitivity) | SPEC base; no natural break in the sorted list between 100m and 250m, and more events stabilise the truncated severity fit |
| D13 | M6 | Programmes with identical dollar terms are evaluated once; 387 grid IDs → 255 distinct contracts; aliases in `programme_aliases.csv` | The 1-in-200 and 1-in-250 OEP both equal the event cap, so E200 and E250 give the same contract; duplicates would tie on the frontier |
| D14 | M4/M9 | Gross 1-in-200 OEP sits at the SPEC event cap (3 × Harvey = USD 26.6bn; 0.47% of events capped). Base kept as SPEC; M9 adds two sensitivities: lognormal severity (next-best AIC, ΔAIC 0.5) and a 5× cap | The 99.5% capital proxy is driven by the cap assumption; the memo must say so and show how much the recommendation depends on it |
