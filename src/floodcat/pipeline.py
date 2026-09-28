"""Pipeline entry point: `python -m floodcat.pipeline <step>` (SPEC §9, Makefile targets)."""
from __future__ import annotations

import importlib
import sys

# step -> "module:function"; filled in as each module is built
STEPS: dict[str, str] = {
    "data": "floodcat.data.portfolio:run_all",
    "events": "floodcat.events.report:run",
    "model": "floodcat.model.fit:run",
    "simulate": "floodcat.model.simulate:run",
    "engine": "floodcat.reinsurance.excel:run",
    "pricing": "floodcat.capital.run:run_pricing",
    "capital": "floodcat.capital.run:run_capital",
    "frontier": "floodcat.capital.run:run_frontier",
    "validate": "floodcat.validation.run:run",
    "benchmark": "floodcat.validation.benchmark:run",
    "report": "floodcat.report:run",
}

ORDER = ["data", "events", "model", "simulate", "engine", "pricing", "capital", "frontier", "validate", "benchmark", "report"]


def run(step: str) -> None:
    if step not in ORDER:
        raise SystemExit(f"unknown step {step!r}; choose from {ORDER}")
    if step not in STEPS:
        raise SystemExit(f"step {step!r} is not built yet")
    mod, fn = STEPS[step].split(":")
    print(f"== {step} ==", flush=True)
    getattr(importlib.import_module(mod), fn)()


if __name__ == "__main__":
    for s in sys.argv[1:]:
        run(s)
