"""Cost-capital frontier, convex hull, marginal cost of capital and the three management choices (SPEC §8, §9 M8).

    dominated   i if some j has net_cost_j <= net_cost_i and EC_j <= EC_i with one strict
    frontier    non-dominated programmes, sorted by net cost
    hull        lower convex hull of the frontier in (net_cost, EC_net), starting at no reinsurance
    marginal CoC between hull points k-1, k = (net_cost_k - net_cost_(k-1)) / (relief_k - relief_(k-1))
    Budget-first     = cheapest frontier programme with relief_pct >= budget_min_relief
    Balanced(h)      = last hull point whose marginal CoC <= h (walking from no reinsurance)
    Protection-first = frontier programme with the lowest EC_net
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def dominated(df: pd.DataFrame, cost: str = "net_cost", risk: str = "ec_net") -> pd.Series:
    c, r = df[cost].to_numpy(), df[risk].to_numpy()
    out = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        weak = (c <= c[i]) & (r <= r[i])
        strict = (c < c[i]) | (r < r[i])
        out[i] = bool(np.any(weak & strict))
    return pd.Series(out, index=df.index)


def frontier(df: pd.DataFrame, cost: str = "net_cost", risk: str = "ec_net") -> pd.DataFrame:
    return df[~dominated(df, cost, risk)].sort_values([cost, risk]).copy()


def lower_hull(front: pd.DataFrame, start_id: str, cost: str = "net_cost", risk: str = "ec_net", id_col: str = "programme_id") -> pd.DataFrame:
    """Lower convex hull of the frontier from the no-reinsurance point (monotone chain)."""
    pts = front.sort_values([cost, risk])
    start = pts[pts[id_col] == start_id]
    pts = pd.concat([start, pts[(pts[cost] >= float(start[cost].iloc[0])) & (pts[id_col] != start_id)]])
    hull: list[int] = []
    for idx in pts.index:
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = pts.loc[hull[-2], [cost, risk]], pts.loc[hull[-1], [cost, risk]]
            x3, y3 = pts.loc[idx, [cost, risk]]
            # drop the middle point unless it lies strictly below the chord (convex from below)
            if (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1) <= 0:
                hull.pop()
            else:
                break
        hull.append(idx)
    h = pts.loc[hull].copy()
    h["marginal_coc"] = np.nan
    dc = h[cost].diff()
    dr = -h[risk].diff()
    h.loc[h.index[1:], "marginal_coc"] = (dc / dr).iloc[1:].values
    return h


def balanced(hull: pd.DataFrame, h: float, id_col: str = "programme_id") -> str:
    pick = hull.iloc[0][id_col]
    for _, row in hull.iloc[1:].iterrows():
        if row["marginal_coc"] <= h:
            pick = row[id_col]
        else:
            break
    return pick


def budget_first(front: pd.DataFrame, min_relief: float, id_col: str = "programme_id") -> str | None:
    ok = front[front["relief_pct"] >= min_relief]
    return None if ok.empty else ok.sort_values(["net_cost", "ec_net"]).iloc[0][id_col]


def protection_first(front: pd.DataFrame, id_col: str = "programme_id") -> str:
    return front.sort_values(["ec_net", "net_cost"]).iloc[0][id_col]


def choices(df: pd.DataFrame, start_id: str, hurdles: list[float], min_relief: float, id_col: str = "programme_id") -> dict:
    front = frontier(df)
    hull = lower_hull(front, start_id, id_col=id_col)
    return {
        "frontier": front, "hull": hull,
        "budget_first": budget_first(front, min_relief, id_col),
        "balanced": {h: balanced(hull, h, id_col) for h in hurdles},
        "protection_first": protection_first(front, id_col),
    }
