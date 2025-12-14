from __future__ import annotations

from typing import Protocol

from ...shared.models import RatingStats, DeathmatchStats


class StatsRepository(Protocol):
    async def rating_stats(self) -> RatingStats: ...

    async def deathmatch_stats(self) -> DeathmatchStats: ...
