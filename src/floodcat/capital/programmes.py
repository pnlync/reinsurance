"""Programme grid from OEP return periods, and evaluation of the grid on any year-event table (SPEC §5.3, §9 M6-M8).

Attachment and exhaustion = (1 - q) x OEP^-1(1/RP) of the gross event loss, rounded to USD 10m.
The dollar terms are fixed from the base model; validation and stresses re-evaluate the same contracts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from floodcat.capital.metrics import net_annual_loss, programme_metrics
from floodcat.reinsurance.cat_xol import capped_event_recovery
from floodcat.reinsurance.engine import Layer, Programme, YearEventTable, apply_programme
from floodcat.reinsurance.pricing import layer_probabilities, price_layer, price_quota_share
from floodcat.utils import risk_measures as rm
from floodcat.utils.io import valid_layer_pairs

NO_RI = "QS0_XS0"


def _pct(x: float) -> int:
    return int(round(100 * x))


def layer_id(q: float, a: int, e: int, c: float, n: int) -> str:
    return f"QS{_pct(q)}_A{a}_E{e}_C{_pct(c)}_R{n}"


def programme_id(q: float, a: int | None = None, e: int | None = None, t: int = 0, c: float | None = None, n: int | None = None) -> str:
    if a is None:
        return f"QS{_pct(q)}_XS0"
    return f"QS{_pct(q)}_A{a}_E{e}_T{t}_C{_pct(c)}_R{n}"


def signature(p: Programme) -> tuple:
    return (p.q, tuple((l.attach, l.limit, l.c, l.n_reinst) for l in p.layers))


def dedupe(progs: list[Programme]) -> tuple[list[Programme], pd.DataFrame]:
    """Drop programmes whose dollar terms equal an earlier one (D13): e.g. exhaustion at 1-in-200 and 1-in-250
    coincide when both return levels sit at the event cap. Returns (unique programmes, alias table)."""
    seen: dict = {}
    unique, aliases = [], []
    for p in progs:
        s = signature(p)
        if s in seen:
            aliases.append({"alias_id": p.programme_id, "programme_id": seen[s]})
        else:
            seen[s] = p.programme_id
            unique.append(p)
    return unique, pd.DataFrame(aliases, columns=["alias_id", "programme_id"])


def generate(max_event: np.ndarray, cfg: dict) -> list[Programme]:
    """All programmes of SPEC §5.3: no RI, pure QS, and QS x layer structures x placement x reinstatements
    (before de-duplication of identical dollar contracts; see `dedupe`)."""
    rnd = cfg["rounding"]

    def level(q: float, rp: int) -> float:
        return float(rnd * round((1 - q) * rm.return_level(max_event, rp) / rnd))

    progs = [Programme(NO_RI)] + [Programme(programme_id(q), q=q) for q in cfg["pure_quota_share"]]
    for q in cfg["quota_share"]:
        for a, e in valid_layer_pairs(cfg):
            structures = [(0, [(a, e)])] + [(t, [(a, t), (t, e)]) for t in cfg["tower_split_rp"] if a < t < e]
            for t, pieces in structures:
                for c in cfg["placement"]:
                    for n in cfg["reinstatements"]:
                        layers = tuple(
                            Layer(layer_id(q, lo, hi, c, n), level(q, lo), level(q, hi) - level(q, lo), c, n, lo, hi)
                            for lo, hi in pieces
                        )
                        progs.append(Programme(programme_id(q, a, e, t, c, n), q=q, layers=layers))
    return progs


def programmes_table(progs: list[Programme]) -> pd.DataFrame:
    rows = []
    for p in progs:
        base = {"programme_id": p.programme_id, "q": p.q, "n_layers": len(p.layers)}
        for i, lay in enumerate(p.layers, 1):
            base.update({f"layer{i}_id": lay.layer_id, f"layer{i}_attach": lay.attach, f"layer{i}_exhaust": lay.exhaust,
                         f"layer{i}_limit": lay.limit, f"layer{i}_attach_rp": lay.attach_rp, f"layer{i}_exhaust_rp": lay.exhaust_rp,
                         f"layer{i}_c": lay.c, f"layer{i}_n_reinst": lay.n_reinst})
        rows.append(base)
    return pd.DataFrame(rows)


def programmes_from_table(df: pd.DataFrame) -> list[Programme]:
    """Rebuild the fixed-dollar programmes from programmes.csv."""
    out = []
    for r in df.to_dict(orient="records"):
        layers = []
        for i in (1, 2):
            if f"layer{i}_id" in r and isinstance(r.get(f"layer{i}_id"), str):
                layers.append(Layer(r[f"layer{i}_id"], float(r[f"layer{i}_attach"]), float(r[f"layer{i}_limit"]), float(r[f"layer{i}_c"]),
                                    int(r[f"layer{i}_n_reinst"]), int(r[f"layer{i}_attach_rp"]), int(r[f"layer{i}_exhaust_rp"])))
        out.append(Programme(r["programme_id"], float(r["q"]), tuple(layers)))
    return out


def unique_layers(progs: list[Programme]) -> dict[str, tuple[float, Layer]]:
    return {lay.layer_id: (p.q, lay) for p in progs for lay in p.layers}


def evaluate(progs: list[Programme], t: YearEventTable, max_event: np.ndarray, pricing: dict, var_level: float = 0.995,
             history: YearEventTable | None = None, net_ep_rps: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Price every layer and QS share on `t`, then compute gross/net metrics for every programme.

    pricing: coc_r, d, xol_expense, qs_expense, rate, tvar_level. Returns (layer_pricing, qs_pricing, programme_metrics).
    net_ep_rps: if given, also report net OEP (largest retained event after QS and XoL) and net AEP at these return periods."""
    kw = dict(coc_r=pricing["coc_r"], d=pricing["d"], rate=pricing["rate"], tvar_level=pricing["tvar_level"])
    cache: dict = {}
    hist_cache: dict = {}
    layer_rows, layer_prices = [], {}
    for lid, (q, lay) in unique_layers(progs).items():
        res = apply_programme(t, Programme(lid, q, (lay,)), cache)["layers"][lid]
        price = price_layer(res["recovery"], res["f"], lay.c * lay.limit, expense=pricing["xol_expense"], **kw)
        layer_prices[lid] = price
        row = {"layer_id": lid, "q": q, "attach": lay.attach, "exhaust": lay.exhaust, "limit": lay.limit, "c": lay.c,
               "n_reinst": lay.n_reinst, "attach_rp": lay.attach_rp, "exhaust_rp": lay.exhaust_rp,
               **layer_probabilities(max_event, q, lay.attach, lay.exhaust)}
        if history is not None:
            h = apply_programme(history, Programme(lid, q, (lay,)), hist_cache)["layers"][lid]["recovery"]
            row.update({"years_hit": int((h > 0).sum()), "burning_cost": float(h.mean())})
        row.update(price)
        layer_rows.append(row)
    layers_df = pd.DataFrame(layer_rows)

    qs_prices = {}
    for q in sorted({p.q for p in progs if p.q > 0}):
        qs_prices[q] = price_quota_share(t.gross, q, coc_r=pricing["coc_r"], d=pricing["d"], expense=pricing["qs_expense"], tvar_level=pricing["tvar_level"])
    qs_df = pd.DataFrame(list(qs_prices.values()))

    rows = []
    for p in progs:
        res = apply_programme(t, p, cache)
        qp = qs_prices.get(p.q)
        net = net_annual_loss(t.gross, res["qs_recovery"], qp["premium"] if qp else 0.0, res["layers"], layer_prices, pricing["rate"])
        m = programme_metrics(t.gross, net, qp, res["layers"], layer_prices, pricing["rate"], var_level)
        row = {"programme_id": p.programme_id, "q": p.q, "n_layers": len(p.layers), **m}
        if net_ep_rps:
            retained = (1 - p.q) * t.event_loss
            for lay in p.layers:
                retained = retained - capped_event_recovery(t.event_loss, t.year_id, lay.attach, lay.limit, lay.c, lay.n_reinst, p.q)
            net_max = np.zeros(t.n_years)
            np.maximum.at(net_max, t.year_id, retained)
            for rp in net_ep_rps:
                row[f"net_oep_{rp}"] = rm.return_level(net_max, rp)
                row[f"net_aep_{rp}"] = rm.return_level(net, rp)
        rows.append(row)
    return layers_df, qs_df, pd.DataFrame(rows)
