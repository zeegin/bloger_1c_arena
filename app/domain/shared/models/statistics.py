from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RatingStats:
    games: int
    players: int


@dataclass(frozen=True)
class DeathmatchStats:
    games: int
    players: int
