"""The only module allowed to read (or write) the frozen raw OpenFEMA files (SPEC §4.1, M0, M1).

Bulk parquet files on fema.gov refuse scripted clients, so the data come from the OpenFEMA API
(SPEC §4.1 "Otherwise the API ... with $select, $filter by state, and paging"). Each dataset is
pulled in slices (state x month for policies, state for claims) with keyset paging on `id`, checked
against the API's record count, and frozen into one parquet file per dataset. `MANIFEST` records the
URL template, version, download date, row count and SHA-256.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pandas as pd
import requests

from floodcat.utils.io import ROOT, load_config, sha256

RAW_DIR = ROOT / "data/raw"
MANIFEST = RAW_DIR / "MANIFEST"
API = "https://www.fema.gov/api/open"
PAGE = 10_000
WORKERS = 16

CLAIMS_FILE = RAW_DIR / "nfip_claims_v3.parquet"
POLICIES_FILE = RAW_DIR / "nfip_policies_v3.parquet"
NATIONAL_FILE = RAW_DIR / "nfip_policies_v3_national_inforce_2025.parquet"


# ---------------------------------------------------------------- download helpers

def _get(url: str, params: dict, tries: int = 6) -> requests.Response:
    for k in range(tries):
        try:
            r = requests.get(url, params=params, timeout=180)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 ** k)
    raise RuntimeError(f"OpenFEMA request failed after {tries} tries: {url} {params}")


def _count(entity: str, version: int, flt: str) -> int:
    r = _get(f"{API}/v{version}/{entity}", {"$filter": flt, "$inlinecount": "allpages", "$top": 1, "$select": "id"})
    return int(r.json()["metadata"]["count"])


def _pull_slice(entity: str, version: int, fields: list[str], flt: str, out: Path) -> tuple[str, int, int]:
    """Keyset-page one filtered slice into `out` (all columns as text); return (name, expected, got)."""
    expected = _count(entity, version, flt)
    frames, last = [], None
    while True:
        f = flt if last is None else f"{flt} and id gt {last}"
        r = _get(f"{API}/v{version}/{entity}", {"$select": ",".join(fields), "$filter": f, "$orderby": "id", "$top": PAGE, "$format": "csv"})
        df = pd.read_csv(io.StringIO(r.text), dtype=str, keep_default_na=False)
        if df.empty:
            break
        frames.append(df)
        last = int(df["id"].iloc[-1])
        if len(df) < PAGE:
            break
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({c: pd.Series(dtype=str) for c in fields})
    df = df[fields]
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    return out.name, expected, len(df)


def _run_slices(entity: str, version: int, fields: list[str], slices: dict[str, str], slice_dir: Path) -> dict:
    slice_dir.mkdir(parents=True, exist_ok=True)
    todo = {n: f for n, f in slices.items() if not (slice_dir / f"{n}.parquet").exists()}
    print(f"{entity}: {len(slices)} slices, {len(todo)} to fetch", flush=True)
    bad = []
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(_pull_slice, entity, version, fields, f, slice_dir / f"{n}.parquet") for n, f in todo.items()]
        for i, fut in enumerate(as_completed(futs), 1):
            name, exp, got = fut.result()
            if exp != got:
                bad.append((name, exp, got))
                (slice_dir / name).unlink()
            if i % 50 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} slices done", flush=True)
    if bad:
        raise RuntimeError(f"row-count mismatch, slices deleted for retry: {bad[:10]}")
    return {"slices": len(slices)}


def _freeze(slice_dir: Path, out: Path) -> int:
    """Concatenate slice files into one frozen parquet (streaming via DuckDB) and remove the slices."""
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_parquet('{slice_dir}/*.parquet', union_by_name = true) ORDER BY id) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]
    for p in slice_dir.glob("*.parquet"):
        p.unlink()
    slice_dir.rmdir()
    return n


def _record(entry: dict) -> None:
    entries = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    entries = [e for e in entries if e["file"] != entry["file"]] + [entry]
    MANIFEST.write_text(json.dumps(entries, indent=2) + "\n")


def _months(start: str, end: str) -> list[tuple[str, str]]:
    ms = pd.period_range(start, end, freq="M")
    return [(str(m.start_time.date()), str((m + 1).start_time.date())) for m in ms]


# ---------------------------------------------------------------- public download entry points

def download_all() -> None:
    """Download and freeze claims, policies and the national in-force check (M1). Skips frozen files."""
    fields = load_config("fields")
    states = load_config("portfolio")["states"]
    today = dt.date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    jobs = [
        (CLAIMS_FILE, fields["claims"], {s: f"state eq '{s}'" for s in states}),
        (POLICIES_FILE, fields["policies"], {
            f"{s}_{a[:7]}": f"propertyState eq '{s}' and policyEffectiveDate ge '{a}' and policyEffectiveDate lt '{b}'"
            for s in states for a, b in _months("2009-01", "2026-12")
        }),
        (NATIONAL_FILE, fields["national_check"], {
            a[:7]: f"policyEffectiveDate ge '{a}' and policyEffectiveDate lt '{b}' and policyTerminationDate gt '2025-12-31'"
            for a, b in _months("2020-01", "2025-12")
        }),
    ]
    for out, spec, slices in jobs:
        if out.exists():
            print(f"{out.name} already frozen; skipping")
            continue
        cols = list(spec["pull"])
        _run_slices(spec["dataset"], spec["version"], cols, slices, RAW_DIR / (out.stem + "_slices"))
        n = _freeze(RAW_DIR / (out.stem + "_slices"), out)
        _record({
            "file": out.name,
            "dataset": spec["dataset"],
            "version": spec["version"],
            "url": f"{API}/v{spec['version']}/{spec['dataset']}?$select=<fields>&$filter=<slice>&$orderby=id (keyset paging)",
            "slices": list(slices.values())[:1] + ["..."],
            "n_slices": len(slices),
            "fields": cols,
            "download_date": today,
            "rows": int(n),
            "sha256": sha256(out),
        })
        print(f"froze {out.name}: {n:,} rows", flush=True)


# ---------------------------------------------------------------- read access for the rest of the package

def raw_path(name: str) -> str:
    """Path of a frozen raw file as a string for DuckDB (`claims`, `policies`, `national`)."""
    return str({"claims": CLAIMS_FILE, "policies": POLICIES_FILE, "national": NATIONAL_FILE}[name])


def query(sql: str) -> pd.DataFrame:
    """Run DuckDB SQL in which `{claims}`, `{policies}` and `{national}` stand for the frozen raw files."""
    sql = sql.format(**{k: f"read_parquet('{raw_path(k)}')" for k in ("claims", "policies", "national")})
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    return con.execute(sql).df()


if __name__ == "__main__":
    download_all()
