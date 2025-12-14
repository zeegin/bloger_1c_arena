from __future__ import annotations

from typing import Sequence

from ...shared.models import Channel, DeathmatchStats, FavoriteChannelInfo, RatingStats
from ..repositories import ChannelsRepository, StatsRepository


class RatingService:
    """
    Доменный сервис поверх репозиториев рейтинга.
    """

    def __init__(self, channels: ChannelsRepository, stats: StatsRepository):
        self._channels = channels
        self._stats = stats

    async def list_top_channels(self, limit: int) -> list[Channel]:
        return list(await self._channels.list_top(limit))

    async def list_all_channels(self) -> list[Channel]:
        return list(await self._channels.list_all())

    async def list_favorite_channels(self) -> list[FavoriteChannelInfo]:
        return list(await self._channels.list_favorites())

    async def get_rating_stats(self) -> RatingStats:
        return await self._stats.rating_stats()

    async def get_deathmatch_stats(self) -> DeathmatchStats:
        return await self._stats.deathmatch_stats()
