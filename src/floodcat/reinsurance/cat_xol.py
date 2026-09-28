"""Catastrophe excess of loss, per occurrence, with annual cap from reinstatements (SPEC §8).

    S'_e       = (1 - q) S_e                        (QS inures first)
    r_e        = c min(max(S'_e - A, 0), L)
    R_year     = min(sum_e r_e, (1 + n) c L)        recoveries accumulate in event order and stop at the cap
    f_year     = min(R_year / (c L), n)
"""
from __future__ import annotations

import numpy as np

from floodcat.reinsurance.reinstatement import reinstated_fraction


def event_recovery(loss_after_qs: np.ndarray, attach: float, limit: float, c: float) -> np.ndarray:
    return c * np.minimum(np.maximum(np.asarray(loss_after_qs, dtype=float) - attach, 0.0), limit)


def apply_cat_xol(event_loss: np.ndarray, year_id: np.ndarray, n_years: int, attach: float, limit: float,
                  c: float, n_reinst: int, q: float = 0.0) -> dict:
    """Vectorised over a YELT (events in within-year order). Returns per-year recovery R and fraction f.

    The annual total min(sum r_e, cap) is the same whatever the order; order matters only for which
    event exhausts the cap, which the annual view does not need."""
    r = event_recovery((1 - q) * np.asarray(event_loss, dtype=float), attach, limit, c)
    gross_rec = np.bincount(year_id, weights=r, minlength=n_years)
    cap = (1 + n_reinst) * c * limit
    rec = np.minimum(gross_rec, cap)
    return {"recovery": rec, "f": reinstated_fraction(rec, c * limit, n_reinst)}


def capped_event_recovery(event_loss: np.ndarray, year_id: np.ndarray, attach: float, limit: float, c: float,
                          n_reinst: int, q: float = 0.0) -> np.ndarray:
    """Per-event recovery after the annual cap, consumed in event order (YELT sorted by year, then event)."""
    r = event_recovery((1 - q) * np.asarray(event_loss, dtype=float), attach, limit, c)
    cap = (1 + n_reinst) * c * limit
    cum = np.cumsum(r)
    start = np.r_[0, np.flatnonzero(np.diff(year_id)) + 1]
    offset = np.repeat(np.r_[0.0, cum][start], np.diff(np.r_[start, len(r)]))
    within = np.minimum(cum - offset, cap)
    prev = np.r_[0.0, within[:-1]]
    prev[start] = 0.0
    return within - prev
