# SPEC §9 M0 — one target per pipeline step; `make all` rebuilds everything from data/raw
PY := uv run python -m floodcat.pipeline
STEPS := data events model simulate engine pricing capital frontier validate benchmark report

.PHONY: $(STEPS) all test

$(STEPS):
	$(PY) $@

all:
	$(PY) $(STEPS)

test:
	uv run pytest -q
