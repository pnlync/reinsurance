<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Flood Catastrophe Reinsurance</title>
  <meta name="description" content="What reinsurance a Gulf Coast flood portfolio should buy, what it costs and how much catastrophe capital it removes, built from public NFIP data.">
  <link rel="icon" type="image/svg+xml" href="./assets/favicon.svg">
  <link rel="stylesheet" href="./styles/site.css">
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="#top"><span class="brand-dot"></span>Flood Cat <span class="long">Reinsurance</span></a>
    <nav class="topnav" aria-label="Sections">
      <a href="#portfolio">Portfolio</a>
      <a href="#model">Cat model</a>
      <a href="#pricing">Pricing</a>
      <a href="#decision">Decision</a>
      <a href="#validation">Validation</a>
      <a href="#benchmark">Benchmark</a>
      <a href="#limitations">Limitations</a>
    </nav>
  </div>
</header>

<main id="top">
  <section class="hero" aria-labelledby="title">
    <p class="eyebrow">Reinsurance &amp; catastrophe project · Tom Zhang · Python, Excel</p>
    <h1 id="title">Flood Catastrophe Reinsurance &amp; Capital Optimisation</h1>
    <p class="question">For a flood insurer exposed to catastrophe accumulation, what reinsurance programme should it buy, how much should it pay, and how much tail risk and economic capital does that programme remove?</p>
    <p class="lede">A stylised Gulf Coast flood portfolio (FL, TX, LA, MS, AL) built from public NFIP claims and policy data. Historical flood events from {{calibration_start}}–{{calibration_end}} are restated to 2025 exposure and turned into a stochastic loss model of {{n_sims:,}} simulated years; {{n_programmes}} quota-share and catastrophe excess-of-loss programmes are priced on a technical basis and compared on net cost against the 99.5% one-year economic capital proxy they release.</p>
    <div class="answer">
      <p><strong>Answer.</strong> Buy {{recommended_desc}}. It releases <strong>{{relief_pct:.1%}}</strong> of the 99.5% one-year economic capital proxy (USD {{relief:,.0f}}m) for a net cost of <strong>USD {{net_cost:,.0f}}m a year</strong>: an implied cost of capital of <strong>{{implied_coc:.1%}}</strong>, {{coc_vs_hurdle}} the {{hurdle:.0%}} hurdle.</p>
      <p>The case rests on the reinsurer's diversification: with none, the implied cost rises to {{d10_rec_coc:.1%}} and the same rule picks {{d10_balanced_desc}}.</p>
    </div>
    <div class="links">
      <a class="btn primary" href="./memo.pdf" target="_blank" rel="noopener">Actuarial memo (PDF)</a>
      <a class="btn" href="https://github.com/pnlync/reinsurance">GitHub repository</a>
      <a class="btn" href="./assets/reinsurance_checks.xlsx">Excel treaty check</a>
      <a class="btn" href="https://pnlync.github.io/actuarial/">Portfolio homepage</a>
    </div>
    <p class="honesty"><strong>Stylised portfolio, indicative prices.</strong> Real inputs: OpenFEMA NFIP Redacted Claims and Policies (v3), public FEMA reinsurance placements and FloodSmart Re cat bond terms. The portfolio is calibrated to NFIP Gulf-state experience and does not reproduce the NFIP's finances. Prices are indicative technical premiums, not market quotes; economic capital is a 99.5% one-year proxy, not a Solvency&nbsp;II SCR.</p>
  </section>

  <section id="overview" aria-labelledby="h-overview">
    <h2 id="h-overview">What the model found</h2>
    <p class="section-q">Six results, each written by the pipeline to <code>outputs/</code>.</p>
    <div class="findings">
      <div class="finding"><div class="num">{{relief_pct:.0%}}</div><div class="label">Capital released by the recommended programme</div><p>Net economic capital falls from USD {{gross_ec:,.0f}}m to USD {{ec_net:,.0f}}m. Premium USD {{premium:,.0f}}m, expected recoveries USD {{exp_recovery:,.0f}}m.</p></div>
      <div class="finding"><div class="num">{{implied_coc:.1%}}</div><div class="label">Implied cost of the released capital</div><p>Every programme costs {{coc_min:.1%}}–{{coc_max:.1%}} per unit of capital released, below the {{hurdle:.0%}} hurdle, because the reinsurer charges {{coc_r:.0%}} × {{d:.1f}} on its capital plus expenses.</p></div>
      <div class="finding"><div class="num">{{d10_rec_coc:.1%}}</div><div class="label">Without reinsurer diversification</div><p>At d = 1 reinsurance capital costs more than equity and the Balanced rule picks {{d10_balanced_desc}}. Diversification is why reinsurance is worth buying at all.</p></div>
      <div class="finding"><div class="num">−{{eo_ec_drop:.0%}}</div><div class="label">Gross capital without {{eo_event}}</div><p>The 1-in-200 tail rests on a few events: the year bootstrap puts the recommended programme's relief at {{relief_pct_p05:.0%}}–{{relief_pct_p95:.0%}} (90% interval).</p></div>
      <div class="finding"><div class="num">{{stress_structure_held}} / {{stress_total}}</div><div class="label">Stresses keeping the layer structure</div><p>{{stress_sentence}}</p></div>
      <div class="finding"><div class="num">{{band_mult_min:.1f}}–{{band_mult_max:.1f}}×</div><div class="label">Price multiple of expected loss</div><p>Comparable with FloodSmart Re cat bonds ({{cb_mult_min:.1f}}–{{cb_mult_max:.1f}}×); rates on line sit below FEMA's {{fema_rol_2025:.1%}} mainly because the model's layers are wider.</p></div>
    </div>
    <h3>From claims to a reinsurance decision</h3>
    <div class="chain"><span>NFIP claims &amp; policies</span><i>→</i><span>Event catalogue</span><i>→</i><span>As-if 2025</span><i>→</i><span>Frequency · severity · attritional</span><i>→</i><span>Year–event simulation</span><i>→</i><span>Treaty engine</span><i>→</i><span>Technical pricing</span><i>→</i><span>Gross vs net capital</span><i>→</i><span>Cost–capital frontier</span></div>
  </section>

  <section id="portfolio" aria-labelledby="h-port">
    <h2 id="h-port">Portfolio and events</h2>
    <p class="section-q">What are we buying reinsurance for, and which historical catastrophes hit it?</p>
    <p>The 2025 Gulf Coast reference portfolio: {{portfolio_policies:,.0f}} insured units, USD {{portfolio_tiv_bn:,.0f}}bn total insured value ({{fl_tiv_share:.0%}} in Florida) and USD {{portfolio_premium_m:,.0f}}m premium. Claims are grouped by FEMA's <code>floodEvent</code> label and each event is restated to 2025 by the ratio of state insured value; events of at least USD {{u0:,.0f}}m form the catalogue ({{n_events_calib}} in {{calibration_start}}–{{calibration_end}}), the rest is attritional loss (mean USD {{attritional_mean:,.0f}}m a year).</p>
    {{html_events}}
    <figure><img src="./assets/charts/m1_tiv_by_state.png" alt="Written total insured value by state" loading="lazy"><figcaption>Insured value by state is the as-if yardstick: each event is scaled by its state's 2025 insured value relative to the event year.</figcaption></figure>
  </section>

  <section id="model" aria-labelledby="h-model">
    <h2 id="h-model">Catastrophe loss model</h2>
    <p class="section-q">How many catastrophes a year, how large, and what does a 1-in-200 year look like?</p>
    <p>Annual loss = attritional + sum of event losses. Frequency: {{frequency_family}}, {{frequency_mean:.2f}} events a year (dispersion index {{dispersion:.2f}}). Severity: {{severity_family}} fitted with left truncation at the event threshold, chosen by AIC after checking that each of the five largest events is unremarkable under the fit; each event is capped at {{cap_multiple:.0f}}× the largest calibration event. {{cap_sentence}}</p>
    <figure><img src="./assets/charts/hero_1_ep_curves.png" alt="Modelled OEP and AEP with calibration years" loading="lazy"><figcaption>Occurrence (largest event) and aggregate (annual) exceedance curves. Gross 1-in-200 annual loss USD {{gross_var_995:,.0f}}m; economic capital proxy USD {{gross_ec:,.0f}}m.</figcaption></figure>
    {{html_ep}}
    <figure><img src="./assets/charts/m3_severity_qq_survival.png" alt="Severity QQ plot and conditional survival" loading="lazy"><figcaption>The three candidate fits are within {{aic_spread:.1f}} AIC points; the largest events sit above the fitted line, as the largest of {{n_events_calib}} events often will.</figcaption></figure>
  </section>

  <section id="pricing" aria-labelledby="h-pricing">
    <h2 id="h-pricing">Treaties and technical pricing</h2>
    <p class="section-q">What does each layer recover, and what should the reinsurer charge?</p>
    <p>Quota share inures to per-event Cat XoL. Layers are set by return period (attach 1-in-{{attach_rps}}; exhaust 1-in-{{exhaust_rps}}), as single layers or towers, placed {{placements}}, with zero or one reinstatement. Premium = (modelled expected loss + {{coc_r:.0%}} × {{d:.1f}} × the reinsurer's TVaR capital) ÷ (1 − {{xol_expense:.0%}} expenses), with expected reinstatement premium counted as income.</p>
    {{html_pricing}}
    <figure><img src="./assets/charts/m6_rol_vs_ap.png" alt="Technical rate on line by attachment probability" loading="lazy"><figcaption>Rate on line falls with attachment probability; the multiple of expected loss rises for remote layers, where capital dominates the price. Burning cost is zero where history never reached, which is why a model is needed.</figcaption></figure>
  </section>

  <section id="decision" aria-labelledby="h-dec">
    <h2 id="h-dec">Capital and the programme decision</h2>
    <p class="section-q">Which programmes are efficient, and which should management choose?</p>
    <p>Net loss = gross − recoveries + premiums + reinstatement premiums. A fixed premium moves VaR and the mean equally, so capital relief comes only from tail recoveries. Net cost = premiums + expected reinstatement premiums − expected recoveries; implied cost of capital = net cost ÷ capital relief. {{n_frontier}} of {{n_programmes}} programmes are efficient.</p>
    <figure><img src="./assets/charts/hero_3_frontier.png" alt="Cost-capital frontier with the three management choices" loading="lazy"><figcaption>Every point is a programme; the line is the cost–capital frontier. There is no single optimum: the choice depends on budget, appetite and the cost of the insurer's own capital.</figcaption></figure>
    {{html_choices}}
    <h3>Walking up the frontier</h3>
    <p>The Balanced rule stops before the first step whose marginal cost of capital exceeds the hurdle ({{h_lo:.0%}}: <code>{{balanced_08_id}}</code>; {{h_hi:.0%}}: <code>{{balanced_12_id}}</code>). Equivalently it minimises net reinsurance cost + {{hurdle:.0%}} × net capital: USD {{tcr_rec:,.0f}}m against USD {{tcr_gross:,.0f}}m with no reinsurance.</p>
    {{html_hull}}
    <h3>Recommended programme</h3>
    {{html_layers}}
    <figure><img src="./assets/charts/hero_2_gross_net.png" alt="Gross versus net aggregate exceedance for the recommended programme" loading="lazy"><figcaption>The programme trades a higher expected cost in ordinary years for a much thinner tail.</figcaption></figure>
    <div class="note"><strong>Affordability.</strong> The premium is {{premium_share_of_portfolio:.0%}} of the portfolio's own premium. At a {{hurdle:.0%}} hurdle the gross capital would cost USD {{tcr_gross:,.0f}}m a year, more than the expected margin of USD {{expected_margin:,.0f}}m, so transferring the tail is cheaper than holding it. If that premium is not affordable, Budget-first ({{budget_first_desc}}) releases {{budget_relief_pct:.0%}} for USD {{budget_net_cost:,.0f}}m.</div>
  </section>

  <section id="validation" aria-labelledby="h-val">
    <h2 id="h-val">Validation, stresses and sensitivities</h2>
    <p class="section-q">Would the recommendation survive a different view of the risk or the price?</p>
    <ul class="tight">
      <li><strong>Convergence</strong>: gross VaR 99.5 moves {{conv_diff:.2%}} and the recommended relief {{conv_rec_diff:.2%}} at {{conv_years:,}} years.</li>
      <li><strong>Temporal holdout</strong>: refitted on {{fit0}}–{{fit1}}, the model expected {{ho_count_mean:.1f}} events in {{test0}}–{{test1}}; {{ho_count_obs}} occurred (percentile {{ho_count_pct:.0%}}). {{ho_largest_name}} was a 1-in-{{ho_ian_rp:.0f}} event under that model.</li>
      <li><strong>Largest event removed</strong>: without {{eo_event}}, gross capital falls to USD {{eo_gross_ec:,.0f}}m and the Balanced choice becomes {{eo_balanced_desc}}.</li>
      <li><strong>Year bootstrap</strong> ({{n_boot}} replicates): 90% intervals of {{relief_pct_p05:.0%}}–{{relief_pct_p95:.0%}} for relief and {{implied_coc_p05:.1%}}–{{implied_coc_p95:.1%}} for the implied cost of capital.</li>
      <li><strong>Engine checks</strong>: golden values from a hand-worked toy example, treaty identities, and an Excel workbook in live formulas that matches Python in {{excel_cells}} cells (largest relative difference {{excel_max_diff:.0e}}).</li>
    </ul>
    {{html_stress}}
  </section>

  <section id="benchmark" aria-labelledby="h-bench">
    <h2 id="h-bench">Market benchmark</h2>
    <p class="section-q">Are the technical prices the right order of magnitude?</p>
    <figure><img src="./assets/charts/m10_rol_vs_ap_benchmark.png" alt="Technical pricing versus FEMA placements and FloodSmart Re cat bonds" loading="lazy"><figcaption>Compared by attachment probability, not dollars. Left: rates on line; right: price as a multiple of expected loss.</figcaption></figure>
    <p>FEMA's traditional NFIP placements cost {{fema_rol_2023:.1%}}, {{fema_rol_2024:.1%}} and {{fema_rol_2025:.1%}} rate on line in {{fema_y0}}–{{fema_y1}}, attaching at USD {{fema_attach_bn:.0f}}bn nationally with {{fema_share_lo:.0%}}–{{fema_share_hi:.0%}} shares. The model's layers at similar attachment probabilities price at {{band_rol_min:.1%}}–{{band_rol_max:.1%}}, but as multiples of expected loss ({{band_mult_min:.1f}}–{{band_mult_max:.1f}}×) they sit with FloodSmart Re cat bonds ({{cb_mult_min:.1f}}–{{cb_mult_max:.1f}}×). The benchmarks cover the national NFIP (all floods for FEMA, named storms only for the cat bonds) and were never used to calibrate the model.</p>
  </section>

  <section id="limitations" aria-labelledby="h-lim">
    <h2 id="h-lim">Limitations</h2>
    <p class="section-q">What the model can and cannot say.</p>
    <ul class="tight">
      <li>Historical-event model, not a vendor catastrophe model: no hazard, hydraulics or vulnerability modules.</li>
      <li>{{n_calib_years}} calibration years: the 1-in-200 tail rests on the severity family and the event cap. Pre-2009 events (Katrina, Ike) are excluded for lack of consistent exposure data.</li>
      <li>As-if restatement uses state-level insured value only; {{holdout0}}–{{holdout1}} are held out and {{holdout0}} is immature; events are FEMA labels, not a treaty hours clause.</li>
      <li>Attritional losses assumed independent of catastrophes; paid claims exclude loss adjustment expense.</li>
      <li>Prices use assumed cost of capital, diversification and expenses; economic capital covers this portfolio's insurance risk only.</li>
    </ul>
  </section>
</main>

<footer>Flood Catastrophe Reinsurance &amp; Capital Optimisation · Tom Zhang · Built in Python with an independent Excel check · git <code>{{git_hash}}</code><br>
Data: OpenFEMA NFIP Redacted Claims and NFIP Redacted Policies. This product uses the FEMA OpenFEMA API, but is not endorsed by FEMA. The Federal Government or FEMA cannot vouch for the data or analyses derived from these data after the data have been retrieved from the Agency's website(s). The Gulf Coast portfolio is a stylised insurance portfolio calibrated to the exposure and claims experience observed in the NFIP Gulf states; it is not intended to reproduce the finances of the NFIP itself. Reinsurance prices are indicative technical premiums, not market quotes. Economic capital is a 99.5% one-year proxy, not a Solvency II SCR.</footer>
</body>
</html>
