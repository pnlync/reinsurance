"""Gross vs net metrics and economic capital for a programme (SPEC §8, §9 M7).

    L_net      = L_gross - R_QS - sum_layers R + P_QS + sum_layers (P + RP)
    EC         = VaR_0.995(L) - mean(L)
    relief     = EC_gross - EC_net
    net_cost   = sum_layers (P + mean(RP) - mean(R)) + (P_QS - q mean(L_gross))
    implied_coc= net_cost / relief      (NA if relief <= 0)
"""
from __future__ import annotations

import numpy as np

from floodcat.utils import risk_measures as rm


def net_annual_loss(gross: np.ndarray, qs_recovery: np.ndarray, qs_premium: float, layer_results: dict, layer_prices: dict, rate: float) -> np.ndarray:
    net = np.asarray(gross, dtype=float) - qs_recovery + qs_premium
    for lid, res in layer_results.items():
        p = layer_prices[lid]["premium"]
        net = net - res["recovery"] + p + p * rate * res["f"]
    return net


def loss_metrics(x: np.ndarray, var_level: float = 0.995) -> dict:
    x = np.asarray(x, dtype=float)
    return {"mean": float(x.mean()), "sd": float(x.std(ddof=1)), "var_99": rm.var(x, 0.99), "var_995": rm.var(x, var_level),
            "tvar_99": rm.tvar(x, 0.99), "ec": rm.var(x, var_level) - float(x.mean())}


def programme_metrics(gross: np.ndarray, net: np.ndarray, qs_price: dict | None, layer_results: dict, layer_prices: dict,
                      rate: float, var_level: float = 0.995) -> dict:
    g = loss_metrics(gross, var_level)
    n = loss_metrics(net, var_level)
    premium = (qs_price["premium"] if qs_price else 0.0) + sum(layer_prices[l]["premium"] for l in layer_results)
    exp_rp = sum(layer_prices[l]["premium"] * rate * float(np.mean(r["f"])) for l, r in layer_results.items())
    exp_rec = (qs_price["ceded_el"] if qs_price else 0.0) + sum(float(np.mean(r["recovery"])) for r in layer_results.values())
    net_cost = premium + exp_rp - exp_rec
    relief = g["ec"] - n["ec"]
    return {
        "premium": premium, "exp_reinst_premium": exp_rp, "exp_recovery": exp_rec, "net_cost": net_cost,
        "gross_mean": g["mean"], "gross_ec": g["ec"],
        "net_mean": n["mean"], "net_sd": n["sd"], "net_var_99": n["var_99"], "net_var_995": n["var_995"], "net_tvar_99": n["tvar_99"],
        "ec_net": n["ec"], "relief": relief, "relief_pct": relief / g["ec"],
        "implied_coc": net_cost / relief if relief > 0 else float("nan"),
    }
