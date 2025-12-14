from __future__ import annotations

from typing import Protocol, Sequence

from ...shared.models import Channel


class PairingRepository(Protocol):
    async def fetch_low_game_pool(self, limit: int) -> Sequence[Channel]: ...

    async def fetch_closest(self, channel_id: int, rating: float, limit: int) -> Sequence[Channel]: ...

    async def has_seen_pair(self, user_id: int, a_id: int, b_id: int) -> bool: ...

    async def mark_seen(self, user_id: int, a_id: int, b_id: int) -> None: ...
