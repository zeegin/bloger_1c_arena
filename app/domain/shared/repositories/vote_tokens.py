from __future__ import annotations

from typing import Protocol

from ..models import VoteToken, ActiveVoteToken


class VoteTokensRepository(Protocol):
    async def create(self, user_id: int, vote_type: str, *, channel_a_id: int, channel_b_id: int) -> VoteToken: ...

    async def consume(
        self,
        token: VoteToken,
        *,
        user_id: int,
        vote_type: str,
        channel_a_id: int,
        channel_b_id: int,
    ) -> bool: ...

    async def get_active(self, user_id: int, vote_type: str) -> ActiveVoteToken | None: ...

    async def invalidate(self, user_id: int, vote_type: str) -> None: ...
