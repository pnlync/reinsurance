"""Reinstatements (SPEC §8): reinstated fraction f and reinstatement premium RP = P x rate x f."""
from __future__ import annotations

import numpy as np


def reinstated_fraction(annual_recovery: np.ndarray, placed_limit: float, n_reinst: int) -> np.ndarray:
    """f_year = min(R_year / (c L), n): share of the placed limit restored (and paid for) in the year."""
    return np.minimum(np.asarray(annual_recovery) / placed_limit, n_reinst)


def reinstatement_premium(f: np.ndarray, upfront_premium: float, rate: float) -> np.ndarray:
    return upfront_premium * rate * np.asarray(f)
