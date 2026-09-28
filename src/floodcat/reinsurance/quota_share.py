"""Quota share (SPEC §8): R_QS = q x (A_year + sum_e S_e)."""
from __future__ import annotations

import numpy as np


def apply_quota_share(gross: np.ndarray, q: float) -> np.ndarray:
    """Annual QS recovery for each year."""
    return q * np.asarray(gross, dtype=float)
