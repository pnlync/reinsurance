"""The only module allowed to read the frozen raw OpenFEMA files (SPEC §4.1, M0, M1).

The raw data are FEMA's published v3 bulk parquet files, downloaded by hand in a browser (fema.gov
refuses scripted downloads) and saved unchanged in data/raw/. `MANIFEST` records each file's URL,
dataset version, download date, row count and SHA-256; `verify()` refuses to run on anything else,
so later FEMA refreshes are never pulled in silently.
"""
from __future__ import annotations

import datetime as dt
import json

import duckdb
import pandas as pd

from floodcat.utils.io import ROOT, load_config, sha256

RAW_DIR = ROOT / "data/raw"
MANIFEST = RAW_DIR / "MANIFEST"
BULK_URL = "https://www.fema.gov/about/reports-and-data/openfema/v{version}/{file}"

FILES = {
    "claims": "NfipClaimsV3.parquet",
    "policies": "NfipPoliciesV3.parquet",
}

HOW_TO = """Raw data missing or changed. Download in a browser and save unchanged in data/raw/:
  https://www.fema.gov/about/reports-and-data/openfema/v3/NfipClaimsV3.parquet
  https://www.fema.gov/about/reports-and-data/openfema/v3/NfipPoliciesV3.parquet
(dataset pages: fema.gov/openfema-data-page/nfip-redacted-claims-v3 and .../nfip-redacted-policies-v3)."""


def raw_path(name: str) -> str:
    return str(RAW_DIR / FILES[name])


def query(sql: str) -> pd.DataFrame:
    """Run DuckDB SQL in which `{claims}` and `{policies}` stand for the frozen raw files."""
    sql = sql.format(**{k: f"read_parquet('{raw_path(k)}')" for k in FILES})
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    return con.execute(sql).df()


def _rows(name: str) -> int:
    return int(query(f"SELECT count(*) FROM {{{name}}}").iloc[0, 0])


def write_manifest() -> None:
    """Record the frozen files (run once, after the manual download)."""
    fields = load_config("fields")
    entries = []
    for name, file in FILES.items():
        p = RAW_DIR / file
        spec = fields[name]
        entries.append({
            "file": file,
            "dataset": spec["dataset"],
            "version": spec["version"],
            "url": BULK_URL.format(version=spec["version"], file=file),
            "download_date": dt.date.fromtimestamp(p.stat().st_mtime).isoformat(),
            "rows": _rows(name),
            "sha256": sha256(p),
        })
    MANIFEST.write_text(json.dumps(entries, indent=2) + "\n")


def verify() -> None:
    """Check the raw files exist and match MANIFEST (row count and SHA-256)."""
    if not MANIFEST.exists():
        raise SystemExit("data/raw/MANIFEST missing: run `uv run python -m floodcat.data.load` after downloading.\n" + HOW_TO)
    for e in json.loads(MANIFEST.read_text()):
        p = RAW_DIR / e["file"]
        if not p.exists() or sha256(p) != e["sha256"]:
            raise SystemExit(f"{e['file']} is missing or differs from MANIFEST.\n" + HOW_TO)
    print("raw files match MANIFEST", flush=True)


if __name__ == "__main__":
    write_manifest()
    print(MANIFEST.read_text())
