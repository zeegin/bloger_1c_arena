from __future__ import annotations

from typing import Protocol

from ...shared.models import Channel


class VotesRepository(Protocol):
    async def record_vote(
        self,
        *,
        user_id: int,
        channel_a_before: Channel,
        channel_b_before: Channel,
        channel_a_after: Channel,
        channel_b_after: Channel,
        winner_channel_id: int | None,
        draw: bool,
    ) -> None: ...
