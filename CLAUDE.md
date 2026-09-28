# CLAUDE.md

Flood catastrophe reinsurance & capital optimisation (portfolio project). **SPEC.md is the contract — read it in full before any work and follow §1 "How we work".**

## Key rules (from SPEC, repeated because they are the ones most often broken)
- One module at a time in SPEC §9 order (M0, M1, ...). Before coding a module, explain it in Chinese (≤ 300 words) and wait for the owner's OK. Do not start the next module until the owner replies "continue".
- Tests first (`tests/test_m<n>_*.py`); report every test PASS/FAIL with numbers. One commit per module: `M<n>: <module name>`.
- Never edit the golden values in SPEC §11 or the tests that check them. A failing golden test means the implementation is wrong; report the diagnosis.
- All parameters live in `config/*.yaml`; no hard-coded numbers in `src/` except mathematical constants. Only `floodcat.data.load` may read `data/raw/`.
- Do not add any feature that is not in SPEC; if something seems necessary, ask first. If SPEC is unclear, contradictory or looks wrong: stop and ask. Don't guess. (No blanket decision authority has been given for this project.)
- Every public number comes from `outputs/`; never type numbers by hand into README, memo or CV. Never write "optimal programme", "validated catastrophe model", "vendor-grade", "Solvency II SCR" or "market quote".

## Owner context
- The owner is learning reinsurance / cat modelling through this project and must be able to explain every line in interviews. Prefer readable, explicit numpy/pandas over clever code. Explanations and teach-back in Chinese; code, reports and README in English.
- `private_notes/` holds the owner's planning guides: `claude_guide.md` (the Chinese "Final Guide" that SPEC calls the companion guide) and `chatgpt_prototype.txt` (an earlier ChatGPT draft, superseded by SPEC where they differ, e.g. K_R uses TVaR not VaR). It is gitignored — never commit, quote into public files, or publish it.
- Where the guide and SPEC differ, SPEC wins (e.g. the guide's §2.4 illustrative TVaR = 70 / P = 12.86 is not a golden value; SPEC §11 is).

## Environment
- Python 3.12 via uv (`uv sync`, `uv run pytest`). SPEC says ≥ 3.11, but uv's 3.11 build is killed by macOS on this machine.
- GitHub: git@github.com:pnlync/reinsurance.git (SPEC §10 calls the repo `flood-cat-reinsurance`; the package is `floodcat`).
- `gh` CLI is not installed.
- Raw OpenFEMA files go in `data/raw/` (not committed; `MANIFEST` is committed).
