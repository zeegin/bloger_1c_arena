from __future__ import annotations

import random
from typing import Optional, Tuple

from ..models import Channel
from ..repositories import PairingRepository


class PairingPolicy:
    def __init__(self, repo: PairingRepository):
        self._repo = repo

    async def get_pair(self, user_id: int) -> Optional[Tuple[Channel, Channel]]:
        pool = list(await self._repo.fetch_low_game_pool(limit=50))
        if len(pool) < 2:
            return None

        for _ in range(30):
            a = random.choice(pool)
            candidates = list(await self._repo.fetch_closest(a.id, a.rating, limit=20))
            if not candidates:
                continue
            b = random.choice(candidates[:10])
            if not await self._repo.has_seen_pair(user_id, a.id, b.id):
                await self._repo.mark_seen(user_id, a.id, b.id)
                return a, b

        a = random.choice(pool)
        candidates = list(await self._repo.fetch_closest(a.id, a.rating, limit=1))
        if not candidates:
            return None
        b = candidates[0]
        await self._repo.mark_seen(user_id, a.id, b.id)
        return a, b
