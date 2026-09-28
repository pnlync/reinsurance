"""Project paths and config loading with validation (SPEC §1.8, §5)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "config"
PROCESSED_DIR = ROOT / "data" / "processed"
MARKET_DIR = ROOT / "data" / "market"
OUTPUTS_DIR = ROOT / "outputs"
TABLES_DIR = OUTPUTS_DIR / "tables"
FIGURES_DIR = OUTPUTS_DIR / "figures"
REPORTS_DIR = ROOT / "reports"
EXCEL_DIR = ROOT / "excel"

CONFIG_NAMES = ("portfolio", "modelling", "simulation", "reinsurance", "stress", "fields")


class ConfigError(ValueError):
    """Raised when a config file fails validation."""


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _is_prob(x) -> bool:
    return isinstance(x, (int, float)) and 0 <= x <= 1


def _validate_portfolio(c: dict) -> None:
    _check(isinstance(c["states"], list) and len(c["states"]) > 0, "states must be a non-empty list")
    _check(all(isinstance(s, str) and len(s) == 2 for s in c["states"]), "states must be 2-letter codes")
    _check(isinstance(c["target_year"], int), "target_year must be int")
    s, e = c["calibration"]["start"], c["calibration"]["end"]
    _check(isinstance(s, int) and isinstance(e, int) and s < e < c["target_year"], "calibration must satisfy start < end < target_year")
    _check(all(y > e for y in c["holdout"]["years"]), "holdout years must follow calibration")
    f0, f1 = c["backtest"]["fit"]
    t0, t1 = c["backtest"]["test"]
    _check(s <= f0 < f1 < t0 <= t1 <= e, "backtest fit/test must lie inside calibration, fit before test")
    crs = c["crs_check"]
    _check(all(isinstance(crs[k], (int, float)) and crs[k] > 0 for k in ("ref_policies", "ref_coverage_usd")), "crs_check values must be positive numbers")
    _check(0 < crs["tolerance"] < 1, "crs_check tolerance must be in (0, 1)")
    _check(all(isinstance(v, (int, float)) for v in c["cpi_u_annual"].values()), "CPI values must be numbers")


def _validate_modelling(c: dict) -> None:
    _check(c["event_threshold_u0"] > 0, "u0 must be positive")
    _check(set(c["frequency"]["candidates"]) <= {"poisson", "negbin"}, "unknown frequency family")
    _check(c["frequency"]["lr_critical"] > 0, "lr_critical must be positive")
    _check(set(c["severity"]["candidates"]) <= {"lognormal", "loglogistic", "burr12"}, "unknown severity family")
    _check(isinstance(c["gpd"]["min_exceedances"], int) and c["gpd"]["min_exceedances"] > 0, "gpd.min_exceedances must be a positive int")
    _check(c["event_cap_multiple"] >= 1, "event cap multiple must be >= 1")
    _check(c["attritional"]["base"] in {"bootstrap", "lognormal"}, "attritional.base must be bootstrap or lognormal")


def _validate_simulation(c: dict) -> None:
    _check(isinstance(c["n_years"], int) and c["n_years"] > 0, "n_years must be a positive int")
    _check(c["convergence"]["n_years"] > c["n_years"], "convergence run must be larger than base")
    _check(0 < c["convergence"]["tolerance"] < 1, "tolerance must be in (0, 1)")
    _check(isinstance(c["n_batches"], int) and c["n_years"] % c["n_batches"] == 0, "n_years must split evenly into n_batches")
    _check(isinstance(c["seed"], int), "seed must be int")
    _check(c["bootstrap"]["replicates"] > 0 and c["bootstrap"]["n_years"] > 0, "bootstrap sizes must be positive")


def valid_layer_pairs(cfg: dict) -> list[tuple[int, int]]:
    """(attachment RP, exhaustion RP) pairs with exhaustion > attachment (SPEC §5.3)."""
    return [(a, e) for a in cfg["attachment_rp"] for e in cfg["exhaustion_rp"] if e > a]


def _validate_reinsurance(c: dict) -> None:
    _check(all(_is_prob(q) and q < 1 for q in c["quota_share"]), "quota shares must be in [0, 1)")
    _check(all(q in c["quota_share"] and q > 0 for q in c["pure_quota_share"]), "pure QS shares must be positive grid shares")
    _check(all(isinstance(r, int) and r > 1 for r in c["attachment_rp"] + c["exhaustion_rp"] + c["tower_split_rp"]), "return periods must be ints > 1")
    _check(len(valid_layer_pairs(c)) > 0, "no valid attachment/exhaustion pair")
    _check(all(_is_prob(p) and p > 0 for p in c["placement"]), "placements must be in (0, 1]")
    _check(all(isinstance(n, int) and n >= 0 for n in c["reinstatements"]), "reinstatements must be non-negative ints")
    _check(_is_prob(c["reinstatement_rate"]), "reinstatement rate must be in [0, 1]")
    _check(c["rounding"] > 0, "rounding must be positive")
    p = c["pricing"]
    for k in ("coc_r", "diversification_d", "xol_expense", "qs_expense", "tvar_level"):
        _check(_is_prob(p[k]), f"pricing.{k} must be in [0, 1]")
    _check(p["xol_expense"] < 1 and p["qs_expense"] < 1, "expense loads must be < 1")
    d = c["decision"]
    _check(_is_prob(d["hurdle"]) and all(_is_prob(h) for h in d["hurdle_sensitivity"]), "hurdles must be in [0, 1]")
    _check(_is_prob(d["budget_min_relief"]), "budget_min_relief must be in [0, 1]")
    _check(_is_prob(c["capital"]["var_level"]), "capital.var_level must be in [0, 1]")


_STRESS_KEYS = {"frequency_scale", "severity_scale", "tail", "xi_shift", "coc_r", "diversification_d", "hurdle"}


def _validate_stress(c: dict) -> None:
    _check(isinstance(c["scenarios"], dict) and len(c["scenarios"]) > 0, "stress scenarios missing")
    for name, s in c["scenarios"].items():
        _check(set(s) <= _STRESS_KEYS, f"stress {name}: unknown keys {set(s) - _STRESS_KEYS}")
        for k in ("coc_r", "diversification_d", "hurdle"):
            if k in s:
                _check(_is_prob(s[k]), f"stress {name}: {k} must be in [0, 1]")
        for k in ("frequency_scale", "severity_scale"):
            if k in s:
                _check(s[k] > 0, f"stress {name}: {k} must be positive")


def _validate_fields(c: dict) -> None:
    _check("claims" in c and "policies" in c, "fields.yaml needs claims and policies sections")


_VALIDATORS = {
    "portfolio": _validate_portfolio,
    "modelling": _validate_modelling,
    "simulation": _validate_simulation,
    "reinsurance": _validate_reinsurance,
    "stress": _validate_stress,
    "fields": _validate_fields,
}


def load_config(name: str) -> dict:
    """Load and validate `config/<name>.yaml` (SPEC §5)."""
    if name not in CONFIG_NAMES:
        raise ConfigError(f"unknown config {name!r}")
    with open(CONFIG_DIR / f"{name}.yaml") as fh:
        cfg = yaml.safe_load(fh)
    try:
        _VALIDATORS[name](cfg)
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"{name}.yaml: missing or malformed entry ({exc})") from exc
    return cfg


def git_hash() -> str:
    """Short git hash of HEAD, with '-dirty' if the tree has uncommitted changes (SPEC §4.3)."""
    try:
        h = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "src", "config"], cwd=ROOT)
        return h + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=float)
        fh.write("\n")
