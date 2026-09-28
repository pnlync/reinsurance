"""Indicative technical premium for Cat XoL layers and quota share (SPEC §8, §9 M6).

    EL      = mean(C)
    K_R     = TVaR_0.995(C) - EL
    target  = (EL + CoC_R d K_R) / (1 - e)          expected total premium income
    P       = target / (1 + rate mean(f))            upfront premium
    ROL     = P / (c L)
    multiple= (P + P rate mean(f)) / EL
    P_QS    = (q mean(L) + CoC_R d K_QS) / (1 - e_QS),   K_QS = TVaR_0.995(q L) - q mean(L)
"""
from __future__ import annotations

import numpy as np

from floodcat.utils import risk_measures as rm


def price_layer(recovery: np.ndarray, f: np.ndarray, placed_limit: float, *, coc_r: float, d: float,
                expense: float, rate: float, tvar_level: float = 0.995) -> dict:
    c = np.asarray(recovery, dtype=float)
    el = float(c.mean())
    tv = rm.tvar(c, tvar_level)
    k_r = tv - el
    charge = coc_r * d * k_r
    target = (el + charge) / (1 - expense)
    mean_f = float(np.mean(f))
    p = target / (1 + rate * mean_f)
    exp_rp = p * rate * mean_f
    return {
        "el": el, "sd": float(c.std(ddof=1)) if len(c) > 1 else 0.0, "tvar995": tv, "k_r": k_r,
        "capital_charge": charge, "target": target, "mean_f": mean_f, "premium": p,
        "exp_reinst_premium": exp_rp, "rol": p / placed_limit,
        "multiple": (p + exp_rp) / el if el > 0 else float("nan"),
        "net_cost": p + exp_rp - el,
    }


def price_quota_share(gross: np.ndarray, q: float, *, coc_r: float, d: float, expense: float, tvar_level: float = 0.995) -> dict:
    g = np.asarray(gross, dtype=float)
    ceded_el = q * float(g.mean())
    k = rm.tvar(q * g, tvar_level) - ceded_el
    p = (ceded_el + coc_r * d * k) / (1 - expense)
    return {"q": q, "ceded_el": ceded_el, "k_qs": k, "capital_charge": coc_r * d * k, "premium": p, "net_cost": p - ceded_el}


def layer_probabilities(max_event: np.ndarray, q: float, attach: float, exhaust: float) -> dict:
    """AP = P(max S' > A); EP = P(max S' >= A + L), with S' = (1 - q) S (SPEC §11 toy: AP 0.3, EP 0.1)."""
    m = (1 - q) * np.asarray(max_event, dtype=float)
    return {"ap": float(np.mean(m > attach)), "ep": float(np.mean(m >= exhaust))}
