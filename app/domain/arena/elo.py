from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EloResult:
    ra_after: float
    rb_after: float


def expected_score(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rb - ra) / 400.0))


def elo_update(ra: float, rb: float, winner: str, k: float) -> EloResult:
    """
    winner: "A", "B" или "D" (ничья)
    """
    ea = expected_score(ra, rb)
    eb = 1.0 - ea

    if winner == "A":
        sa = 1.0
    elif winner == "B":
        sa = 0.0
    else:
        sa = 0.5
    sb = 1.0 - sa

    ra2 = ra + k * (sa - ea)
    rb2 = rb + k * (sb - eb)
    return EloResult(ra_after=ra2, rb_after=rb2)
