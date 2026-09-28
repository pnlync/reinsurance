"""Shared SPEC §11 toy objects for the M5-M8 golden tests."""
from pathlib import Path

import numpy as np
import pandas as pd

from floodcat.reinsurance.engine import Layer, Programme, YearEventTable

FIX = Path(__file__).parent / "fixtures" / "toy_yelt.csv"
N_YEARS = 10
PRICING = dict(coc_r=0.10, d=0.5, expense=0.10, rate=1.0)


def toy_table() -> YearEventTable:
    yelt = pd.read_csv(FIX)
    gross = np.bincount(yelt["year_id"], weights=yelt["loss"], minlength=N_YEARS)   # attritional 0
    return YearEventTable(yelt["loss"].to_numpy(float), yelt["year_id"].to_numpy(np.int64), gross)


def toy_max_event() -> np.ndarray:
    yelt = pd.read_csv(FIX)
    m = np.zeros(N_YEARS)
    np.maximum.at(m, yelt["year_id"].to_numpy(), yelt["loss"].to_numpy(float))
    return m


def layer(c=1.0, n=1) -> Layer:
    return Layer("L50x60", attach=60.0, limit=50.0, c=c, n_reinst=n)


def programme(c=1.0, n=1, q=0.0) -> Programme:
    return Programme("toy", q=q, layers=(layer(c, n),))
