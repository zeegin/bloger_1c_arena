from __future__ import annotations

from typing import Optional, Protocol, Sequence

from .models import (
    Channel,
    DeathmatchState,
    DeathmatchStats,
    FavoriteChannelInfo,
    RatingStats,
)
from .value_objects import VoteToken


class ChannelsRepository(Protocol):
    async def get(self, channel_id: int) -> Channel: ...

    async def list_top(self, limit: int) -> Sequence[Channel]: ...

    async def list_all(self) -> Sequence[Channel]: ...

    async def list_favorites(self) -> Sequence[FavoriteChannelInfo]: ...

    async def add_or_update(
        self,
        *,
        tg_url: str,
        title: str,
        description: str,
        image_url: str,
    ) -> None: ...

    async def delete_not_in(self, allowed_urls: set[str]) -> int: ...


class PlayersRepository(Protocol):
    async def upsert(self, tg_user_id: int, username: Optional[str], first_name: Optional[str]) -> int: ...

    async def get_classic_games(self, user_id: int) -> int: ...

    async def set_favorite(self, user_id: int, channel_id: Optional[int]) -> None: ...

    async def get_favorite(self, user_id: int) -> Optional[Channel]: ...

    async def get_reward_stage(self, user_id: int) -> int: ...

    async def set_reward_stage(self, user_id: int, stage: int) -> None: ...


class StatsRepository(Protocol):
    async def rating_stats(self) -> RatingStats: ...

    async def deathmatch_stats(self) -> DeathmatchStats: ...


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


class VotesRepository(Protocol):
    async def record_vote(
        self,
        *,
        user_id: int,
        channel_a_before: Channel,
        channel_b_before: Channel,
        channel_a_after: Channel,
        channel_b_after: Channel,
        winner_channel_id: Optional[int],
        draw: bool,
    ) -> None: ...


class DeathmatchRepository(Protocol):
    async def get_state(self, user_id: int) -> Optional[DeathmatchState]: ...

    async def save_state(self, state: DeathmatchState) -> None: ...

    async def delete_state(self, user_id: int) -> None: ...

    async def log_vote(
        self,
        *,
        user_id: int,
        champion_id: Optional[int],
        channel_a_id: int,
        channel_b_id: int,
        winner_id: int,
    ) -> None: ...


class PairingRepository(Protocol):
    async def fetch_low_game_pool(self, limit: int) -> Sequence[Channel]: ...

    async def fetch_closest(self, channel_id: int, rating: float, limit: int) -> Sequence[Channel]: ...

    async def has_seen_pair(self, user_id: int, a_id: int, b_id: int) -> bool: ...

    async def mark_seen(self, user_id: int, a_id: int, b_id: int) -> None: ...
