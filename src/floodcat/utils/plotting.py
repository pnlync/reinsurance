"""Shared figure styling (SPEC §12)."""
from __future__ import annotations

import matplotlib.pyplot as plt

SUBTITLE = "Gulf Coast reference portfolio (FL, TX, LA, MS, AL), 2025 exposure, USD"

plt.rcParams.update({
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
})


def finish(fig, ax, title: str, subtitle: str = SUBTITLE) -> None:
    """Title plus the SPEC §12 subtitle on every figure."""
    fig.suptitle(title, x=0.02, ha="left", fontsize=12, fontweight="bold")
    ax.set_title(subtitle, loc="left", fontsize=9, color="0.35")
    fig.tight_layout()
