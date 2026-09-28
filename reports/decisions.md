# Decision log

The owner gave the agent full discretion over this project on 28 Sep 2026. Every judgement call that SPEC leaves open, or where the agent departs from SPEC, is recorded here with its reason.

| # | Module | Decision | Why |
|---|---|---|---|
| D1 | M0 | Python 3.12 (SPEC says ≥ 3.11) | uv's 3.11 build is killed by macOS on this machine; same setup as the sibling project |
| D2 | M0 | Repo is `reinsurance`, package `floodcat` (SPEC §10 calls the repo `flood-cat-reinsurance`) | GitHub repo already created under that name |
| D3 | M0 | All modelling money is in USD m; raw claims/exposure stay in USD until the event catalogue | SPEC golden values and outputs are in USD m; one unit from M2 onward avoids 1e6 slips |
| D4 | M0 | Makefile targets call `python -m floodcat.pipeline <step>`; `make all` runs the steps in order | One entry point, easy to reproduce from a clean clone |
| D5 | M0 | Data-source URLs and dataset versions live in `config/fields.yaml` | SPEC lists no separate data config; fields.yaml already holds the version-specific mapping |
