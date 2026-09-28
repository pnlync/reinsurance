"""Programmes and `apply_programme` (SPEC §8, §9 M5).

A programme is a quota share q (possibly 0) plus zero, one or two Cat XoL layers in dollar terms.
The QS inures first: every XoL layer sees (1 - q) x event loss; attritional losses are not covered by XoL.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from floodcat.reinsurance.cat_xol import apply_cat_xol
from floodcat.reinsurance.quota_share import apply_quota_share


@dataclass(frozen=True)
class Layer:
    layer_id: str
    attach: float           # USD m, after QS
    limit: float            # USD m
    c: float                # placement share
    n_reinst: int
    attach_rp: int | None = None
    exhaust_rp: int | None = None

    @property
    def exhaust(self) -> float:
        return self.attach + self.limit


@dataclass(frozen=True)
class Programme:
    programme_id: str
    q: float = 0.0
    layers: tuple[Layer, ...] = field(default_factory=tuple)


@dataclass
class YearEventTable:
    """Minimal YELT/YLT view the engine needs; works for simulated years and historical as-if years."""
    event_loss: np.ndarray
    year_id: np.ndarray
    gross: np.ndarray            # annual gross loss (attritional + events), one entry per year

    @property
    def n_years(self) -> int:
        return len(self.gross)

    @classmethod
    def from_frames(cls, yelt: pd.DataFrame, ylt: pd.DataFrame) -> "YearEventTable":
        return cls(yelt["loss"].to_numpy(float), yelt["year_id"].to_numpy(np.int64), ylt["gross"].to_numpy(float))


def apply_programme(t: YearEventTable, prog: Programme, cache: dict | None = None) -> dict:
    """Per-year QS recovery and, per layer, per-year recovery R and reinstated fraction f."""
    out = {"qs_recovery": apply_quota_share(t.gross, prog.q), "layers": {}}
    for lay in prog.layers:
        key = (prog.q, lay.attach, lay.limit, lay.c, lay.n_reinst)
        if cache is not None and key in cache:
            res = cache[key]
        else:
            res = apply_cat_xol(t.event_loss, t.year_id, t.n_years, lay.attach, lay.limit, lay.c, lay.n_reinst, prog.q)
            if cache is not None:
                cache[key] = res
        out["layers"][lay.layer_id] = res
    return out
